"""Main content pages: dashboard, libraries, books, shelf, groups, search, notes."""
import os
from pathlib import Path

from PySide6.QtCore import QStringListModel, Qt, QTimer
from PySide6.QtGui import QColor, QPixmapCache
from PySide6.QtWidgets import (QCheckBox, QComboBox, QCompleter, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                               QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget)

from ..bookshelf.shelf_view import ShelfView
from ..core.i18n import tr
from .book_grid import BookView, cover_pixmap
from .dialogs import (BookInfoDialog, PickBooksDialog, PickLibraryDialog, ask_color, confirm)
from .icons import icon, pixmap


def lbl(text, obj=None):
    l = QLabel(text)
    if obj:
        l.setObjectName(obj)
    return l


def btn(text, primary=False, ic=None, ctx=None):
    b = QPushButton(text)
    if primary:
        b.setObjectName("primary")
    if ic and ctx:
        b.setIcon(icon(ic, "#ffffff" if primary else ctx.pal.text, 18))
    return b


class BookActions:
    """Mixin with actions shared by grid, shelf and search."""

    def open_book(self, b, page=0):
        if b["missing"] or not Path(b["path"]).exists():
            self.ctx.svc.check_missing()
            self.relocate(b)
            return
        self.ctx.openBook.emit(self.ctx.lib_id, b["id"], page)

    def relocate(self, b):
        QMessageBox.information(self, tr("missing_file"), f"{tr('missing_file')}:\n{b['path']}")
        f, _ = QFileDialog.getOpenFileName(self, tr("relocate"), "", "PDF (*.pdf)")
        if f:
            if self.ctx.svc.relocate_book(b["id"], f):
                folder = str(Path(f).parent)
                n = self.ctx.svc.relocate_in_folder(folder)
                self.ctx.booksChanged.emit()
            else:
                QMessageBox.warning(self, tr("error"), "SHA-256 mismatch: this is a different file.")

    def book_menu(self, b, pos, extra=None):
        svc = self.ctx.svc
        sel = self.view.selected_books() if hasattr(self, "view") and hasattr(self.view, "selected_books") else [b]
        sel = sel or [b]
        m = QMenu(self)
        m.addAction(icon("bookopen", self.ctx.pal.text, 16), tr("open")).triggered.connect(lambda: self.open_book(b))
        m.addAction(icon("edit", self.ctx.pal.text, 16), tr("edit")).triggered.connect(
            lambda: BookInfoDialog(self.ctx, b, self).exec())
        m.addAction(icon("heart", self.ctx.pal.text, 16), tr("favorite")).triggered.connect(
            lambda: self._fav(sel))
        if self.ctx.svc.shelves():
            sub = m.addMenu(icon("shelf", self.ctx.pal.text, 16), tr("shelf"))
            for s in self.ctx.svc.shelves():
                sub.addAction(s["name"]).triggered.connect(lambda _=False, sid=s["id"]: self._to_shelf(sid, sel))
        if b["missing"]:
            m.addAction(tr("relocate")).triggered.connect(lambda: self.relocate(b))
        if len(self.ctx.mgr.list()) > 1:
            m.addAction(tr("move_to_lib")).triggered.connect(lambda: self._move(sel))
        m.addSeparator()
        m.addAction(tr("remove_from_lib")).triggered.connect(lambda: self._remove(sel, False))
        m.addAction(tr("delete_file")).triggered.connect(lambda: self._remove(sel, True))
        m.exec(pos)

    def _fav(self, sel):
        for b in sel:
            self.ctx.svc.update_book(b["id"], favorite=0 if b["favorite"] else 1)
        self.ctx.booksChanged.emit()

    def _to_shelf(self, sid, sel):
        for b in sel:
            self.ctx.svc.add_to_shelf(sid, b["id"])
        self.ctx.booksChanged.emit()

    def _move(self, sel):
        d = PickLibraryDialog(self.ctx, self.ctx.lib_id, self)
        if d.exec() and d.chosen():
            fails = 0
            for b in sel:
                ok, msg = self.ctx.mgr.move_book(b["id"], self.ctx.lib_id, d.chosen())
                fails += 0 if ok else 1
            if fails:
                QMessageBox.warning(self, tr("error"), f"{fails} ✗ (duplicate / error)")
            QPixmapCache.clear()
            self.ctx.booksChanged.emit()

    def _remove(self, sel, delete_file):
        if delete_file:
            names = "\n".join(b["path"] for b in sel[:5])
            if not confirm(self, f"{tr('delete_file')}\n\n{names}\n\n⚠ این عمل غیرقابل بازگشت است.", True):
                return
        elif len(sel) > 1 and not confirm(self, f"{tr('remove_from_lib')}: {len(sel)}"):
            return
        for b in sel:
            self.ctx.svc.remove_book(b["id"], delete_file=delete_file)
        QPixmapCache.clear()
        self.ctx.booksChanged.emit()


