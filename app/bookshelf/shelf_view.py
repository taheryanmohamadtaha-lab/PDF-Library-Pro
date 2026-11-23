"""Painted 2.5D bookshelf: wood/modern styles, real covers, drag-to-reorder, persisted order."""
import random

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QAbstractScrollArea, QMenu

from ..core.i18n import tr
from ..ui.book_grid import cover_pixmap

BOOK_W, BOOK_H, GAP, PLANK, PAD = 112, 164, 26, 26, 36


def wood_tile(base: QColor, w=256, h=256) -> QPixmap:
    pm = QPixmap(w, h)
    pm.fill(base)
    p = QPainter(pm)
    rnd = random.Random(7)
    for _ in range(90):
        x = rnd.randint(0, w)
        c = QColor(base)
        c = c.darker(100 + rnd.randint(5, 45)) if rnd.random() < 0.6 else c.lighter(100 + rnd.randint(5, 25))
        c.setAlpha(rnd.randint(30, 90))
        p.setPen(QPen(c, rnd.choice((1, 1, 2, 3))))
        pts = [QPoint(x + int(3 * __import__("math").sin(y / 25 + x)), y) for y in range(0, h + 1, 16)]
        for a, b in zip(pts, pts[1:]):
            p.drawLine(a, b)
    p.end()
    return pm


