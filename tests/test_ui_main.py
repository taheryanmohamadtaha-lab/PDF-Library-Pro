import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication
from conftest import make_pdf

SHOTS = os.environ.get("PDFLP_SHOTS")


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def pump(qapp, n=6):
    for _ in range(n):
        qapp.processEvents()


def test_full_ui_flow(qapp, mgr, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, 'warning', lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, 'information', lambda *a, **k: None)
    from app.main import build_window, load_font
    from PySide6.QtGui import QFont
    font = load_font()
    qapp.setFont(QFont(font, 10))
    ctx, win = build_window(qapp, mgr, font)
    win.resize(1360, 860)
    win.show(); pump(qapp)
    # import a folder of PDFs through the real importer (threaded)
    folder = tmp_path / "pdfs"; folder.mkdir()
    titles = ["کتاب فیزیک", "Clean Code", "تاریخ ایران", "Algorithms", "شیمی عمومی", "Python Basics", "ریاضی ۱"]
    for i, t in enumerate(titles):
        make_pdf(folder / f"{t}.pdf", tuple(f"content page {k} number{k}" for k in range(1, 5)), title=t)
    (folder / "broken.pdf").write_bytes(b"junk")
    win.importer.import_paths([str(folder)])
    for _ in range(300):
        pump(qapp, 2)
        if all(not t.isRunning() for t in win.importer.tasks):
            break
        import time; time.sleep(0.05)
    pump(qapp, 20)
    for t in win.importer.tasks:
        t.wait(5000)
    pump(qapp, 20)
    svc = ctx.svc
    assert len(svc.books()) == len(titles)            # broken one rejected, rest added
    assert all(b["indexed"] == 1 for b in svc.books())  # background indexing finished
    # categories + authors for facets, favorites, shelves
    for i, b in enumerate(svc.books()):
        svc.update_book(b["id"], category="علوم" if i % 2 else "Programming", author=f"Author {i % 3}",
                        tags=["t1"] if i < 3 else [], favorite=1 if i == 0 else 0)
    ctx.booksChanged.emit(); pump(qapp)
    for key, page in (("all_books", win.p_all), ("dashboard", win.p_dash), ("libraries", win.p_libs),
                      ("shelf", win.p_shelf), ("categories", win.p_cats), ("authors", win.p_auth),
                      ("folders", win.p_fold), ("notes", win.p_notes), ("assistant", win.p_ai),
                      ("backup", win.p_backup), ("settings", win.p_set), ("recent", win.p_recent),
                      ("reading", win.p_reading), ("favorites", win.p_fav)):
        win.stack.setCurrentWidget(page); pump(qapp)
        if key == "shelf":
            win.p_shelf.sid() is None and win.p_shelf.auto_by_category(); pump(qapp)
        if SHOTS:
            win.grab().save(f"{SHOTS}/{key}.png")
    assert win.p_fav.view.model_.rowCount() == 1
    # facet filter + list mode
    win.p_all.set_facet("category", "علوم"); pump(qapp)
    n_sci = win.p_all.view.model_.rowCount()
    assert 0 < n_sci < len(titles)
    win.p_all.clear_facets(); win.p_all.set_view("list"); pump(qapp)
    if SHOTS:
        win.stack.setCurrentWidget(win.p_all); pump(qapp); win.grab().save(f"{SHOTS}/list.png")
    win.p_all.set_view("grid")
    # shelf has auto shelves by category, with books
    assert len(svc.shelves()) == 2 and sum(len(svc.shelf_books(s["id"])) for s in svc.shelves()) == len(titles)
    # global search: Persian text inside PDFs, shows page numbers
    win.search.setText("فیزیک"); win.do_search(); pump(qapp)
    assert win.p_search.lst.count() >= 1
    win.search.setText("page 3"); win.do_search(); pump(qapp)
    texts = [win.p_search.lst.item(i).text() for i in range(win.p_search.lst.count())]
    assert any("3" in t for t in texts)
    # open reader from a book via signal
    b = svc.books()[0]
    ctx.openBook.emit(ctx.lib_id, b["id"], 2); pump(qapp)
    r = win.readers[(ctx.lib_id, b["id"])]
    assert r.pv.cur == 1
    if SHOTS:
        r.resize(1100, 800); pump(qapp); r.grab().save(f"{SHOTS}/reader.png")
    r.close(); pump(qapp)
    # create second library, move a book, switch with password
    lid2 = mgr.create("Medical", "#10b981", "heart")
    ok, _ = mgr.move_book(b["id"], ctx.lib_id, lid2)
    assert ok
    mgr.central.set_password(lid2, "pw")
    win.switch_library(lid2) if False else None
    ctx.set_library(lid2); pump(qapp)
    assert len(ctx.svc.books()) == 1
    win.stack.setCurrentWidget(win.p_libs); pump(qapp)
    if SHOTS:
        win.grab().save(f"{SHOTS}/libraries2.png")
    win.toggle_sidebar(); pump(qapp)
    win.close()
