"""PDF Library Pro entry point."""
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from .core import i18n
from .core.config import APP_NAME, resource_path, setup_logging
from .libraries.manager import LibraryManager
from .ui.context import Context
from .ui.main_window import MainWindow
from .ui.theme import stylesheet


def load_font() -> str:
    family = "Segoe UI"
    for f in ("Vazirmatn-Regular.ttf", "Vazirmatn-Bold.ttf"):
        p = resource_path("fonts", f)
        if p.exists():
            fid = QFontDatabase.addApplicationFont(str(p))
            if fid >= 0:
                family = QFontDatabase.applicationFontFamilies(fid)[0]
    return family


def build_window(app, mgr, font):
    ctx = Context(mgr)
    app.setLayoutDirection(Qt.LeftToRight if i18n.lang() == "en" else Qt.RightToLeft)
    app.setStyleSheet(stylesheet(ctx.pal, font))
    win = MainWindow(ctx)
    return ctx, win


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    selftest = "--selftest" in argv
    if selftest:
        os.environ["PDFLP_HOME"] = tempfile.mkdtemp(prefix="pdflp_selftest_")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    log = setup_logging()
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    font = load_font()
    app.setFont(QFont(font, 10))
    mgr = LibraryManager()
    state = {}

    def show():
        ctx, win = build_window(app, mgr, font)
        old = state.get("win")
        state.update(ctx=ctx, win=win)
        win.restartRequested.connect(lambda: QTimer.singleShot(0, show))
        win.show()
        if old is not None:
            old.hide()
            old.deleteLater()

    show()
    if selftest:
        QTimer.singleShot(1500, app.quit)
        code = app.exec()
        print("SELFTEST OK" if code == 0 else "SELFTEST FAIL")
        return code
    code = app.exec()
    mgr.close_all()
    return code


if __name__ == "__main__":
    sys.exit(main())
