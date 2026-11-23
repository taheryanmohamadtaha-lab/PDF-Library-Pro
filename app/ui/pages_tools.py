"""AI assistant, backup and settings pages."""
import html
import json
from datetime import datetime
from pathlib import Path

import pymupdf
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSpinBox, QSplitter, QTextBrowser, QVBoxLayout, QWidget)

from ..ai import rag
from ..ai.factory import make_provider
from ..ai.providers import AIError, OllamaProvider
from ..ai.secrets import load_key, save_key
from ..backup import backup as bk
from ..core import i18n
from ..core.i18n import tr
from ..ocr import ocr as ocrmod
from .dialogs import confirm
from .pages_library import Header, btn, lbl
from .theme import ACCENTS
from .workers import Task

TASKS = [("qa", "پرسش و پاسخ", "Q&A"), ("summary", "خلاصه‌سازی کتاب", "Book summary"),
         ("chapter", "خلاصه فصل", "Chapter summary"), ("pages", "خلاصه صفحات انتخابی", "Selected pages summary"),
         ("keypoints", "نکات مهم", "Key points"), ("definitions", "تعاریف", "Definitions"),
         ("flashcards", "فلش‌کارت", "Flashcards"), ("quiz", "آزمون چهارگزینه‌ای", "Multiple-choice quiz"),
         ("compare", "مقایسه کتاب‌ها", "Compare books"), ("topics", "موضوعات", "Topics"),
         ("handout", "جزوه خلاصه", "Study handout")]


class AssistantPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.task = None
        self.last = ""
        self.provider_factory = make_provider
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 8, 24, 8)
        left = QVBoxLayout()
        self.head = Header(tr("assistant"))
        left.addWidget(self.head)
        self.status_lbl = lbl("", "muted")
        left.addWidget(self.status_lbl)
        self.books = QListWidget()
        self.books.setSelectionMode(QListWidget.MultiSelection)
        left.addWidget(lbl(tr("all_books"), "h2"))
        left.addWidget(self.books, 1)
        lay.addLayout(left, 1)
        right = QVBoxLayout()
        form = QHBoxLayout()
        self.task_box = QComboBox()
        for k, fa, en in TASKS:
            self.task_box.addItem(fa if i18n.lang() == "fa" else en, k)
        self.p_from = QSpinBox(); self.p_to = QSpinBox()
        for s in (self.p_from, self.p_to):
            s.setRange(1, 99999)
        self.p_to.setValue(10)
        self.topic = QLineEdit()
        self.topic.setPlaceholderText("فصل / موضوع (اختیاری)")
        for w in (self.task_box, QLabel(tr("page")), self.p_from, QLabel("–"), self.p_to, self.topic):
            form.addWidget(w)
        right.addLayout(form)
        self.q = QPlainTextEdit()
        self.q.setPlaceholderText(tr("ask") + "…")
        self.q.setFixedHeight(70)
        right.addWidget(self.q)
        row = QHBoxLayout()
        self.run_btn = btn(tr("run"), True)
        self.run_btn.clicked.connect(self.run)
        self.save_btn = btn(tr("export"))
        self.save_btn.clicked.connect(self.export)
        self.hist = QComboBox()
        self.hist.activated.connect(self.load_conv)
        row.addWidget(self.run_btn); row.addWidget(self.save_btn); row.addWidget(self.hist, 1)
        right.addLayout(row)
        self.out = QTextBrowser()
        self.out.setOpenLinks(False)
        self.out.anchorClicked.connect(self._link)
        right.addWidget(self.out, 3)
        lay.addLayout(right, 2)
        self.consented = False
        self.sources = []

    def refresh(self):
        provider = make_provider(self.ctx.mgr.central)
        mode = self.ctx.setting("ai_mode", "none")
        if mode == "none":
            self.status_lbl.setText(tr("ai_none") + " — " + "تنظیمات ← هوش مصنوعی")
        elif mode == "local":
            st = provider.status()
            self.status_lbl.setText(("● Ollama OK — " + provider.model) if st["ok"] and provider.model else
                                    ("Ollama: " + (st.get("error") or "مدل انتخاب نشده")))
        else:
            self.status_lbl.setText("API: " + (provider.model or "?") + f" — tokens used this session: {getattr(provider, 'used_tokens', 0)}")
        self.books.clear()
        for l in self.ctx.mgr.list():
            for b in self.ctx.mgr.service(l["id"]).books(order="b.title COLLATE NOCASE"):
                it = QListWidgetItem(f"{b['title']}  [{l['name']}]" if len(self.ctx.mgr.list()) > 1 else b["title"])
                it.setData(Qt.UserRole, (l["id"], b["id"]))
                self.books.addItem(it)
        self.hist.clear()
        self.hist.addItem("— " + tr("assistant") + " —", None)
        for r in self.ctx.svc.db.q("SELECT id,title FROM ai_conversations ORDER BY id DESC LIMIT 30"):
            self.hist.addItem(r["title"], r["id"])

    def retranslate(self):
        self.head.t.setText(tr("assistant"))
        self.run_btn.setText(tr("run"))
        self.save_btn.setText(tr("export"))

    def run(self):
        sel = [i.data(Qt.UserRole) for i in self.books.selectedItems()]
        if not sel:
            QMessageBox.information(self, tr("assistant"), tr("all_books") + "؟")
            return
        provider = make_provider(self.ctx.mgr.central)
        if provider is None:
            QMessageBox.information(self, tr("assistant"), tr("ai_none"))
            return
        if provider.sends_data_online and not self.consented:
            if not confirm(self, tr("ai_consent")):
                return
            self.consented = True
        task = self.task_box.currentData()
        question = self.q.toPlainText().strip()
        topic = self.topic.text().strip()
        if task == "qa" and not question:
            return
        svcs = {l["id"]: self.ctx.mgr.service(l["id"]) for l in self.ctx.mgr.list()}
        pr = (self.p_from.value(), self.p_to.value())
        self.run_btn.setEnabled(False)
        self.out.setHtml("<i>…</i>")

        def work(progress, cancelled):
            if task == "qa":
                return rag.ask(provider, svcs, sel, question)
            rng = None
            if task == "pages":
                rng, t = pr, "summary"
            elif task == "chapter":
                lib, bid = sel[0]
                b = svcs[lib].book(bid)
                doc = pymupdf.open(b["path"])
                rng = rag.chapter_range(doc.get_toc(), topic, b["pages"]) if not doc.needs_pass else None
                doc.close()
                if not rng:
                    return rag.Answer("فصل پیدا نشد (فهرست PDF یا نام فصل را بررسی کنید).", [], True)
                t = "summary"
            else:
                t = task
            t = {"pages": "summary", "chapter": "summary"}.get(task, task)
            return rag.run_task(provider, svcs, sel, t, rng, "" if task in ("chapter",) else topic, lambda m: progress(0, 0, m))

        self.task = Task(work, self)
        self.task.done.connect(lambda a: self._show(a, task, sel, question))
        self.task.failed.connect(self._fail)
        self.task.start()

    def _fail(self, msg):
        self.run_btn.setEnabled(True)
        self.out.setHtml(f"<b style='color:#ef4444'>{tr('error')}:</b> {html.escape(msg)}")

    def _show(self, ans, task, sel, question):
        self.run_btn.setEnabled(True)
        if not ans.found:
            self.out.setHtml(f"<b>{html.escape(tr('ai_not_found'))}</b>")
            self.last = tr("ai_not_found")
            return
        text = ans.text
        if task in ("flashcards", "quiz"):
            data = rag.parse_json(text)
            if data:
                lines = []
                for i, c in enumerate(data, 1):
                    if task == "flashcards":
                        lines.append(f"{i}. {c.get('q')}\n   → {c.get('a')}  (p.{c.get('page', '?')})")
                    else:
                        opts = c.get("options", [])
                        lines.append(f"{i}. {c.get('q')}\n" + "\n".join(f"   {'ABCD'[j]}) {o}" for j, o in enumerate(opts[:4])) +
                                     f"\n   ✔ {'ABCD'[int(c.get('answer', 0)) % 4]}  (p.{c.get('page', '?')})")
                text = "\n\n".join(lines)
        self.last = text
        self.sources = ans.sources
        src = "".join(f"<a href='open:{lid_bid[0]}:{b}:{p}'>{html.escape(t)} p.{p}</a> &nbsp; " for t, p, b in ans.sources
                      for lid_bid in [next(s for s in sel if s[1] == b)])
        self.out.setHtml(f"<div style='white-space:pre-wrap'>{html.escape(text)}</div><hr><b>{tr('sources')}:</b><br>{src}")
        title = (question or self.task_box.currentText())[:60]
        db = self.ctx.mgr.service(sel[0][0]).db
        cid = db.x("INSERT INTO ai_conversations(title,book_ids) VALUES(?,?)", (title, json.dumps(sel)))
        db.x("INSERT INTO ai_messages(conversation_id,role,content) VALUES(?,?,?)", (cid, "user", question or task))
        db.x("INSERT INTO ai_messages(conversation_id,role,content,sources) VALUES(?,?,?,?)",
             (cid, "assistant", text, json.dumps(ans.sources)))
        if sel[0][0] == self.ctx.lib_id:
            self.hist.insertItem(1, title, cid)

    def load_conv(self, idx):
        cid = self.hist.itemData(idx)
        if cid is None:
            return
        rows = self.ctx.svc.db.q("SELECT role,content FROM ai_messages WHERE conversation_id=? ORDER BY id", (cid,))
        self.out.setHtml("".join(f"<p><b>{r['role']}:</b><br><span style='white-space:pre-wrap'>{html.escape(r['content'])}</span></p>" for r in rows))
        self.last = rows[-1]["content"] if rows else ""

    def _link(self, url):
        s = url.toString()
        if s.startswith("open:"):
            _, lib, bid, page = s.split(":")
            self.ctx.openBook.emit(int(lib), int(bid), int(page))

    def export(self):
        if not self.last:
            return
        f, _ = QFileDialog.getSaveFileName(self, tr("export"), "answer.md", "Markdown (*.md);;Text (*.txt)")
        if f:
            Path(f).write_text(self.last, encoding="utf-8")


