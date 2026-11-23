"""Shared application context (current library, theme, signals)."""
from PySide6.QtCore import QObject, Signal

from ..core import i18n
from ..libraries.manager import LibraryManager
from .theme import palette


class Context(QObject):
    libraryChanged = Signal()
    booksChanged = Signal()
    themeChanged = Signal()
    openBook = Signal(int, int, int)  # lib_id, book_id, page (0 = resume)
    status = Signal(str)

    def __init__(self, mgr: LibraryManager):
        super().__init__()
        self.mgr = mgr
        self.lib_id = mgr.default_id()
        i18n.set_lang(mgr.central.get("lang", "fa"))

    # ------------------------------------------------------------------ props
    @property
    def svc(self):
        return self.mgr.service(self.lib_id)

    @property
    def lib(self):
        return self.mgr.get(self.lib_id)

    @property
    def pal(self):
        return palette(self.mgr.central.get("theme", "dark") == "dark", self.mgr.central.get("accent", "purple"))

    def set_library(self, lib_id: int):
        self.lib_id = lib_id
        self.libraryChanged.emit()

    def setting(self, key, default=None):
        return self.mgr.central.get(key, default)
