"""Main window: collapsible sidebar, top bar with global search, stacked pages, import, backup, readers."""
import logging
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QSize, QStringListModel, Qt, QTimer, Signal
from PySide6.QtGui import QPixmapCache
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QCompleter, QFileDialog, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from ..backup import backup as bk
from ..core import i18n
from ..core.config import APP_NAME
from ..core.i18n import tr
from ..ocr import ocr as ocrmod
from .context import Context
from .icons import icon, pixmap
from .pages_library import (BooksPage, DashboardPage, GroupPage, LibrariesPage, NotesPage, SearchPage, ShelfPage)
from .pages_tools import AssistantPage, BackupPage, SettingsPage
from .reader import ReaderWindow
from .workers import Task

log = logging.getLogger("pdflp.main")

NAV = [("dashboard", "home"), ("libraries", "library"), ("all_books", "books"), ("shelf", "shelf"),
       ("recent", "clock"), ("reading", "bookopen"), ("favorites", "heart"), ("categories", "tag"),
       ("authors", "users"), ("folders", "folder"), ("notes", "note"), ("assistant", "sparkles"),
       ("backup", "backup"), ("settings", "settings")]


class Importer:
    def __init__(self, win):
        self.win = win
        self.ctx = win.ctx
        self.tasks = []

    def show_add_menu(self, anchor):
        m = QMenu(self.win)
        m.addAction(icon("file", self.ctx.pal.text, 16), tr("add_books")).triggered.connect(self.add_files)
        m.addAction(icon("folder", self.ctx.pal.text, 16), tr("add_folder")).triggered.connect(self.add_folder)
        m.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self.win, tr("add_books"), "", "PDF (*.pdf)")
        if files:
            self.import_paths(files)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self.win, tr("add_folder"))
        if d:
            self.import_paths([d])

    def import_paths(self, paths):
        svc, lib_id = self.ctx.svc, self.ctx.lib_id
        mode = self.ctx.setting("copy_mode", "link")

        def work(progress, cancelled):
            files = []
            for p in map(Path, paths):
                if p.is_dir():
                    files += [(f, str(p)) for f in sorted(p.rglob("*")) if f.suffix.lower() == ".pdf"]
                elif p.suffix.lower() == ".pdf":
                    files.append((p, str(p.parent)))
            res = {"added": [], "dup": 0, "err": []}
            for i, (f, src) in enumerate(files):
                if cancelled():
                    break
                st, val = svc.add_pdf(f, mode, src)
                if st == "added":
                    res["added"].append(val)
                elif st == "duplicate":
                    res["dup"] += 1
                else:
                    res["err"].append(f"{f.name}: {val}")
                progress(i + 1, len(files), f.name)
            return res

        t = Task(work, self.win)
        self.tasks.append(t)
        self.win.show_progress(tr("add_books"), t)
        t.done.connect(lambda r: self._imported(r, lib_id, t))
        t.failed.connect(lambda m: self.win.hide_progress(f"{tr('error')}: {m}"))
        t.start()

    def _imported(self, res, lib_id, t):
        self.win.hide_progress(f"{tr('added_n') % len(res['added'])} · {tr('dups_n') % res['dup']} · "
                               f"{tr('errors_n') % len(res['err'])}")
        self.ctx.booksChanged.emit()
        if res["err"]:
            QMessageBox.warning(self.win, tr("error"), "\n".join(res["err"][:15]))
        if res["added"]:
            self.index(lib_id, res["added"])

    def index(self, lib_id, ids):
        svc = self.ctx.mgr.service(lib_id)

        def work(progress, cancelled):
            for k, bid in enumerate(ids):
                if cancelled():
                    break
                svc.index_book(bid, progress=lambda a, b, bid=bid: progress(k * 1000 + a * 1000 // max(b, 1),
                                                                            len(ids) * 1000,
                                                                            svc.book(bid)["title"]), cancel=cancelled)
            return ids

        t = Task(work, self.win)
        self.tasks.append(t)
        self.win.show_progress(tr("indexing"), t)
        t.done.connect(lambda _: (self.win.hide_progress(tr("done")), self.ctx.booksChanged.emit()))
        t.failed.connect(lambda m: self.win.hide_progress(f"{tr('error')}: {m}"))
        t.start()

    def ocr_missing(self):
        svc = self.ctx.svc
        if not ocrmod.find_tesseract():
            QMessageBox.information(self.win, "OCR", tr("ocr_missing"))
            return
        todo = [b["id"] for b in svc.db.q("SELECT DISTINCT book_id AS id FROM file_index WHERE has_text=0")]
        langs = self.ctx.setting("ocr_langs", "fas+eng")

        def work(progress, cancelled):
            done = 0
            for k, bid in enumerate(todo):
                n, msg = ocrmod.ocr_pages(svc, bid, langs=langs, cancel=cancelled,
                                          progress=lambda a, b, k=k: progress(k * 1000 + a * 1000 // max(b, 1),
                                                                              len(todo) * 1000, svc.book(bid)["title"]))
                done += n
            return done

        t = Task(work, self.win)
        self.tasks.append(t)
        self.win.show_progress("OCR", t)
        t.done.connect(lambda n: self.win.hide_progress(f"OCR: {n} {tr('pages')}"))
        t.failed.connect(lambda m: self.win.hide_progress(m))
        t.start()


