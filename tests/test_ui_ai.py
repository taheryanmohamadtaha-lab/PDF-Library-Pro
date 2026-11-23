import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import threading, time
from http.server import HTTPServer
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from conftest import make_pdf
from test_ai import H


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def wait(qapp, cond, t=10):
    end = time.time() + t
    while time.time() < end and not cond():
        qapp.processEvents(); time.sleep(0.02)
    assert cond()


def test_settings_and_assistant_with_local_ai(qapp, mgr, tmp_path, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    from app.main import build_window, load_font
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}"
    ctx, win = build_window(qapp, mgr, load_font())
    _, bid = ctx.svc.add_pdf(make_pdf(tmp_path / "a.pdf", ("Mitochondria produce ATP energy", "Cells divide")))
    ctx.svc.index_book(bid)
    # settings: switch to local AI, save an API key -> key must not be in SQLite
    s = win.p_set
    s.mode.setCurrentIndex(1); s.o_url.setText(url); s.o_model.setCurrentText("fake:1b")
    s.a_key.setText("sk-secret-123")
    restarts = []
    win.restartRequested.connect(lambda: restarts.append(1))
    s.save()
    assert restarts and ctx.setting("ai_mode") == "local"
    dump = b"".join(open(p, "rb").read() for p in (mgr.home / "central.db",))
    assert b"sk-secret-123" not in dump
    from app.ai.secrets import load_key
    assert load_key() == "sk-secret-123"
    s.refresh_models(); assert s.o_model.count() == 1
    # assistant Q&A with page citation + saved conversation
    ai = win.p_ai
    ai.refresh()
    ai.books.item(0).setSelected(True)
    ai.q.setPlainText("What do mitochondria produce?")
    ai.run()
    wait(qapp, lambda: ai.run_btn.isEnabled())
    assert "Answer" in ai.out.toPlainText() and "p.1" in ai.out.toPlainText()
    assert ctx.svc.db.one("SELECT COUNT(*) FROM ai_conversations")[0] == 1
    # unanswerable question -> explicit "not in PDF", no model call
    ai.q.setPlainText("quantum gluon chromodynamics"); ai.run()
    wait(qapp, lambda: ai.run_btn.isEnabled())
    assert "پیدا نشد" in ai.out.toPlainText()
    # no-AI mode keeps everything else working
    ctx.mgr.central.set("ai_mode", "none")
    ai.refresh()
    assert len(ctx.svc.books()) == 1
    srv.shutdown(); win.close()


def test_ocr_missing_is_graceful(mgr, tmp_path, monkeypatch):
    from app.ocr import ocr
    monkeypatch.setattr(ocr, "find_tesseract", lambda: None)
    svc = mgr.service(mgr.default_id())
    _, bid = svc.add_pdf(make_pdf(tmp_path / "s.pdf", ("x",)))
    assert ocr.ocr_pages(svc, bid) == (0, "tesseract-not-installed")