class Header(QWidget):
    def __init__(self, title="", sub=""):
        super().__init__()
        self.t = lbl(title, "h1")
        self.s = lbl(sub, "muted")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self.t)
        lay.addWidget(self.s)


# ============================================================ dashboard
class DashboardPage(QWidget, BookActions):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(24, 12, 24, 12)
        self.head = Header(tr("dashboard"))
        self.lay.addWidget(self.head)
        self.cards = QHBoxLayout()
        self.lay.addLayout(self.cards)
        self.lay.addWidget(lbl(tr("continue_reading"), "h2"))
        self.cont = BookView(ctx)
        self.cont.setFixedHeight(285)
        self.cont.setFlow(BookView.LeftToRight)
        self.cont.setWrapping(False)
        self.cont.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.lay.addWidget(self.cont)
        self.lay.addWidget(lbl(tr("recent"), "h2"))
        self.recent = BookView(ctx)
        self.recent.setFixedHeight(285)
        self.recent.setWrapping(False)
        self.recent.setFlow(BookView.LeftToRight)
        self.lay.addWidget(self.recent)
        self.lay.addStretch()
        for v in (self.cont, self.recent):
            v.openRequested.connect(self.open_book)
            v.contextRequested.connect(lambda b, pos, v=v: self._ctx(v, b, pos))

    def _ctx(self, v, b, pos):
        self.view = v
        self.book_menu(b, pos)

    def refresh(self):
        svc = self.ctx.svc
        st = svc.stats()
        self.head.t.setText(f"{tr('dashboard')} — {self.ctx.lib['name']}")
        self.head.s.setText(tr("you_have") % st["books"])
        while self.cards.count():
            it = self.cards.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for key, val, ic in (("all_books", st["books"], "books"), ("total_pages", f"{st['pages']:,}", "file"),
                             ("reading", st["reading"], "bookopen"), ("favorites", st["favorites"], "heart"),
                             ("notes", st["notes"], "note")):
            f = QFrame()
            f.setObjectName("statcard")
            l = QHBoxLayout(f)
            pm = QLabel()
            pm.setPixmap(pixmap(ic, self.ctx.pal.accent, 28))
            col = QVBoxLayout()
            col.addWidget(lbl(str(val), "h1"))
            col.addWidget(lbl(tr(key), "muted"))
            l.addWidget(pm)
            l.addLayout(col)
            self.cards.addWidget(f)
        self.cont.model_.set_rows(svc.books("p.percent>0 AND p.percent<100", order="p.updated_at DESC LIMIT 12"))
        self.recent.model_.set_rows(svc.books(order="b.added_at DESC, b.id DESC LIMIT 14"))


# ============================================================ books page
SORTS = [("sort_added", "b.added_at DESC, b.id DESC"), ("title", "b.title COLLATE NOCASE"),
         ("author", "b.author COLLATE NOCASE"), ("progress", "p.percent DESC"), ("pages", "b.pages DESC")]
SORT_FA = {"sort_added": "تاریخ افزودن", "title": "عنوان", "author": "نویسنده", "progress": "پیشرفت", "pages": "تعداد صفحه"}
SORT_EN = {"sort_added": "Date added", "title": "Title", "author": "Author", "progress": "Progress", "pages": "Pages"}