class MainWindow(QMainWindow):
    restartRequested = Signal()

    def __init__(self, ctx: Context):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 860)
        self.setAcceptDrops(True)
        self.readers: dict = {}
        self.unlocked: set = set()
        self.importer = Importer(self)
        pal = ctx.pal
        root = QWidget()
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        # ---------------- sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        sv = QVBoxLayout(self.sidebar)
        sv.setContentsMargins(8, 10, 8, 10)
        sv.setSpacing(2)
        self.logo = QLabel()
        self.logo.setPixmap(pixmap("books", pal.accent, 30))
        self.title = QLabel(tr("app"))
        self.title.setObjectName("h2")
        top = QHBoxLayout()
        top.addWidget(self.logo)
        top.addWidget(self.title, 1)
        sv.addLayout(top)
        sv.addSpacing(8)
        self.group = QButtonGroup(self)
        self.navs = {}
        for i, (key, ic) in enumerate(NAV):
            b = QToolButton()
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setIcon(icon(ic, pal.text, 20))
            b.setIconSize(QSize(20, 20))
            b.setText("  " + tr(key))
            b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.setSizePolicy(b.sizePolicy().horizontalPolicy(), b.sizePolicy().verticalPolicy())
            b.setMinimumWidth(190)
            b.clicked.connect(lambda _=False, i=i: self.stack.setCurrentIndex(i))
            self.group.addButton(b, i)
            self.navs[key] = b
            sv.addWidget(b)
        sv.addStretch()
        self.collapsed = False
        h.addWidget(self.sidebar)
        # ---------------- right
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        self.topbar = QFrame()
        self.topbar.setObjectName("topbar")
        tb = QHBoxLayout(self.topbar)
        tb.setContentsMargins(16, 10, 16, 4)
        self.menu_btn = QToolButton()
        self.menu_btn.setIcon(icon("menu", pal.text, 20))
        self.menu_btn.clicked.connect(self.toggle_sidebar)
        self.lib_combo = QComboBox()
        self.lib_combo.setMinimumWidth(170)
        self.lib_combo.activated.connect(lambda i: self.switch_library(self.lib_combo.itemData(i)))
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("search_ph"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", pal.muted, 18), QLineEdit.LeadingPosition)
        self.completer_model = QStringListModel()
        self.search.setCompleter(QCompleter(self.completer_model, self))
        self.search.textEdited.connect(self._suggest)
        self.search.returnPressed.connect(self.do_search)
        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("muted")
        tb.addWidget(self.menu_btn)
        tb.addWidget(self.lib_combo)
        tb.addWidget(self.search, 1)
        tb.addWidget(self.status_lbl)
        self.pbar = QProgressBar()
        self.pbar.setFixedWidth(150)
        self.pbar.hide()
        self.cancel_btn = QToolButton()
        self.cancel_btn.setIcon(icon("x", pal.text, 16))
        self.cancel_btn.hide()
        tb.addWidget(self.pbar)
        tb.addWidget(self.cancel_btn)
        right.addWidget(self.topbar)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        h.addLayout(right, 1)
        # ---------------- pages (index == NAV order)
        self.p_dash = DashboardPage(ctx)
        self.p_libs = LibrariesPage(ctx, self.switch_library, self.backup_one)
        self.p_all = BooksPage(ctx, "all", self.importer)
        self.p_shelf = ShelfPage(ctx)
        self.p_recent = BooksPage(ctx, "recent", self.importer)
        self.p_reading = BooksPage(ctx, "reading", self.importer)
        self.p_fav = BooksPage(ctx, "favorites", self.importer)
        self.p_cats = GroupPage(ctx, "category", "categories", self.open_group)
        self.p_auth = GroupPage(ctx, "author", "authors", self.open_group)
        self.p_fold = GroupPage(ctx, "source_dir", "folders", self.open_group)
        self.p_notes = NotesPage(ctx)
        self.p_ai = AssistantPage(ctx)
        self.p_backup = BackupPage(ctx, self.backup_one, self.backup_all, self.restore)
        self.p_set = SettingsPage(ctx, self.restartRequested.emit)
        self.p_set.ocr_btn.clicked.connect(self.importer.ocr_missing)
        self.p_search = SearchPage(ctx)
        self.pages = [self.p_dash, self.p_libs, self.p_all, self.p_shelf, self.p_recent, self.p_reading, self.p_fav,
                      self.p_cats, self.p_auth, self.p_fold, self.p_notes, self.p_ai, self.p_backup, self.p_set]
        for p in self.pages + [self.p_search]:
            self.stack.addWidget(p)
        self.stack.currentChanged.connect(self._page_changed)
        ctx.libraryChanged.connect(self.refresh_all)
        ctx.booksChanged.connect(self.refresh_current)
        ctx.openBook.connect(self.open_reader)
        ctx.status.connect(self.status_lbl.setText)
        self.navs["all_books"].setChecked(True)
        self.stack.setCurrentIndex(2)
        self.fill_libs()
        self.refresh_current()
        # scheduled backups
        self.sched = QTimer(self, interval=3_600_000, timeout=self.check_scheduled_backup)
        self.sched.start()
        QTimer.singleShot(4000, self.check_scheduled_backup)
        QTimer.singleShot(1500, self.verify_files)

    # ----------------------------------------------------------------- misc
    def toggle_sidebar(self):
        self.collapsed = not self.collapsed
        for key, b in self.navs.items():
            b.setToolButtonStyle(Qt.ToolButtonIconOnly if self.collapsed else Qt.ToolButtonTextBesideIcon)
            b.setMinimumWidth(0 if self.collapsed else 190)
            b.setToolTip(tr(key))
        self.title.setVisible(not self.collapsed)
        self.sidebar.setFixedWidth(60 if self.collapsed else 220)

    def fill_libs(self):
        self.lib_combo.blockSignals(True)
        self.lib_combo.clear()
        for l in self.ctx.mgr.list():
            self.lib_combo.addItem(("🔒 " if l["pw_hash"] else "") + l["name"], l["id"])
        self.lib_combo.setCurrentIndex(self.lib_combo.findData(self.ctx.lib_id))
        self.lib_combo.blockSignals(False)

    def switch_library(self, lib_id):
        if lib_id is None:
            return
        lib = self.ctx.mgr.get(lib_id)
        if lib["pw_hash"] and lib_id not in self.unlocked:
            pw, ok = QInputDialog.getText(self, tr("unlock"), tr("unlock"), QLineEdit.Password)
            if not ok or not self.ctx.mgr.central.check_password(lib_id, pw):
                if ok:
                    QMessageBox.warning(self, tr("error"), tr("wrong_pw"))
                self.fill_libs()
                return
            self.unlocked.add(lib_id)
        QPixmapCache.clear()
        self.ctx.set_library(lib_id)

    def refresh_all(self):
        self.fill_libs()
        self.refresh_current()

    def refresh_current(self):
        self._page_changed(self.stack.currentIndex())

    def _page_changed(self, i):
        if i < len(self.pages):
            self.navs[NAV[i][0]].setChecked(True)
        w = self.stack.widget(i)
        for fn in ("refresh", "prepare"):
            if hasattr(w, fn):
                try:
                    getattr(w, fn)()
                except Exception:
                    log.exception("page refresh failed")

    def open_group(self, kind, value):
        self.p_all.set_facet(kind, value)
        self.stack.setCurrentWidget(self.p_all)

    def show_progress(self, text, task):
        self.status_lbl.setText(text)
        self.pbar.setRange(0, 0)
        self.pbar.show()
        self.cancel_btn.show()
        if getattr(self, "_cancel_conn", None) is not None:
            self.cancel_btn.clicked.disconnect(self._cancel_conn)
        self._cancel_conn = self.cancel_btn.clicked.connect(task.cancel)

        def prog(a, b, msg):
            if b:
                self.pbar.setRange(0, b)
                self.pbar.setValue(a)
            self.status_lbl.setText(f"{text}  {msg[:40]}")
        task.progress.connect(prog)

    def hide_progress(self, msg=""):
        self.pbar.hide()
        self.cancel_btn.hide()
        self.status_lbl.setText(msg)

    # ----------------------------------------------------------------- search
    def _suggest(self, text):
        self.completer_model.setStringList(self.ctx.svc.suggest(text))

    def do_search(self):
        self.stack.setCurrentWidget(self.p_search)
        self.p_search.run(self.search.text())

    # ----------------------------------------------------------------- reader
    def open_reader(self, lib_id, bid, page):
        key = (lib_id, bid)
        w = self.readers.get(key)
        if w is not None and w.isVisible():
            if page:
                w.pv.go_to(page - 1)
            w.raise_()
            w.activateWindow()
            return
        w = ReaderWindow(self.ctx, lib_id, bid, page)
        if not w.ok:
            return
        w.closed.connect(lambda l, b: (self.readers.pop((l, b), None), self.ctx.booksChanged.emit()))
        self.readers[key] = w
        w.show()

    # ----------------------------------------------------------------- backup
    def backup_one(self, lib_id):
        try:
            out = bk.backup_library(self.ctx.mgr, lib_id, self.p_backup.backup_dir())
            self.status_lbl.setText(f"{tr('done')}: {out.name}")
            QMessageBox.information(self, tr("backup"), f"{tr('done')}\n{out}")
        except Exception as e:
            log.exception("backup failed")
            QMessageBox.warning(self, tr("error"), str(e))
        self.p_backup.refresh()

    def backup_all(self):
        try:
            out = bk.backup_all(self.ctx.mgr, self.p_backup.backup_dir())
            QMessageBox.information(self, tr("backup"), f"{tr('done')}\n{out}")
        except Exception as e:
            log.exception("backup failed")
            QMessageBox.warning(self, tr("error"), str(e))
        self.p_backup.refresh()

    def restore(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("restore"), str(self.p_backup.backup_dir()), "ZIP (*.zip)")
        if not f:
            return
        try:
            ids = bk.restore(self.ctx.mgr, Path(f))
            QMessageBox.information(self, tr("restore"), f"{tr('done')}: {len(ids)}")
            self.ctx.libraryChanged.emit()
        except Exception as e:
            log.exception("restore failed")
            QMessageBox.warning(self, tr("error"), str(e))

    def check_scheduled_backup(self):
        sched = int(self.ctx.setting("backup_sched", "0"))
        if not sched:
            return
        last = self.ctx.setting("last_backup", "")
        due = timedelta(days=1 if sched == 1 else 7)
        if last and datetime.now() - datetime.fromisoformat(last) < due:
            return
        try:
            out = bk.backup_all(self.ctx.mgr, self.p_backup.backup_dir())
            self.status_lbl.setText(f"Auto backup: {out.name}")
        except Exception:
            log.exception("scheduled backup failed")

    def verify_files(self):
        try:
            n = self.ctx.svc.check_missing()
            if n:
                self.status_lbl.setText(f"{n} × {tr('missing_file')}")
                self.refresh_current()
        except Exception:
            log.exception("verify failed")

    # ----------------------------------------------------------------- drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.importer.import_paths(paths)

    def closeEvent(self, e):
        for w in list(self.readers.values()):
            w.close()
        super().closeEvent(e)
