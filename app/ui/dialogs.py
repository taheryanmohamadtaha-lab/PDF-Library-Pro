from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout)

from ..core.i18n import tr


class BookInfoDialog(QDialog):
    def __init__(self, ctx, book, parent=None):
        super().__init__(parent)
        self.ctx, self.bid = ctx, book["id"]
        self.setWindowTitle(book["title"])
        self.setMinimumWidth(480)
        svc = ctx.svc
        form = QFormLayout()
        self.f = {}
        for k in ("title", "author", "translator", "publisher", "category"):
            self.f[k] = QLineEdit(book[k] or "")
            form.addRow(tr(k), self.f[k])
        self.tags = QLineEdit("، ".join(svc.tags_of(book["id"])))
        form.addRow(tr("tags"), self.tags)
        self.desc = QPlainTextEdit(book["description"] or "")
        self.desc.setFixedHeight(90)
        form.addRow(tr("description"), self.desc)
        self.fav = QCheckBox(tr("favorite"))
        self.fav.setChecked(bool(book["favorite"]))
        form.addRow("", self.fav)
        info = QLabel(f"{book['file_name']}  ·  {book['pages']} {tr('pages')}  ·  {book['size'] // 1024} KB\n{book['path']}")
        info.setObjectName("muted")
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info.setWordWrap(True)
        cover = QPushButton(tr("set_cover"))
        cover.clicked.connect(self.pick_cover)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(info)
        lay.addWidget(cover)
        lay.addWidget(bb)

    def pick_cover(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("set_cover"), "", "Images (*.png *.jpg *.jpeg *.webp)")
        if f:
            self.ctx.svc.set_cover_from_image(self.bid, f)
            from PySide6.QtGui import QPixmapCache
            QPixmapCache.clear()
            self.ctx.booksChanged.emit()

    def save(self):
        tags = [t.strip() for t in self.tags.text().replace("،", ",").split(",")]
        self.ctx.svc.update_book(self.bid, tags=tags, favorite=int(self.fav.isChecked()),
                                 description=self.desc.toPlainText(),
                                 **{k: v.text().strip() for k, v in self.f.items() if k != "title" or v.text().strip()})
        self.ctx.booksChanged.emit()
        self.accept()


class PickLibraryDialog(QDialog):
    def __init__(self, ctx, exclude: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("move_to_lib"))
        self.lst = QListWidget()
        for l in ctx.mgr.list():
            if l["id"] != exclude:
                it = QListWidgetItem(l["name"])
                it.setData(Qt.UserRole, l["id"])
                self.lst.addItem(it)
        self.lst.setCurrentRow(0)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.lst)
        lay.addWidget(bb)

    def chosen(self):
        it = self.lst.currentItem()
        return it.data(Qt.UserRole) if it else None


class PickBooksDialog(QDialog):
    def __init__(self, books, parent=None, title=""):
        super().__init__(parent)
        self.setWindowTitle(title or tr("add_books"))
        self.resize(420, 480)
        self.lst = QListWidget()
        self.lst.setSelectionMode(QListWidget.ExtendedSelection)
        for b in books:
            it = QListWidgetItem(b["title"])
            it.setData(Qt.UserRole, b["id"])
            self.lst.addItem(it)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.lst)
        lay.addWidget(bb)

    def chosen(self):
        return [i.data(Qt.UserRole) for i in self.lst.selectedItems()]


def ask_color(parent, initial="#8b5cf6") -> str:
    c = QColorDialog.getColor(QColor(initial), parent)
    return c.name() if c.isValid() else ""


def confirm(parent, text, danger=False) -> bool:
    m = QMessageBox(parent)
    m.setIcon(QMessageBox.Warning if danger else QMessageBox.Question)
    m.setText(text)
    y = m.addButton(tr("yes"), QMessageBox.AcceptRole)
    m.addButton(tr("no"), QMessageBox.RejectRole)
    m.exec()
    return m.clickedButton() is y