class BooksPage(QWidget, BookActions):
    def __init__(self, ctx, mode="all", importer=None):
        super().__init__()
        self.ctx, self.mode, self.importer = ctx, mode, importer
        self.facets = {"author": None, "category": None, "tag": None, "source_dir": None}
        self.title_key = {"all": "all_books", "recent": "recent", "reading": "reading", "favorites": "favorites"}[mode]
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 8, 8, 8)
        left = QVBoxLayout()
        top = QHBoxLayout()
        self.head = Header(tr(self.title_key))
        top.addWidget(self.head)
        top.addStretch()
        self.add_btn = btn(tr("add_books"), True, "plus", ctx)
        self.add_btn.clicked.connect(self._add_menu)
        top.addWidget(self.add_btn)
        left.addLayout(top)
        bar = QHBoxLayout()
        self.sort = QComboBox()
        self.sort.currentIndexChanged.connect(self.refresh)
        self.filter_btn = btn(tr("filters"))
        self.filter_btn.setCheckable(True)
        self.filter_btn.setChecked(True)
        self.filter_btn.toggled.connect(lambda c: self.panel.setVisible(c))
        self.fav_only = QCheckBox(tr("favorites"))
        self.fav_only.toggled.connect(self.refresh)
        self.miss_only = QCheckBox(tr("missing_file"))
        self.miss_only.toggled.connect(self.refresh)
        self.vg = btn("", ic="grid", ctx=ctx)
        self.vl = btn("", ic="list", ctx=ctx)
        self.vg.clicked.connect(lambda: self.set_view("grid"))
        self.vl.clicked.connect(lambda: self.set_view("list"))
        for w in (self.sort, self.filter_btn, self.fav_only, self.miss_only):
            bar.addWidget(w)
        bar.addStretch()
        bar.addWidget(self.vg)
        bar.addWidget(self.vl)
        left.addLayout(bar)
        self.view = BookView(ctx)
        self.view.openRequested.connect(self.open_book)
        self.view.contextRequested.connect(lambda b, pos: self.book_menu(b, pos))
        self.empty = lbl(tr("drop_hint"), "muted")
        self.empty.setAlignment(Qt.AlignCenter)
        left.addWidget(self.view, 1)
        left.addWidget(self.empty)
        root.addLayout(left, 1)
        # facet panel (Booklore-like right panel)
        self.panel = QFrame()
        self.panel.setObjectName("card")
        self.panel.setFixedWidth(210)
        pl = QVBoxLayout(self.panel)
        self.f_lists = {}
        for key, title in (("author", "authors"), ("category", "categories"), ("tag", "tags"), ("source_dir", "folders")):
            pl.addWidget(lbl(tr(title), "h2"))
            lw = QListWidget()
            lw.setMaximumHeight(130)
            lw.itemClicked.connect(lambda it, k=key: self._facet_clicked(k, it))
            pl.addWidget(lw)
            self.f_lists[key] = lw
        clear = btn(tr("clear"))
        clear.clicked.connect(self.clear_facets)
        pl.addWidget(clear)
        pl.addStretch()
        root.addWidget(self.panel)
        self.set_view(ctx.setting("view_mode", "grid"))
        self._fill_sort()

    def _fill_sort(self):
        names = SORT_EN if tr("grid") == "Grid" else SORT_FA
        self.sort.blockSignals(True)
        self.sort.clear()
        for k, _ in SORTS:
            self.sort.addItem(names[k])
        self.sort.blockSignals(False)

    def set_view(self, mode):
        self.view.set_mode(mode)
        self.ctx.mgr.central.set("view_mode", mode)

    def _add_menu(self):
        if self.importer:
            self.importer.show_add_menu(self.add_btn)

    def set_facet(self, kind, value):
        self.clear_facets(refresh=False)
        self.facets[kind] = value
        self.refresh()

    def clear_facets(self, refresh=True):
        self.facets = {k: None for k in self.facets}
        self.fav_only.setChecked(False)
        self.miss_only.setChecked(False)
        if refresh:
            self.refresh()

    def _facet_clicked(self, key, it):
        v = it.data(Qt.UserRole)
        self.facets[key] = None if self.facets[key] == v else v
        self.refresh()

    def retranslate(self):
        self._fill_sort()
        self.add_btn.setText(tr("add_books"))
        self.filter_btn.setText(tr("filters"))
        self.fav_only.setText(tr("favorites"))
        self.miss_only.setText(tr("missing_file"))
        self.empty.setText(tr("drop_hint"))

    def refresh(self):
        svc = self.ctx.svc
        where, args = [], []
        if self.mode == "recent":
            where.append("b.last_opened IS NOT NULL")
        elif self.mode == "reading":
            where.append("p.percent>0 AND p.percent<100")
        elif self.mode == "favorites" or self.fav_only.isChecked():
            where.append("b.favorite=1")
        if self.miss_only.isChecked():
            where.append("b.missing=1")
        for k in ("author", "category", "source_dir"):
            if self.facets[k]:
                where.append(f"b.{k}=?")
                args.append(self.facets[k])
        if self.facets["tag"]:
            where.append("b.id IN (SELECT bt.book_id FROM book_tags bt JOIN tags t ON t.id=bt.tag_id WHERE t.name=?)")
            args.append(self.facets["tag"])
        order = "b.last_opened DESC" if self.mode == "recent" and self.sort.currentIndex() == 0 \
            else SORTS[max(0, self.sort.currentIndex())][1]
        rows = svc.books(" AND ".join(where), args, order)
        self.view.model_.set_rows(rows)
        self.head.t.setText(tr(self.title_key))
        self.head.s.setText(tr("you_have") % len(rows))
        self.empty.setVisible(not rows)
        self.view.setVisible(bool(rows))
        for key in ("author", "category", "source_dir"):
            self._fill_list(key, svc.distinct(key))
        self._fill_list("tag", [(t, svc.db.one("SELECT COUNT(*) FROM book_tags bt JOIN tags t ON t.id=bt.tag_id "
                                               "WHERE t.name=?", (t,))[0]) for t in svc.all_tags()])

    def _fill_list(self, key, items):
        lw = self.f_lists[key]
        lw.blockSignals(True)
        lw.clear()
        for name, n in items:
            label = Path(name).name or name if key == "source_dir" else name
            it = QListWidgetItem(f"{label}  ({n})")
            it.setData(Qt.UserRole, name)
            it.setToolTip(name)
            lw.addItem(it)
            if self.facets[key] == name:
                it.setSelected(True)
        lw.blockSignals(False)


