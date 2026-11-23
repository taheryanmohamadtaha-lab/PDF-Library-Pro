"""Internal PDF reader: lazy page rendering with cache, selection, highlights, search."""
import logging
from collections import OrderedDict

import pymupdf
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractScrollArea, QCheckBox, QComboBox, QDockWidget, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QSpinBox, QTabWidget, QToolBar, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QWidget)

from ..core.i18n import tr
from .dialogs import confirm
from .icons import icon

log = logging.getLogger("pdflp.reader")
MARGIN, GAP = 24, 16
HL_COLORS = {"yellow": "#ffe066", "green": "#8ce99a", "blue": "#74c0fc", "pink": "#faa2c1"}


class PageView(QAbstractScrollArea):
    pageChanged = Signal(int)
    selectionMade = Signal(int, object, str)  # page, rect(page space), text
    zoomChanged = Signal(float)

    def __init__(self):
        super().__init__()
        self.doc = None
        self.zoom, self.fit = 1.0, "width"
        self.rot = 0
        self.mode = "continuous"  # single | double | continuous
        self.rtl_pages = False
        self.cur = 0
        self.cache = OrderedDict()
        self.sizes = []          # base (zoom=1, rot applied) size per page
        self.rows = []           # list of lists of page indexes
        self.row_y, self.row_h = [], []
        self.highlights = {}     # page -> rows
        self.hits = {}           # page -> [Rect]
        self.search_term = ""
        self.sel = None          # (page, QPointF start, QPointF end) in pixmap coords
        self.sel_text = ""
        self.highlight_provider = None
        self.setBackgroundRole(self.backgroundRole())
        self.viewport().setStyleSheet("background:#3b3b42;")
        self.viewport().setMouseTracking(True)
        self._wheel_acc = 0
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self._prefetch = QTimer(self, singleShot=True, interval=60, timeout=self._prefetch_next)

    # ---------------------------------------------------------------- loading
    def set_doc(self, doc):
        self.doc = doc
        self.sizes = []
        for i in range(doc.page_count):
            r = doc.load_page(i).rect
            self.sizes.append((r.width, r.height))
        self.cache.clear()
        self.relayout()

    def base_size(self, i):
        w, h = self.sizes[i]
        return (h, w) if self.rot % 180 else (w, h)

    # ---------------------------------------------------------------- layout
    def _build_rows(self):
        n = len(self.sizes)
        if self.mode == "double":
            self.rows, i = [], 0
            while i < n:
                pair = [i] if i == 0 else [i, i + 1] if i + 1 < n else [i]
                if i == 0:
                    pair = [0]
                    i += 1
                else:
                    i += len(pair)
                self.rows.append(pair)
        else:
            self.rows = [[i] for i in range(n)]

    def relayout(self):
        if not self.doc:
            return
        self._build_rows()
        vw, vh = self.viewport().width(), self.viewport().height()
        if self.fit:
            idx = self.rows[self._row_of(self.cur)]
            bw = sum(self.base_size(i)[0] for i in idx) + GAP * (len(idx) - 1)
            bh = max(self.base_size(i)[1] for i in idx)
            zw = (vw - 2 * MARGIN) / max(bw, 1)
            zh = (vh - 2 * MARGIN) / max(bh, 1)
            self.zoom = max(0.1, min(zw if self.fit == "width" else min(zw, zh), 8.0))
        self.row_y, self.row_h, y = [], [], MARGIN
        for row in self.rows:
            h = int(max(self.base_size(i)[1] for i in row) * self.zoom)
            self.row_y.append(y)
            self.row_h.append(h)
            y += h + GAP
        self.total_h = y + MARGIN - GAP
        maxw = max(sum(int(self.base_size(i)[0] * self.zoom) for i in r) + GAP * (len(r) - 1) for r in self.rows)
        self.total_w = maxw + 2 * MARGIN
        self.verticalScrollBar().setPageStep(vh)
        self.verticalScrollBar().setSingleStep(40)
        self.horizontalScrollBar().setPageStep(vw)
        if self.mode == "continuous":
            self.verticalScrollBar().setRange(0, max(0, self.total_h - vh))
        else:
            self.verticalScrollBar().setRange(0, max(0, max(self.row_h[self._row_of(self.cur)] + 2 * MARGIN - vh, 0)))
        self.horizontalScrollBar().setRange(0, max(0, self.total_w - vw))
        self.zoomChanged.emit(self.zoom)
        self.go_to(self.cur, emit=False)
        self.viewport().update()

    def _row_of(self, page):
        for i, r in enumerate(self.rows):
            if page in r:
                return i
        return 0

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()

    # ------------------------------------------------------------ navigation
    def go_to(self, page, emit=True):
        if not self.doc:
            return
        page = max(0, min(page, self.doc.page_count - 1))
        self.cur = page
        if self.mode == "continuous":
            self.verticalScrollBar().blockSignals(True)
            self.verticalScrollBar().setValue(max(0, self.row_y[self._row_of(page)] - MARGIN // 2))
            self.verticalScrollBar().blockSignals(False)
        else:
            self.verticalScrollBar().setRange(0, max(0, self.row_h[self._row_of(page)] + 2 * MARGIN
                                                    - self.viewport().height()))
            self.verticalScrollBar().setValue(0)
        self.viewport().update()
        if emit:
            self.pageChanged.emit(page)

    def step(self, delta):
        if self.mode == "double":
            r = self._row_of(self.cur) + delta
            r = max(0, min(r, len(self.rows) - 1))
            self.go_to(self.rows[r][0])
        else:
            self.go_to(self.cur + delta)

    def _on_scroll(self, v):
        if self.mode != "continuous" or not self.doc:
            self.viewport().update()
            return
        mid = v + self.viewport().height() * 0.3
        r = 0
        for i, y in enumerate(self.row_y):
            if y <= mid:
                r = i
        new = self.rows[r][0]
        if new != self.cur:
            self.cur = new
            self.pageChanged.emit(new)
        self.viewport().update()

    def set_zoom(self, z):
        self.fit = None
        self.zoom = max(0.1, min(z, 8.0))
        self.cache.clear()
        self._relayout_keep()

    def set_fit(self, fit):
        self.fit = fit
        self.cache.clear()
        self._relayout_keep()

    def set_rotation(self, rot):
        self.rot = rot % 360
        self.cache.clear()
        self._relayout_keep()

    def set_mode(self, mode):
        self.mode = mode
        self._relayout_keep()

    def _relayout_keep(self):
        cur = self.cur
        self.relayout()
        self.go_to(cur, emit=False)

    # -------------------------------------------------------------- rendering
    def _matrix(self, z=None):
        return pymupdf.Matrix(z or self.zoom, z or self.zoom).prerotate(self.rot)

    def render_page(self, i) -> QPixmap:
        key = (i, round(self.zoom, 3), self.rot)
        pm = self.cache.get(key)
        if pm is not None:
            self.cache.move_to_end(key)
            return pm
        ratio = self.devicePixelRatioF()
        pix = self.doc.load_page(i).get_pixmap(matrix=self._matrix(self.zoom * ratio), alpha=False)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(ratio)
        self.cache[key] = pm
        while len(self.cache) > 14:
            self.cache.popitem(last=False)
        return pm

    def _page_origin(self, i):
        """Top-left (widget coords) of page i, or None if hidden."""
        r = self._row_of(i)
        vp = self.viewport()
        row = self.rows[r]
        widths = [int(self.base_size(p)[0] * self.zoom) for p in row]
        order = list(row)[::-1] if (self.rtl_pages and len(row) > 1) else list(row)
        total = sum(widths) + GAP * (len(row) - 1)
        x = (vp.width() - total) // 2 - self.horizontalScrollBar().value() if total < vp.width() else MARGIN - \
            self.horizontalScrollBar().value()
        for p in order:
            w = int(self.base_size(p)[0] * self.zoom)
            if p == i:
                break
            x += int(self.base_size(p)[0] * self.zoom) + GAP
        if self.mode == "continuous":
            y = self.row_y[r] - self.verticalScrollBar().value()
        else:
            y = MARGIN - self.verticalScrollBar().value()
        h = int(self.base_size(i)[1] * self.zoom)
        rowh = self.row_h[r]
        y += (rowh - h) // 2
        return x, y

    def visible_pages(self):
        if not self.doc:
            return []
        if self.mode != "continuous":
            return list(self.rows[self._row_of(self.cur)])
        top = self.verticalScrollBar().value()
        bot = top + self.viewport().height()
        out = []
        for r, (y, h) in enumerate(zip(self.row_y, self.row_h)):
            if y + h >= top and y <= bot:
                out += self.rows[r]
        return out

    def _to_pixmap_rect(self, page, rect) -> QRectF:
        pr = self.doc.load_page(page).rect
        T = self._matrix()
        tl = (pr * T).tl
        r = pymupdf.Rect(rect) * T
        return QRectF(r.x0 - tl.x, r.y0 - tl.y, r.width, r.height)

    def paintEvent(self, e):
        p = QPainter(self.viewport())
        if not self.doc:
            return
        for i in self.visible_pages():
            ox, oy = self._page_origin(i)
            pm = self.render_page(i)
            w, h = int(self.base_size(i)[0] * self.zoom), int(self.base_size(i)[1] * self.zoom)
            p.fillRect(ox + 3, oy + 4, w, h, QColor(0, 0, 0, 90))
            p.drawPixmap(ox, oy, pm)
            for hl in self.highlights_for(i):
                rc = self._to_pixmap_rect(i, (hl["x0"], hl["y0"], hl["x1"], hl["y1"]))
                c = QColor(hl["color"])
                c.setAlpha(110)
                p.fillRect(rc.translated(ox, oy), c)
            for rect in self.hits.get(i, []):
                rc = self._to_pixmap_rect(i, rect)
                p.fillRect(rc.translated(ox, oy), QColor(255, 140, 0, 120))
            if self.sel and self.sel[0] == i:
                a, b = self.sel[1], self.sel[2]
                rc = QRectF(a, b).normalized().translated(ox, oy)
                p.fillRect(rc, QColor(70, 130, 255, 70))
                p.setPen(QPen(QColor(70, 130, 255), 1))
                p.drawRect(rc)
        self._schedule_prefetch()

    def highlights_for(self, page):
        if self.highlight_provider is None:
            return []
        if page not in self.highlights:
            self.highlights[page] = self.highlight_provider(page + 1)
        return self.highlights[page]

    def invalidate_highlights(self):
        self.highlights.clear()
        self.viewport().update()

    def _schedule_prefetch(self):
        if self.doc and not self._prefetch.isActive():
            self._prefetch.start()

    def _prefetch_next(self):
        if not self.doc:
            return
        vis = self.visible_pages()
        if not vis:
            return
        for cand in (vis[-1] + 1, vis[0] - 1):
            if 0 <= cand < self.doc.page_count and (cand, round(self.zoom, 3), self.rot) not in self.cache:
                self.render_page(cand)
                return

    # --------------------------------------------------------------- search
    def set_hits(self, term, hits):
        self.search_term, self.hits = term, hits
        self.viewport().update()

    # --------------------------------------------------------------- input
    def _page_at(self, pos):
        for i in self.visible_pages():
            ox, oy = self._page_origin(i)
            w, h = int(self.base_size(i)[0] * self.zoom), int(self.base_size(i)[1] * self.zoom)
            if ox <= pos.x() <= ox + w and oy <= pos.y() <= oy + h:
                return i, QPointF(pos.x() - ox, pos.y() - oy)
        return None, None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            i, pt = self._page_at(e.position().toPoint())
            self.sel = (i, pt, pt) if i is not None else None
            self.sel_text = ""
            self.viewport().update()

    def mouseMoveEvent(self, e):
        if self.sel and e.buttons() & Qt.LeftButton:
            i = self.sel[0]
            ox, oy = self._page_origin(i)
            w, h = int(self.base_size(i)[0] * self.zoom), int(self.base_size(i)[1] * self.zoom)
            x = min(max(e.position().x() - ox, 0), w)
            y = min(max(e.position().y() - oy, 0), h)
            self.sel = (i, self.sel[1], QPointF(x, y))
            self.viewport().update()

    def mouseReleaseEvent(self, e):
        if self.sel and e.button() == Qt.LeftButton:
            i, a, b = self.sel
            rc = QRectF(a, b).normalized()
            if rc.width() < 4 or rc.height() < 4:
                self.sel = None
                self.viewport().update()
                return
            page_rect = self._to_page_rect(i, rc)
            text = self.doc.load_page(i).get_text("text", clip=page_rect).strip()
            self.sel_text = text
            self.selectionMade.emit(i, page_rect, text)

    def _to_page_rect(self, i, rc: QRectF) -> pymupdf.Rect:
        pr = self.doc.load_page(i).rect
        T = self._matrix()
        tl = (pr * T).tl
        inv = ~T
        p0 = pymupdf.Point(rc.left() + tl.x, rc.top() + tl.y) * inv
        p1 = pymupdf.Point(rc.right() + tl.x, rc.bottom() + tl.y) * inv
        return pymupdf.Rect(p0, p1).normalize()

    def clear_selection(self):
        self.sel, self.sel_text = None, ""
        self.viewport().update()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            self.set_zoom(self.zoom * (1.12 if e.angleDelta().y() > 0 else 1 / 1.12))
            return
        if self.mode == "continuous":
            super().wheelEvent(e)
            return
        sb = self.verticalScrollBar()
        d = e.angleDelta().y()
        if (d < 0 and sb.value() >= sb.maximum()) or (d > 0 and sb.value() <= sb.minimum()):
            self._wheel_acc += d
            if abs(self._wheel_acc) >= 120:
                self.step(1 if self._wheel_acc < 0 else -1)
                self._wheel_acc = 0
        else:
            self._wheel_acc = 0
            super().wheelEvent(e)

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_PageDown, Qt.Key_Right) and self.mode != "continuous" or k == Qt.Key_PageDown:
            self.step(1)
        elif k in (Qt.Key_PageUp, Qt.Key_Left) and self.mode != "continuous" or k == Qt.Key_PageUp:
            self.step(-1)
        elif k == Qt.Key_Home:
            self.go_to(0)
        elif k == Qt.Key_End:
            self.go_to(self.doc.page_count - 1)
        elif e.matches(QKeySequence.Copy) and self.sel_text:
            QGuiApplication.clipboard().setText(self.sel_text)
        else:
            super().keyPressEvent(e)


class ReaderWindow(QMainWindow):
    closed = Signal(int, int)

    def __init__(self, ctx, lib_id: int, book_id: int, start_page: int = 0):
        super().__init__()
        self.ctx, self.lib_id, self.bid = ctx, lib_id, book_id
        self.svc = ctx.mgr.service(lib_id)
        self.book = self.svc.book(book_id)
        self.doc = None
        self.password = ""
        self.setWindowTitle(self.book["title"])
        self.resize(1180, 820)
        self.pv = PageView()
        self.setCentralWidget(self.pv)
        self.pv.highlight_provider = lambda pg: [dict(r) for r in self.svc.highlights(self.bid, pg)]
        self.pv.pageChanged.connect(self._page_changed)
        self.pv.selectionMade.connect(self._selection)
        self.pv.zoomChanged.connect(lambda z: self.zoom_lbl.setText(f"{int(z * 100)}%"))
        self.pv.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pv.customContextMenuRequested.connect(self._menu)
        self._build_toolbar()
        self._build_side()
        self._save_timer = QTimer(self, singleShot=True, interval=700, timeout=self._save_progress)
        self.hl_color = HL_COLORS["yellow"]
        self.ok = self._open_doc()
        if self.ok:
            prog = self.svc.progress(book_id)
            mode = prog["mode"] if prog and prog["mode"] else "continuous"
            self.mode_box.setCurrentIndex({"single": 0, "double": 1, "continuous": 2}.get(mode, 2))
            page = start_page - 1 if start_page else (prog["page"] - 1 if prog and prog["page"] else 0)
            self.pv.cur = max(0, min(page, self.doc.page_count - 1))
            self.pv.relayout()
            self._page_changed(self.pv.cur, save=False)
            self.svc.touch_opened(book_id, self.pv.cur + 1)
            self.refresh_side()

    # ------------------------------------------------------------------ open
    def _open_doc(self) -> bool:
        path = self.book["path"]
        try:
            doc = pymupdf.open(path)
        except Exception as e:
            QMessageBox.warning(self, tr("open_failed"), f"{tr('open_failed')}:\n{path}\n{e}")
            return False
        if doc.needs_pass:
            for _ in range(3):
                pw, ok = QInputDialog.getText(self, tr("password_req"), tr("password_req"), QLineEdit.Password)
                if not ok:
                    return False
                if doc.authenticate(pw):
                    self.password = pw
                    break
            else:
                return False
            if not self.book["indexed"]:
                self.svc.index_book(self.bid, password=self.password)
        self.doc = doc
        self.pv.set_doc(doc)
        self.total_lbl.setText(f"/ {doc.page_count}")
        self.page_spin.setRange(1, doc.page_count)
        return True

    # --------------------------------------------------------------- toolbar
    def _tb(self, name, tip, fn, checkable=False):
        b = QToolButton()
        b.setIcon(icon(name, self.ctx.pal.text, 20))
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.clicked.connect(fn)
        self.tb.addWidget(b)
        return b

    def _build_toolbar(self):
        self.tb = QToolBar()
        self.tb.setMovable(False)
        self.addToolBar(self.tb)
        self.side_btn = self._tb("menu", tr("toc"), lambda c: self.side.setVisible(c), True)
        self.side_btn.setChecked(True)
        self._tb("up", "◀", lambda: self.pv.step(-1))
        self.page_spin = QSpinBox()
        self.page_spin.setMinimumWidth(70)
        self.page_spin.editingFinished.connect(lambda: self.pv.go_to(self.page_spin.value() - 1))
        self.tb.addWidget(self.page_spin)
        self.total_lbl = QLabel("/ 0")
        self.tb.addWidget(self.total_lbl)
        self._tb("down", "▶", lambda: self.pv.step(1))
        self.tb.addSeparator()
        self._tb("zoomout", tr("zoom_out"), lambda: self.pv.set_zoom(self.pv.zoom / 1.15))
        self.zoom_lbl = QLabel("100%")
        self.tb.addWidget(self.zoom_lbl)
        self._tb("zoomin", tr("zoom_in"), lambda: self.pv.set_zoom(self.pv.zoom * 1.15))
        self._tb("fitw", tr("fit_width"), lambda: self.pv.set_fit("width"))
        self._tb("fitp", tr("fit_page"), lambda: self.pv.set_fit("page"))
        self._tb("rotate", tr("rotate"), lambda: self.pv.set_rotation(self.pv.rot + 90))
        self.mode_box = QComboBox()
        self.mode_box.addItems([tr("single"), tr("double"), tr("continuous")])
        self.mode_box.setCurrentIndex(2)
        self.mode_box.currentIndexChanged.connect(
            lambda i: (self.pv.set_mode(("single", "double", "continuous")[i]), self._save_progress()))
        self.tb.addWidget(self.mode_box)
        rtl = QCheckBox("RTL")
        rtl.toggled.connect(lambda c: (setattr(self.pv, "rtl_pages", c), self.pv.viewport().update()))
        self.tb.addWidget(rtl)
        self.tb.addSeparator()
        self._tb("bookmark", tr("bookmark"), self.add_bookmark)
        self.color_box = QComboBox()
        for name in HL_COLORS:
            self.color_box.addItem(name)
        self.color_box.currentTextChanged.connect(lambda n: setattr(self, "hl_color", HL_COLORS[n]))
        self.tb.addWidget(self.color_box)
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText(tr("find"))
        self.find_edit.setFixedWidth(180)
        self.find_edit.returnPressed.connect(self.do_find)
        self.tb.addWidget(self.find_edit)
        self._tb("fullscreen", tr("fullscreen") + " (F11)", self.toggle_fs)
        self.prog = QProgressBar()
        self.prog.setFixedWidth(110)
        self.prog.setTextVisible(False)
        self.tb.addWidget(self.prog)
        QShortcut(QKeySequence("F11"), self, self.toggle_fs)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.find_edit.setFocus())
        QShortcut(QKeySequence("Escape"), self, lambda: self.isFullScreen() and self.toggle_fs())

    def toggle_fs(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def _build_side(self):
        self.side = QDockWidget(self)
        self.side.setTitleBarWidget(QWidget())
        self.tabs = QTabWidget()
        self.toc = QTreeWidget(); self.toc.setHeaderHidden(True)
        self.toc.itemClicked.connect(lambda it, _: self.pv.go_to(it.data(0, Qt.UserRole) - 1))
        self.pages_list = QListWidget()
        self.pages_list.itemClicked.connect(lambda it: self.pv.go_to(it.data(Qt.UserRole) - 1))
        self.bm_list = QListWidget()
        self.bm_list.itemDoubleClicked.connect(lambda it: self.pv.go_to(it.data(Qt.UserRole)[0] - 1))
        self.bm_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bm_list.customContextMenuRequested.connect(lambda pos: self._side_menu(self.bm_list, pos))
        self.res_list = QListWidget()
        self.res_list.itemClicked.connect(lambda it: self.pv.go_to(it.data(Qt.UserRole) - 1))
        for w, name in ((self.toc, tr("toc")), (self.pages_list, tr("pages")), (self.bm_list, tr("notes")),
                        (self.res_list, tr("find"))):
            self.tabs.addTab(w, name)
        self.side.setWidget(self.tabs)
        self.side.setMinimumWidth(290)
        self.addDockWidget(Qt.RightDockWidgetArea if self.layoutDirection() == Qt.RightToLeft
                           else Qt.LeftDockWidgetArea, self.side)

    def refresh_side(self):
        self.toc.clear()
        stack = {0: self.toc.invisibleRootItem()}
        for lvl, title, page in self.doc.get_toc():
            it = QTreeWidgetItem([title])
            it.setData(0, Qt.UserRole, max(page, 1))
            stack.get(lvl - 1, self.toc.invisibleRootItem()).addChild(it)
            stack[lvl] = it
        self.toc.expandToDepth(0)
        if self.pages_list.count() == 0:
            for i in range(1, min(self.doc.page_count, 5000) + 1):
                it = QListWidgetItem(f"{tr('page')} {i}")
                it.setData(Qt.UserRole, i)
                self.pages_list.addItem(it)
        self.bm_list.clear()
        for bm in self.svc.bookmarks(self.bid):
            it = QListWidgetItem(f"🔖 {tr('page')} {bm['page']}  {bm['label']}")
            it.setData(Qt.UserRole, (bm["page"], "bm", bm["id"]))
            self.bm_list.addItem(it)
        for n in self.svc.notes(self.bid):
            icon_ = "💬" if n["kind"] == "note" else "❝"
            it = QListWidgetItem(f"{icon_} {tr('page')} {n['page']}: {n['text'][:80]}")
            it.setData(Qt.UserRole, (n["page"], "note", n["id"]))
            self.bm_list.addItem(it)
        for h in self.svc.highlights(self.bid):
            it = QListWidgetItem(f"🖍 {tr('page')} {h['page']}: {(h['text'] or '')[:80]}")
            it.setData(Qt.UserRole, (h["page"], "hl", h["id"]))
            self.bm_list.addItem(it)

    def _side_menu(self, lst, pos):
        it = lst.itemAt(pos)
        if not it:
            return
        page, kind, rid = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction(tr("clear")).triggered.connect(lambda: self._delete_item(kind, rid))
        m.exec(lst.mapToGlobal(pos))

    def _delete_item(self, kind, rid):
        {"bm": self.svc.delete_bookmark, "note": self.svc.delete_note, "hl": self.svc.delete_highlight}[kind](rid)
        self.pv.invalidate_highlights()
        self.refresh_side()

    # --------------------------------------------------------------- actions
    def _page_changed(self, page, save=True):
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(page + 1)
        self.page_spin.blockSignals(False)
        self.prog.setValue(int(100 * (page + 1) / max(self.doc.page_count, 1)))
        self.statusBar().showMessage(f"{tr('page')} {page + 1} / {self.doc.page_count}  ·  "
                                     f"{int(100 * (page + 1) / self.doc.page_count)}%")
        if save:
            self._save_timer.start()

    def _save_progress(self):
        if self.doc:
            self.svc.save_progress(self.bid, self.pv.cur + 1, self.doc.page_count, self.pv.zoom, self.pv.mode)

    def add_bookmark(self):
        self.svc.add_bookmark(self.bid, self.pv.cur + 1, "")
        self.refresh_side()
        self.statusBar().showMessage(tr("bookmark") + " ✓", 2000)

    def _selection(self, page, rect, text):
        self._sel = (page, rect, text)

    def _menu(self, pos):
        m = QMenu(self)
        if self.pv.sel_text or self.pv.sel:
            m.addAction(tr("find") if False else "Copy").triggered.connect(
                lambda: QGuiApplication.clipboard().setText(self.pv.sel_text))
            m.addAction(tr("highlight")).triggered.connect(self.highlight_selection)
            m.addAction(tr("quote")).triggered.connect(lambda: self.save_quote())
            m.addAction(tr("add_note")).triggered.connect(self.note_selection)
        else:
            m.addAction(tr("bookmark")).triggered.connect(self.add_bookmark)
            m.addAction(tr("add_note")).triggered.connect(self.note_page)
        m.exec(self.pv.mapToGlobal(pos))

    def highlight_selection(self):
        if not getattr(self, "_sel", None):
            return
        page, rect, text = self._sel
        self.svc.add_highlight(self.bid, page + 1, tuple(rect), self.hl_color, text)
        self.pv.clear_selection()
        self.pv.invalidate_highlights()
        self.refresh_side()

    def save_quote(self):
        if getattr(self, "_sel", None) and self._sel[2]:
            self.svc.add_note(self.bid, self._sel[0] + 1, self._sel[2], "quote")
            self.refresh_side()

    def note_selection(self):
        text, ok = QInputDialog.getMultiLineText(self, tr("add_note"), tr("add_note"),
                                                 "")
        if ok and text.strip():
            self.svc.add_note(self.bid, self._sel[0] + 1, text.strip(), "note")
            self.refresh_side()

    def note_page(self):
        text, ok = QInputDialog.getMultiLineText(self, tr("add_note"), f"{tr('page')} {self.pv.cur + 1}", "")
        if ok and text.strip():
            self.svc.add_note(self.bid, self.pv.cur + 1, text.strip(), "note")
            self.refresh_side()

    def do_find(self):
        term = self.find_edit.text().strip()
        self.res_list.clear()
        if not term or not self.doc:
            self.pv.set_hits("", {})
            return
        hits, shown = {}, 0
        for i in range(self.doc.page_count):
            rects = self.doc.load_page(i).search_for(term)
            if rects:
                hits[i] = rects
                if shown < 500:
                    it = QListWidgetItem(f"{tr('page')} {i + 1}  ({len(rects)})")
                    it.setData(Qt.UserRole, i + 1)
                    self.res_list.addItem(it)
                    shown += 1
        self.pv.set_hits(term, hits)
        self.tabs.setCurrentWidget(self.res_list)
        self.side.setVisible(True)
        if hits:
            first = next((p for p in sorted(hits) if p >= self.pv.cur), min(hits))
            self.pv.go_to(first)

    def closeEvent(self, e):
        self._save_progress()
        if self.doc:
            self.doc.close()
        self.closed.emit(self.lib_id, self.bid)
        super().closeEvent(e)