# ============================================================ backup
class BackupPage(QWidget):
    def __init__(self, ctx, backup_one, backup_all, restore_fn):
        super().__init__()
        self.ctx = ctx
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 8, 24, 8)
        self.head = Header(tr("backup"))
        lay.addWidget(self.head)
        self.info = lbl("", "muted")
        lay.addWidget(self.info)
        self.b1 = btn(tr("backup_now"), True, "backup", ctx)
        self.b2 = btn(tr("backup_all"), ic="backup", ctx=ctx)
        self.b3 = btn(tr("restore"), ic="library", ctx=ctx)
        self.b1.clicked.connect(lambda: backup_one(ctx.lib_id))
        self.b2.clicked.connect(backup_all)
        self.b3.clicked.connect(restore_fn)
        for b in (self.b1, self.b2, self.b3):
            lay.addWidget(b)
        row = QHBoxLayout()
        row.addWidget(lbl("زمان‌بندی خودکار"))
        self.sched = QComboBox()
        self.sched.addItems(["خاموش", "روزانه", "هفتگی"])
        self.sched.setCurrentIndex(int(ctx.setting("backup_sched", "0")))
        self.sched.currentIndexChanged.connect(lambda i: ctx.mgr.central.set("backup_sched", i))
        row.addWidget(self.sched)
        row.addStretch()
        lay.addLayout(row)
        self.folder = lbl("", "muted")
        bf = btn("…")
        bf.clicked.connect(self.pick_folder)
        r2 = QHBoxLayout(); r2.addWidget(lbl(tr("location"))); r2.addWidget(self.folder, 1); r2.addWidget(bf)
        lay.addLayout(r2)
        lay.addStretch()

    def backup_dir(self) -> Path:
        d = Path(self.ctx.setting("backup_dir", "") or (self.ctx.mgr.home / "backups"))
        d.mkdir(parents=True, exist_ok=True)
        return d

    def pick_folder(self):
        f = QFileDialog.getExistingDirectory(self, tr("location"), str(self.backup_dir()))
        if f:
            self.ctx.mgr.central.set("backup_dir", f)
            self.refresh()

    def refresh(self):
        last = self.ctx.setting("last_backup", "")
        per = self.ctx.setting(f"last_backup_{self.ctx.lib_id}", "")
        self.info.setText(f"{tr('last_backup')}: {last or tr('never')}  |  {self.ctx.lib['name']}: {per or tr('never')}")
        self.folder.setText(str(self.backup_dir()))