# ============================================================ shelf page
class ShelfPage(QWidget, BookActions):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 8, 24, 8)
        self.head = Header(tr("shelf"))
        lay.addWidget(self.head)
        bar = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setMinimumWidth(180)
        self.combo.currentIndexChanged.connect(self.load_shelf)
        self.b_new = btn(tr("new_shelf"), True, "plus", ctx)
        self.b_new.clicked.connect(self.new_shelf)
        self.b_ren = btn(tr("rename"))
        self.b_ren.clicked.connect(self.rename)
        self.b_del = btn(tr("delete_lib"))
        self.b_del.clicked.connect(self.delete)
        self.b_add = btn(tr("add_books"), ic="books", ctx=ctx)
        self.b_add.clicked.connect(self.add_books)
        self.style = QComboBox()
        self.style.addItems([tr("wood"), tr("modern")])
        self.style.currentIndexChanged.connect(self.change_style)
        self.b_col = btn(tr("color"))
        self.b_col.clicked.connect(self.change_color)
        self.b_auto = btn(tr("categories"))
        self.b_auto.clicked.connect(self.auto_by_category)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("find"))
        self.search.textChanged.connect(lambda t: self.shelf.set_filter(t))
        self.b_alt = btn(tr("grid"), ic="grid", ctx=ctx)
        self.b_alt.setCheckable(True)
        self.b_alt.toggled.connect(self.toggle_alt)
        for w in (self.combo, self.b_new, self.b_ren, self.b_del, self.b_add, self.style, self.b_col, self.b_auto):
            bar.addWidget(w)
        bar.addStretch()
        bar.addWidget(self.search)
        bar.addWidget(self.b_alt)
        lay.addLayout(bar)
        self.shelf = ShelfView(ctx)
        self.shelf.openRequested.connect(self.open_book)
        self.shelf.infoRequested.connect(lambda b: BookInfoDialog(self.ctx, b, self).exec())
        self.shelf.removeRequested.connect(self.remove_from_shelf)
        self.shelf.orderChanged.connect(self.save_order)
        self.alt = BookView(ctx)
        self.alt.openRequested.connect(self.open_book)
        self.alt.contextRequested.connect(lambda b, pos: self.book_menu(b, pos))
        self.alt.hide()
        lay.addWidget(self.shelf, 1)
        lay.addWidget(self.alt, 1)
        self.count = lbl("", "muted")
        lay.addWidget(self.count)

    def sid(self):
        return self.combo.currentData()

    def refresh(self):
        cur = self.sid()
        self.combo.blockSignals(True)
        self.combo.clear()
        for s in self.ctx.svc.shelves():
            self.combo.addItem(s["name"], s["id"])
        if cur is not None:
            i = self.combo.findData(cur)
            self.combo.setCurrentIndex(max(i, 0))
        self.combo.blockSignals(False)
        self.load_shelf()

    def load_shelf(self):
        sid = self.sid()
        has = sid is not None
        for w in (self.b_ren, self.b_del, self.b_add, self.style, self.b_col):
            w.setEnabled(has)
        if not has:
            self.shelf.set_books([])
            self.count.setText(tr("no_books"))
            return
        s = next(x for x in self.ctx.svc.shelves() if x["id"] == sid)
        rows = self.ctx.svc.shelf_books(sid)
        prog = {r["book_id"]: r["percent"] for r in self.ctx.svc.db.q("SELECT book_id,percent FROM reading_progress")}
        books = [dict(r, percent=prog.get(r["id"], 0)) for r in rows]
        self.style.blockSignals(True)
        self.style.setCurrentIndex(0 if s["style"] == "wood" else 1)
        self.style.blockSignals(False)
        self.shelf.set_books(books, s["style"], s["color"])
        self.alt.model_.set_rows([dict(b) for b in self.ctx.svc.books("b.id IN (%s)" % ",".join(
            str(b["id"]) for b in books) if books else "0")]) if self.b_alt.isChecked() else None
        self.count.setText(tr("books_count") % len(books))
        self.head.s.setText(tr("books_count") % len(books))

    def new_shelf(self):
        name, ok = QInputDialog.getText(self, tr("new_shelf"), tr("shelf_name"))
        if ok and name.strip():
            sid = self.ctx.svc.add_shelf(name.strip())
            self.refresh()
            self.combo.setCurrentIndex(self.combo.findData(sid))

    def rename(self):
        name, ok = QInputDialog.getText(self, tr("rename"), tr("shelf_name"), text=self.combo.currentText())
        if ok and name.strip():
            self.ctx.svc.update_shelf(self.sid(), name=name.strip())
            self.refresh()

    def delete(self):
        if confirm(self, tr("delete_lib") + f": {self.combo.currentText()}?"):
            self.ctx.svc.delete_shelf(self.sid())
            self.refresh()

    def add_books(self):
        have = {b["id"] for b in self.ctx.svc.shelf_books(self.sid())}
        books = [b for b in self.ctx.svc.books() if b["id"] not in have]
        d = PickBooksDialog(books, self, tr("add_books"))
        if d.exec():
            for bid in d.chosen():
                self.ctx.svc.add_to_shelf(self.sid(), bid)
            self.load_shelf()

    def change_style(self, i):
        self.ctx.svc.update_shelf(self.sid(), style="wood" if i == 0 else "modern")
        self.load_shelf()

    def change_color(self):
        c = ask_color(self, "#8a5a2b")
        if c:
            self.ctx.svc.update_shelf(self.sid(), color=c)
            self.load_shelf()

    def auto_by_category(self):
        svc = self.ctx.svc
        names = {s["name"]: s["id"] for s in svc.shelves()}
        for cat, _n in svc.distinct("category"):
            sid = names.get(cat) or svc.add_shelf(cat)
            for b in svc.books("b.category=?", (cat,)):
                svc.add_to_shelf(sid, b["id"])
        self.refresh()

    def toggle_alt(self, on):
        self.shelf.setVisible(not on)
        self.alt.setVisible(on)
        self.load_shelf()

    def remove_from_shelf(self, b):
        self.ctx.svc.remove_from_shelf(self.sid(), b["id"])
        self.load_shelf()

    def save_order(self, ids):
        self.ctx.svc.set_shelf_order(self.sid(), ids)

    def retranslate(self):
        self.head.t.setText(tr("shelf"))
        self.b_new.setText(tr("new_shelf"))
        self.b_ren.setText(tr("rename"))
        self.b_del.setText(tr("delete_lib"))
        self.b_add.setText(tr("add_books"))
        self.b_col.setText(tr("color"))
        self.b_auto.setText(tr("categories"))
        self.search.setPlaceholderText(tr("find"))
        self.b_alt.setText(tr("grid"))
        self.style.blockSignals(True)
        self.style.clear()
        self.style.addItems([tr("wood"), tr("modern")])
        self.style.blockSignals(False)


