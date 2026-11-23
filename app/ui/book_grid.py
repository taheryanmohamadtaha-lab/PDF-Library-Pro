"""Cover grid / list view modelled on the reference screenshots."""
from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap, QPixmapCache
from PySide6.QtWidgets import (QFileDialog, QListView, QMenu, QStyle, QStyledItemDelegate)

from ..core.i18n import tr
from .icons import pixmap


class BookModel(QAbstractListModel):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.rows: list = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = [dict(r) for r in rows]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        b = self.rows[index.row()]
        if role == Qt.UserRole:
            return b
        if role == Qt.DisplayRole:
            return b["title"]
        if role == Qt.ToolTipRole:
            return f"{b['title']}\n{b['author']}\n{b['pages']} {tr('pages')}"
        return None


def cover_pixmap(ctx, b: dict, w: int, h: int) -> QPixmap:
    key = f"cv{ctx.lib_id}-{b['id']}-{b.get('cover')}-{w}x{h}"
    pm = QPixmap()
    if QPixmapCache.find(key, pm):
        return pm
    src = QPixmap()
    cp = ctx.svc.cover_path(b)
    if cp:
        src.load(str(cp))
    if src.isNull():
        src = QPixmap(w, h)
        src.fill(QColor("#3a3a46"))
        p = QPainter(src)
        p.drawPixmap((w - 40) // 2, (h - 40) // 2, pixmap("file", "#9a9aa6", 40))
        p.end()
    pm = src.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    QPixmapCache.insert(key, pm)
    return pm


class BookDelegate(QStyledItemDelegate):
    CARD_W, CARD_H, COVER_H = 150, 262, 200

    def __init__(self, ctx, view):
        super().__init__(view)
        self.ctx = ctx
        self.view = view
        self.list_mode = False

    def sizeHint(self, option, index):
        if self.list_mode:
            return QSize(max(300, self.view.viewport().width() - 8), 78)
        return QSize(self.CARD_W, self.CARD_H)

    def paint(self, p: QPainter, opt, index):
        b = index.data(Qt.UserRole)
        pal = self.ctx.pal
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = opt.rect.adjusted(4, 4, -4, -4)
        sel = bool(opt.state & QStyle.State_Selected)
        hov = bool(opt.state & QStyle.State_MouseOver)
        if sel or hov:
            p.setPen(Qt.NoPen)
            c = QColor(pal.accent)
            c.setAlpha(110 if sel else 50)
            p.setBrush(c)
            p.drawRoundedRect(r, 10, 10)
        rtl = self.view.layoutDirection() == Qt.RightToLeft
        if self.list_mode:
            self._paint_list(p, r, b, pal, rtl)
        else:
            self._paint_card(p, r, b, pal)
        p.restore()

    def _paint_card(self, p, r, b, pal):
        cw, ch = r.width() - 16, self.COVER_H
        pm = cover_pixmap(self.ctx, b, cw * 2, ch * 2)
        ds = pm.size() / 2 if False else QSize(pm.width() // 2, pm.height() // 2)
        x = r.x() + (r.width() - ds.width()) // 2
        y = r.y() + 8 + (ch - ds.height())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawRoundedRect(QRect(x + 2, y + 3, ds.width(), ds.height()), 3, 3)
        p.drawPixmap(QRect(x, y, ds.width(), ds.height()), pm)
        p.setPen(QPen(QColor(255, 255, 255, 30)))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRect(x, y, ds.width(), ds.height()))
        # flags
        if b["favorite"]:
            p.drawPixmap(x + 4, y + 4, pixmap("heart", "#ef4444", 16))
        if b["missing"]:
            p.setBrush(QColor("#ef4444"))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRect(x + 4, y + ds.height() - 20, ds.width() - 8, 16), 4, 4)
            p.setPen(QColor("white"))
            p.setFont(QFont(p.font().family(), 8))
            p.drawText(QRect(x + 4, y + ds.height() - 20, ds.width() - 8, 16), Qt.AlignCenter, tr("missing_file"))
        if b["encrypted"]:
            p.drawPixmap(x + ds.width() - 20, y + 4, pixmap("lock", "#fbbf24", 16))
        ty = r.y() + 8 + ch + 6
        f = QFont(p.font().family(), 9)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(pal.text))
        fm = QFontMetrics(f)
        title = fm.elidedText(b["title"], Qt.ElideRight, r.width() - 10)
        p.drawText(QRect(r.x() + 5, ty, r.width() - 10, 16), Qt.AlignHCenter | Qt.AlignVCenter, title)
        f2 = QFont(p.font().family(), 8)
        p.setFont(f2)
        p.setPen(QColor(pal.muted))
        a = QFontMetrics(f2).elidedText(b["author"] or "—", Qt.ElideRight, r.width() - 10)
        p.drawText(QRect(r.x() + 5, ty + 17, r.width() - 10, 14), Qt.AlignHCenter | Qt.AlignVCenter, a)
        # progress pill like the reference
        pct = int(b["percent"] or 0)
        pill = QRect(r.x() + 8, ty + 36, r.width() - 16, 12)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal.border))
        p.drawRoundedRect(pill, 6, 6)
        if pct > 0:
            p.setBrush(QColor(pal.accent))
            p.drawRoundedRect(QRect(pill.x(), pill.y(), max(12, pill.width() * pct // 100), 12), 6, 6)
        p.setPen(QColor("white" if pct > 40 else pal.text))
        p.setFont(QFont(p.font().family(), 7))
        p.drawText(pill, Qt.AlignCenter, f"{pct}%")

    def _paint_list(self, p, r, b, pal, rtl):
        ch = r.height() - 8
        pm = cover_pixmap(self.ctx, b, 120, ch * 2)
        w, h = pm.width() // 2, pm.height() // 2
        x = r.right() - w - 8 if rtl else r.x() + 8
        p.drawPixmap(QRect(x, r.y() + 4, w, h), pm)
        tx = (r.x() + 120) if rtl else (r.x() + 8 + 60)
        tw = r.width() - 60 - 120 - 20
        f = QFont(p.font().family(), 10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(pal.text))
        al = (Qt.AlignRight if rtl else Qt.AlignLeft) | Qt.AlignVCenter
        title = QFontMetrics(f).elidedText(b["title"], Qt.ElideRight, tw)
        p.drawText(QRect(tx, r.y() + 6, tw, 20), al, title)
        p.setFont(QFont(p.font().family(), 9))
        p.setPen(QColor(pal.muted))
        info = " · ".join(x for x in (b["author"], b["category"], f"{b['pages']} {tr('pages')}") if x)
        p.drawText(QRect(tx, r.y() + 28, tw, 18), al, info)
        pct = int(b["percent"] or 0)
        bar = QRect(tx, r.y() + 52, min(220, tw), 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal.border))
        p.drawRoundedRect(bar, 4, 4)
        p.setBrush(QColor(pal.accent))
        p.drawRoundedRect(QRect(bar.x(), bar.y(), bar.width() * pct // 100, 8), 4, 4)
        p.setPen(QColor(pal.muted))
        p.drawText(QRect(bar.right() + 8 if not rtl else bar.x() - 50, bar.y() - 4, 44, 16), Qt.AlignVCenter, f"{pct}%")


class BookView(QListView):
    openRequested = Signal(dict)
    contextRequested = Signal(dict, QPoint)

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.model_ = BookModel(ctx)
        self.setModel(self.model_)
        self.delegate = BookDelegate(ctx, self)
        self.setItemDelegate(self.delegate)
        self.setMouseTracking(True)
        self.setSelectionMode(QListView.ExtendedSelection)
        self.setResizeMode(QListView.Adjust)
        self.setUniformItemSizes(True)
        self.setFrameShape(QListView.NoFrame)
        self.setStyleSheet("QListView{background:transparent;border:none;}")
        self.set_mode("grid")
        self.doubleClicked.connect(lambda i: self.openRequested.emit(i.data(Qt.UserRole)))

    def set_mode(self, mode: str):
        grid = mode == "grid"
        self.delegate.list_mode = not grid
        self.setViewMode(QListView.IconMode if grid else QListView.ListMode)
        self.setWrapping(grid)
        self.setFlow(QListView.LeftToRight if grid else QListView.TopToBottom)
        self.setSpacing(6 if grid else 2)
        self.setMovement(QListView.Static)
        self.model_.layoutChanged.emit()
        self.doItemsLayout()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.delegate.list_mode:
            self.doItemsLayout()

    def selected_books(self) -> list[dict]:
        return [i.data(Qt.UserRole) for i in self.selectedIndexes()]

    def contextMenuEvent(self, e):
        idx = self.indexAt(e.pos())
        if idx.isValid():
            if not self.selectionModel().isSelected(idx):
                self.setCurrentIndex(idx)
            self.contextRequested.emit(idx.data(Qt.UserRole), e.globalPos())