# ============================================================ settings
class SettingsPage(QWidget):
    changed = None

    def __init__(self, ctx, apply_fn):
        super().__init__()
        self.ctx, self.apply = ctx, apply_fn
        c = ctx.mgr.central
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFrameShape(QFrame.NoFrame)
        host = QWidget(); sc.setWidget(host)
        outer = QVBoxLayout(self); outer.setContentsMargins(24, 8, 24, 8)
        self.head = Header(tr("settings"))
        outer.addWidget(self.head); outer.addWidget(sc)
        lay = QVBoxLayout(host)
        # ---- appearance
        g = QGroupBox("ظاهر / Appearance"); f = QFormLayout(g)
        self.lang = QComboBox(); self.lang.addItem("فارسی", "fa"); self.lang.addItem("English", "en")
        self.lang.setCurrentIndex(0 if c.get("lang", "fa") == "fa" else 1)
        self.theme = QComboBox(); self.theme.addItem(tr("dark"), "dark"); self.theme.addItem(tr("light"), "light")
        self.theme.setCurrentIndex(0 if c.get("theme", "dark") == "dark" else 1)
        self.accent = QComboBox()
        for k in ACCENTS:
            self.accent.addItem(k, k)
        self.accent.setCurrentText(c.get("accent", "purple"))
        self.copy = QComboBox()
        for k in ("link", "copy", "move"):
            self.copy.addItem(tr(k), k)
        self.copy.setCurrentIndex(["link", "copy", "move"].index(c.get("copy_mode", "link")))
        f.addRow(tr("language"), self.lang); f.addRow(tr("theme"), self.theme)
        f.addRow(tr("accent"), self.accent); f.addRow(tr("copy_mode"), self.copy)
        lay.addWidget(g)
        # ---- AI
        g2 = QGroupBox(tr("ai_mode")); f2 = QFormLayout(g2)
        self.mode = QComboBox()
        for k in ("none", "local", "api"):
            self.mode.addItem(tr("ai_" + k), k)
        self.mode.setCurrentIndex(["none", "local", "api"].index(c.get("ai_mode", "none")))
        self.o_url = QLineEdit(c.get("ollama_url", "http://localhost:11434"))
        self.o_model = QComboBox(); self.o_model.setEditable(True); self.o_model.setCurrentText(c.get("ollama_model", ""))
        rf = btn("↻"); rf.clicked.connect(self.refresh_models)
        self.o_stat = lbl("", "muted")
        orow = QHBoxLayout(); orow.addWidget(self.o_model, 1); orow.addWidget(rf)
        self.a_url = QLineEdit(c.get("api_url", "https://api.openai.com/v1"))
        self.a_model = QLineEdit(c.get("api_model", ""))
        self.a_key = QLineEdit(); self.a_key.setEchoMode(QLineEdit.Password)
        self.a_key.setPlaceholderText("●●●● (ذخیره امن)" if load_key() else "API key")
        self.a_tokens = QSpinBox(); self.a_tokens.setRange(100, 8000); self.a_tokens.setValue(int(c.get("api_max_tokens", "1200")))
        f2.addRow(tr("ai_mode"), self.mode)
        f2.addRow("Ollama URL", self.o_url); f2.addRow("Ollama model", orow); f2.addRow("", self.o_stat)
        f2.addRow("API URL", self.a_url); f2.addRow("API model", self.a_model); f2.addRow("API key", self.a_key)
        f2.addRow("max tokens / reply", self.a_tokens)
        lay.addWidget(g2)
        # ---- OCR
        g3 = QGroupBox("OCR"); f3 = QFormLayout(g3)
        exe = ocrmod.find_tesseract()
        self.ocr_lbl = lbl(("✓ " + exe) if exe else tr("ocr_missing"), "muted"); self.ocr_lbl.setWordWrap(True)
        self.ocr_langs = QLineEdit(c.get("ocr_langs", "fas+eng"))
        f3.addRow("Tesseract", self.ocr_lbl); f3.addRow("Languages", self.ocr_langs)
        self.ocr_btn = btn(tr("ocr_run"))
        f3.addRow("", self.ocr_btn)
        lay.addWidget(g3)
        save = btn(tr("save"), True); save.clicked.connect(self.save)
        lay.addWidget(save); lay.addStretch()

    def refresh_models(self):
        st = OllamaProvider(self.o_url.text()).status()
        self.o_model.clear()
        self.o_model.addItems(st["models"])
        self.o_stat.setText("● OK" if st["ok"] else "✗ " + st.get("error", ""))

    def save(self):
        c = self.ctx.mgr.central
        c.set("lang", self.lang.currentData()); c.set("theme", self.theme.currentData())
        c.set("accent", self.accent.currentData()); c.set("copy_mode", self.copy.currentData())
        c.set("ai_mode", self.mode.currentData()); c.set("ollama_url", self.o_url.text().strip())
        c.set("ollama_model", self.o_model.currentText().strip()); c.set("api_url", self.a_url.text().strip())
        c.set("api_model", self.a_model.text().strip()); c.set("api_max_tokens", self.a_tokens.value())
        c.set("ocr_langs", self.ocr_langs.text().strip() or "fas+eng")
        if self.a_key.text().strip():
            save_key(self.a_key.text().strip())  # never stored in SQLite
            self.a_key.clear(); self.a_key.setPlaceholderText("●●●● (ذخیره امن)")
        self.apply()

    def retranslate(self):
        self.head.t.setText(tr("settings"))