# ============================================================ groups
class GroupPage(QWidget):
    """Authors / categories / folders -> click opens filtered books."""

    def __init__(self, ctx, kind, title_key, on_pick):
        super().__init__()
        self.ctx, self.kind, self.title_key, self.on_pick = ctx, kind, title_key, on_pick
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 8, 24, 8)
        self.head = Header(tr(title_key))
        lay.addWidget(self.head)
        self.lst = QListWidget()
        self.lst.setViewMode(QListWidget.IconMode)
        self.lst.setResizeMode(QListWidget.Adjust)
        self.lst.setSpacing(8)
        self.lst.setMovement(QListWidget.Static)
        self.lst.itemActivated.connect(lambda it: on_pick(kind, it.data(Qt.UserRole)))
        self.lst.itemClicked.connect(lambda it: on_pick(kind, it.data(Qt.UserRole)))
        lay.addWidget(self.lst)

    def refresh(self):
        self.head.t.setText(tr(self.title_key))
        self.lst.clear()
        ic = {"author": "users", "category": "tag", "source_dir": "folder"}[self.kind]
        for name, n in self.ctx.svc.distinct(self.kind):
            label = Path(name).name or name if self.kind == "source_dir" else name
            it = QListWidgetItem(icon(ic, self.ctx.pal.accent, 40), f"{label}\n{tr('books_count') % n}")
            it.setData(Qt.UserRole, name)
            it.setToolTip(name)
            it.setSizeHint(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(170, 100))
            it.setTextAlignment(Qt.AlignCenter)
            self.lst.addItem(it)