class ShelfView(QAbstractScrollArea):
    openRequested = Signal(dict)
    removeRequested = Signal(dict)
    infoRequested = Signal(dict)
    orderChanged = Signal(list)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.books: list[dict] = []
        self.style_name, self.color = "wood", "#8a5a2b"
        self.filter = ""
        self.sel = -1
        self.hover = -1
        self.drag = None  # (index, QPoint offset, QPoint pos)
        self._press = None
        self._tile = None
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.verticalScrollBar().setSingleStep(40)

    def set_books(self, books, style="wood", color="#8a5a2b"):
        self.books = [dict(b) for b in books]
        self.style_name, self.color = style, color
        self._tile = None
        self._layout()
        self.viewport().update()

    def set_filter(self, text):
        self.filter = text.strip().lower()
        self.viewport().update()

    # --------------------------------------------------------------- layout
    def _cols(self):
        return max(1, (self.viewport().width() - 2 * PAD + GAP) // (BOOK_W + GAP))

    def _row_h(self):
        return BOOK_H + PLANK + 38

    def _layout(self):
        rows = max(3, -(-max(len(self.books), 1) // self._cols()) + 1)
        self.total_h = rows * self._row_h() + 2 * PAD
        vb = self.verticalScrollBar()
        vb.setRange(0, max(0, self.total_h - self.viewport().height()))
        vb.setPageStep(self.viewport().height())
        self.rows_count = rows

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout()

    def slot_rect(self, i):
        cols = self._cols()
        total_w = cols * BOOK_W + (cols - 1) * GAP
        x0 = (self.viewport().width() - total_w) // 2
        r, c = divmod(i, cols)
        x = x0 + c * (BOOK_W + GAP)
        y = PAD + r * self._row_h() + 38 - self.verticalScrollBar().value()
        return QRect(x, y, BOOK_W, BOOK_H)

    def index_at(self, pos):
        for i in range(len(self.books)):
            if self.slot_rect(i).adjusted(0, -8, 0, PLANK // 2).contains(pos):
                return i
        return -1

    # --------------------------------------------------------------- painting
    def _background(self, p: QPainter):
        vp = self.viewport().rect()
        if self.style_name == "wood":
            if self._tile is None:
                self._tile = wood_tile(QColor(self.color))
            p.drawTiledPixmap(vp, self._tile, QPoint(0, self.verticalScrollBar().value()))
            g = QLinearGradient(0, 0, vp.width(), 0)
            g.setColorAt(0, QColor(0, 0, 0, 130)); g.setColorAt(0.05, QColor(0, 0, 0, 0))
            g.setColorAt(0.95, QColor(0, 0, 0, 0)); g.setColorAt(1, QColor(0, 0, 0, 130))
            p.fillRect(vp, g)
        else:
            c = QColor(self.color).darker(300)
            p.fillRect(vp, c)
            p.fillRect(vp, QColor(255, 255, 255, 10))

    def paintEvent(self, e):
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        self._background(p)
        W = self.viewport().width()
        base = QColor(self.color)
        for r in range(self.rows_count):
            y = PAD + r * self._row_h() + 38 + BOOK_H - self.verticalScrollBar().value()
            if y < -PLANK or y - BOOK_H > self.viewport().height():
                continue
            plank = QRect(0, y, W, PLANK)
            g = QLinearGradient(0, y, 0, y + PLANK)
            if self.style_name == "wood":
                g.setColorAt(0, base.lighter(135)); g.setColorAt(0.25, base.lighter(112)); g.setColorAt(1, base.darker(160))
            else:
                g.setColorAt(0, QColor("#e9e9ee")); g.setColorAt(0.2, base.lighter(150)); g.setColorAt(1, base.darker(180))
            p.fillRect(plank, g)
            sh = QLinearGradient(0, y + PLANK, 0, y + PLANK + 22)
            sh.setColorAt(0, QColor(0, 0, 0, 120)); sh.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillRect(QRect(0, y + PLANK, W, 22), sh)
        for i, b in enumerate(self.books):
            if self.drag and self.drag[0] == i:
                continue
            self._draw_book(p, b, self.slot_rect(i), i)
        if not self.books:
            p.setPen(QColor(255, 255, 255, 190))
            p.drawText(self.viewport().rect(), Qt.AlignCenter, tr("no_books"))
        if self.drag:
            i, off, pos = self.drag
            r = QRect(pos - off, self.slot_rect(0).size())
            p.setOpacity(0.9)
            self._draw_book(p, self.books[i], r, i, lift=10)
            p.setOpacity(1)
            tgt = self._drop_index(pos)
            tr_ = self.slot_rect(min(tgt, max(len(self.books) - 1, 0)))
            p.setPen(QPen(QColor("#ffd43b"), 3))
            p.drawLine(tr_.left() - GAP // 2, tr_.top(), tr_.left() - GAP // 2, tr_.bottom())

    def _draw_book(self, p: QPainter, b: dict, r: QRect, i: int, lift=0):
        dim = self.filter and self.filter not in (b["title"] + " " + (b["author"] or "")).lower()
        if i == self.hover and not lift:
            lift = 6
        pm = cover_pixmap(self.ctx, b, BOOK_W * 2, BOOK_H * 2)
        w, h = pm.width() // 2, pm.height() // 2
        x = r.x() + (BOOK_W - w) // 2
        y = r.bottom() - h - lift
        # contact shadow
        sg = QRadialGradient(x + w / 2, r.bottom() + 6, w * 0.65)
        sg.setColorAt(0, QColor(0, 0, 0, 150)); sg.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen); p.setBrush(QBrush(sg))
        p.drawEllipse(QRectF(x - 6, r.bottom() - 2, w + 14, 16))
        # spine (3D edge) + page block
        spine = QRect(x - 6, y + 2, 7, h - 2)
        gsp = QLinearGradient(spine.left(), 0, spine.right(), 0)
        gsp.setColorAt(0, QColor(0, 0, 0, 200)); gsp.setColorAt(1, QColor(255, 255, 255, 60))
        p.setBrush(QColor(40, 40, 46)); p.drawRect(spine); p.setBrush(QBrush(gsp)); p.drawRect(spine)
        p.setOpacity(0.35 if dim else (p.opacity()))
        p.drawPixmap(QRect(x, y, w, h), pm)
        gl = QLinearGradient(x, y, x + w, y)
        gl.setColorAt(0, QColor(255, 255, 255, 45)); gl.setColorAt(0.08, QColor(0, 0, 0, 40)); gl.setColorAt(0.2, QColor(255, 255, 255, 0))
        p.fillRect(QRect(x, y, w, h), gl)
        if i == self.sel:
            p.setPen(QPen(QColor("#ffd43b"), 3)); p.setBrush(Qt.NoBrush)
            p.drawRect(QRect(x - 1, y - 1, w + 2, h + 2))
        if not dim:
            p.setOpacity(1)
        pct = int(b.get("percent") or 0) if isinstance(b, dict) else 0
        if pct:
            p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 140))
            p.drawRoundedRect(QRect(x + 4, y + h - 18, 34, 14), 6, 6)
            p.setPen(QColor("white")); p.drawText(QRect(x + 4, y + h - 18, 34, 14), Qt.AlignCenter, f"{pct}%")
        p.setOpacity(1)

    # ------------------------------------------------------------ interaction
    def _drop_index(self, pos):
        best, bd = len(self.books), 10 ** 9
        for i in range(len(self.books) + 1):
            r = self.slot_rect(min(i, len(self.books) - 1)) if self.books else QRect()
            x = r.left() if i < len(self.books) else r.right() + GAP
            d = abs(pos.x() - x) + 2 * abs(pos.y() - r.center().y()) // 3
            if d < bd:
                best, bd = i, d
        return best

    def mousePressEvent(self, e):
        i = self.index_at(e.position().toPoint())
        self.sel = i
        self._press = (i, e.position().toPoint()) if e.button() == Qt.LeftButton and i >= 0 else None
        self.viewport().update()

    def mouseMoveEvent(self, e):
        pos = e.position().toPoint()
        if self._press and (e.buttons() & Qt.LeftButton) and not self.drag:
            if (pos - self._press[1]).manhattanLength() > 10:
                i = self._press[0]
                self.drag = (i, self._press[1] - self.slot_rect(i).topLeft(), pos)
        if self.drag:
            self.drag = (self.drag[0], self.drag[1], pos)
        else:
            h = self.index_at(pos)
            if h != self.hover:
                self.hover = h
        self.viewport().update()

    def mouseReleaseEvent(self, e):
        if self.drag:
            i, off, pos = self.drag
            tgt = self._drop_index(pos)
            self.drag = None
            if tgt != i and tgt != i + 1:
                b = self.books.pop(i)
                self.books.insert(tgt - 1 if tgt > i else tgt, b)
                self.orderChanged.emit([x["id"] for x in self.books])
            self.viewport().update()
        self._press = None

    def mouseDoubleClickEvent(self, e):
        i = self.index_at(e.position().toPoint())
        if i >= 0:
            self.openRequested.emit(self.books[i])

    def leaveEvent(self, e):
        self.hover = -1
        self.viewport().update()

    def contextMenuEvent(self, e):
        i = self.index_at(e.pos())
        if i < 0:
            return
        self.sel = i
        b = self.books[i]
        m = QMenu(self)
        m.addAction(tr("open")).triggered.connect(lambda: self.openRequested.emit(b))
        m.addAction(tr("edit")).triggered.connect(lambda: self.infoRequested.emit(b))
        m.addAction(tr("clear")).triggered.connect(lambda: self.removeRequested.emit(b))
        m.exec(e.globalPos())
        self.viewport().update()

    def scrollContentsBy(self, dx, dy):
        self.viewport().update()