# ============================================================ libraries
ICONS = ["library", "books", "bookopen", "folder", "heart", "star", "note", "users", "tag", "home"]


class LibrariesPage(QWidget):
    def __init__(self, ctx, switch_fn, backup_fn):
        super().__init__()
        self.ctx, self.switch, self.backup_fn = ctx, switch_fn, backup_fn
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 8, 24, 8)
        top = QHBoxLayout()
        self.head = Header(tr("libraries"))
        top.addWidget(self.head)
        top.addStretch()
        self.add = btn(tr("new_library"), True, "plus", ctx)
        self.add.clicked.connect(self.new_library)
        top.addWidget(self.add)
        lay.addLayout(top)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        self.host = QWidget()
        self.grid = QGridLayout(self.host)
        self.grid.setAlignment(Qt.AlignTop)
        sc.setWidget(self.host)
        lay.addWidget(sc)

    def refresh(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, l in enumerate(self.ctx.mgr.list()):
            self.grid.addWidget(self._card(l), i // 3, i % 3)

    def _card(self, l):
        c = QFrame()
        c.setObjectName("card")
        c.setMinimumWidth(260)
        v = QVBoxLayout(c)
        row = QHBoxLayout()
        ic = QLabel()
        ic.setFixedSize(48, 48)
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet(f"background:{l['color']};border-radius:24px;")
        ic.setPixmap(pixmap(l["icon"], "#ffffff", 26))
        row.addWidget(ic)
        col = QVBoxLayout()
        name = lbl(l["name"] + ("  ★" if l["is_default"] else "") + ("  🔒" if l["pw_hash"] else ""), "h2")
        st = self.ctx.mgr.stats(l["id"])
        col.addWidget(name)
        col.addWidget(lbl(f"{tr('books_count') % st['books']} · {st['pages']:,} {tr('pages')} · {st['notes']} {tr('notes')}", "muted"))
        row.addLayout(col, 1)
        v.addLayout(row)
        p = lbl(l["path"], "muted")
        p.setWordWrap(True)
        v.addWidget(p)
        cur = l["id"] == self.ctx.lib_id
        ob = btn("✓ " + tr("open") if cur else tr("open"), not cur)
        ob.clicked.connect(lambda _=False, i=l["id"]: self.switch(i))
        more = btn("⋯")
        m = QMenu(more)
        m.addAction(tr("rename")).triggered.connect(lambda _=False, i=l["id"]: self.rename(i))
        m.addAction(tr("color")).triggered.connect(lambda _=False, i=l["id"]: self.recolor(i))
        m.addAction("Icon…").triggered.connect(lambda _=False, i=l["id"]: self.pick_icon(i))
        m.addAction(tr("make_default")).triggered.connect(lambda _=False, i=l["id"]: self._default(i))
        m.addAction(tr("lock")).triggered.connect(lambda _=False, i=l["id"]: self.set_pw(i))
        m.addAction(tr("backup_now")).triggered.connect(lambda _=False, i=l["id"]: self.backup_fn(i))
        m.addSeparator()
        m.addAction(tr("delete_lib")).triggered.connect(lambda _=False, i=l["id"]: self.delete(i))
        more.setMenu(m)
        r2 = QHBoxLayout()
        r2.addWidget(ob, 1)
        r2.addWidget(more)
        v.addLayout(r2)
        return c

    def new_library(self):
        name, ok = QInputDialog.getText(self, tr("new_library"), tr("lib_name"))
        if not ok or not name.strip():
            return
        path = ""
        if confirm(self, tr("location") + "?\n(" + tr("no") + " = default)"):
            path = QFileDialog.getExistingDirectory(self, tr("location"))
        col = ask_color(self, "#7c5cff") or "#7c5cff"
        self.ctx.mgr.create(name.strip(), col, "library", path)
        self.refresh()

    def rename(self, i):
        l = self.ctx.mgr.get(i)
        name, ok = QInputDialog.getText(self, tr("rename"), tr("lib_name"), text=l["name"])
        if ok and name.strip():
            self.ctx.mgr.update(i, name=name.strip())
            self.ctx.libraryChanged.emit()

    def recolor(self, i):
        c = ask_color(self, self.ctx.mgr.get(i)["color"])
        if c:
            self.ctx.mgr.update(i, color=c)
            self.ctx.libraryChanged.emit()

    def pick_icon(self, i):
        v, ok = QInputDialog.getItem(self, "Icon", "Icon", ICONS, 0, False)
        if ok:
            self.ctx.mgr.update(i, icon=v)
            self.ctx.libraryChanged.emit()

    def _default(self, i):
        self.ctx.mgr.set_default(i)
        self.refresh()

    def set_pw(self, i):
        from PySide6.QtWidgets import QLineEdit as LE
        pw, ok = QInputDialog.getText(self, tr("lock"), tr("unlock") + " (خالی = بدون قفل)", LE.Password)
        if ok:
            self.ctx.mgr.central.set_password(i, pw)
            self.refresh()

    def delete(self, i):
        l = self.ctx.mgr.get(i)
        if len(self.ctx.mgr.list()) <= 1:
            QMessageBox.information(self, tr("error"), "حداقل یک کتابخانه باید باقی بماند.")
            return
        if confirm(self, f"{tr('delete_lib')}: «{l['name']}»؟\nفایل‌های PDF اصلی شما حذف نمی‌شوند؛ فقط اطلاعات "
                         "کتابخانه و نسخه‌های آرشیو داخلی پاک می‌شوند.", True):
            if i == self.ctx.lib_id:
                self.switch(self.ctx.mgr.default_id() if self.ctx.mgr.default_id() != i else
                            next(x["id"] for x in self.ctx.mgr.list() if x["id"] != i))
            self.ctx.mgr.delete(i)
            self.refresh()
            self.ctx.libraryChanged.emit()


# ============================================================ search
class SearchPage(QWidget, BookActions):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 8, 24, 8)
        self.head = Header(tr("find"))
        lay.addWidget(self.head)
        bar = QHBoxLayout()
        self.cat = QComboBox()
        self.auth = QComboBox()
        self.scope = QCheckBox(tr("libraries"))
        for w in (self.cat, self.auth, self.scope):
            bar.addWidget(w)
        bar.addStretch()
        lay.addLayout(bar)
        self.lst = QListWidget()
        self.lst.setIconSize(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(40, 56))
        self.lst.itemActivated.connect(self._open)
        self.lst.itemDoubleClicked.connect(self._open)
        lay.addWidget(self.lst)
        self.query = ""
        for w in (self.cat, self.auth):
            w.currentIndexChanged.connect(lambda: self.run(self.query))
        self.scope.toggled.connect(lambda: self.run(self.query))

    def prepare(self):
        for combo, key in ((self.cat, "category"), (self.auth, "author")):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(tr("all") + " — " + tr("categories" if key == "category" else "authors"), "")
            for n, c in self.ctx.svc.distinct(key):
                combo.addItem(f"{n} ({c})", n)
            combo.blockSignals(False)

    def run(self, text):
        self.query = text
        self.lst.clear()
        if not text.strip():
            return
        libs = self.ctx.mgr.list() if self.scope.isChecked() else [self.ctx.lib]
        cat, au = self.cat.currentData(), self.auth.currentData()
        total = 0
        for l in libs:
            svc = self.ctx.mgr.service(l["id"])
            res = svc.search(text)
            ok = lambda b: b and (not cat or b["category"] == cat) and (not au or b["author"] == au)
            tag = f"[{l['name']}] " if len(libs) > 1 else ""
            for b in res["books"]:
                if ok(b):
                    it = QListWidgetItem(f"{tag}{b['title']}\n{b['author']}")
                    cp = svc.cover_path(b)
                    if cp:
                        it.setIcon(icon_from(cp))
                    it.setData(Qt.UserRole, (l["id"], b["id"], 0))
                    self.lst.addItem(it)
                    total += 1
            for h in res["pages"]:
                b = svc.book(h["book_id"])
                if ok(b):
                    it = QListWidgetItem(f"{tag}{b['title']} — {tr('page')} {h['page']}\n{h['snippet']}")
                    it.setData(Qt.UserRole, (l["id"], b["id"], h["page"]))
                    self.lst.addItem(it)
                    total += 1
            for n in res["notes"]:
                b = svc.book(n["book_id"])
                if ok(b):
                    it = QListWidgetItem(f"📝 {tag}{b['title']} — {tr('page')} {n['page']}\n{n['text'][:120]}")
                    it.setData(Qt.UserRole, (l["id"], b["id"], n["page"]))
                    self.lst.addItem(it)
                    total += 1
        self.head.s.setText(f"{total} ✓  «{text}»")

    def _open(self, it):
        lib_id, bid, page = it.data(Qt.UserRole)
        self.ctx.openBook.emit(lib_id, bid, page)


def icon_from(path):
    from PySide6.QtGui import QIcon, QPixmap
    return QIcon(QPixmap(str(path)))


# ============================================================ notes
class NotesPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 8, 24, 8)
        self.head = Header(tr("notes"))
        lay.addWidget(self.head)
        bar = QHBoxLayout()
        self.q = QLineEdit()
        self.q.setPlaceholderText(tr("find"))
        self.q.textChanged.connect(lambda: self.refresh())
        self.kind = QComboBox()
        for k in ("all", "note", "quote", "bookmark", "highlight"):
            self.kind.addItem(k if k != "all" else tr("all"), k)
        self.kind.currentIndexChanged.connect(lambda: self.refresh())
        self.exp = btn(tr("export"), ic="backup", ctx=ctx)
        self.exp.clicked.connect(self.export)
        bar.addWidget(self.q, 1)
        bar.addWidget(self.kind)
        bar.addWidget(self.exp)
        lay.addLayout(bar)
        self.lst = QListWidget()
        self.lst.itemDoubleClicked.connect(self._open)
        self.lst.setContextMenuPolicy(Qt.CustomContextMenu)
        self.lst.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.lst)

    def refresh(self):
        svc = self.ctx.svc
        self.lst.clear()
        kind, q = self.kind.currentData(), self.q.text().strip()
        items = []
        if q:
            ids = {n["id"] for n in svc.search(q)["notes"]}
        for n in svc.notes():
            if q and n["id"] not in ids:
                continue
            if kind in ("all", n["kind"]):
                items.append((n["book_id"], n["page"], f"{'💬' if n['kind'] == 'note' else '❝'} {n['title']} — {tr('page')} {n['page']}\n{n['text']}", ("note", n["id"])))
        if kind in ("all", "bookmark") and not q:
            for r in svc.db.q("SELECT bm.*, b.title FROM bookmarks bm JOIN books b ON b.id=bm.book_id ORDER BY bm.created_at DESC"):
                items.append((r["book_id"], r["page"], f"🔖 {r['title']} — {tr('page')} {r['page']}\n{r['label']}", ("bm", r["id"])))
        if kind in ("all", "highlight"):
            for r in svc.db.q("SELECT h.*, b.title FROM highlights h JOIN books b ON b.id=h.book_id ORDER BY h.created_at DESC"):
                if q and q.lower() not in (r["text"] or "").lower():
                    continue
                items.append((r["book_id"], r["page"], f"🖍 {r['title']} — {tr('page')} {r['page']}\n{r['text'] or ''}", ("hl", r["id"])))
        for bid, page, text, ref in items:
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, (bid, page, ref))
            self.lst.addItem(it)
        self.head.s.setText(str(len(items)))

    def _open(self, it):
        bid, page, _ = it.data(Qt.UserRole)
        self.ctx.openBook.emit(self.ctx.lib_id, bid, page)

    def _menu(self, pos):
        it = self.lst.itemAt(pos)
        if not it:
            return
        bid, page, (kind, rid) = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction(tr("clear")).triggered.connect(lambda: self._delete(kind, rid))
        m.exec(self.lst.mapToGlobal(pos))

    def _delete(self, kind, rid):
        s = self.ctx.svc
        {"note": s.delete_note, "bm": s.delete_bookmark, "hl": s.delete_highlight}[kind](rid)
        self.refresh()

    def export(self):
        it = self.lst.currentItem()
        books = {it.data(Qt.UserRole)[0]} if it else {r["book_id"] for r in self.ctx.svc.db.q("SELECT DISTINCT book_id FROM notes")}
        if not books:
            return
        folder = QFileDialog.getExistingDirectory(self, tr("export"))
        if folder:
            for bid in books:
                b = self.ctx.svc.book(bid)
                safe = "".join(c for c in b["title"] if c.isalnum() or c in " _-")[:60] or str(bid)
                self.ctx.svc.export_notes(bid, Path(folder) / f"{safe}.md")
            self.ctx.status.emit(f"{tr('done')} → {folder}")
