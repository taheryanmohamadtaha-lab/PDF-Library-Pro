import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication
from conftest import make_pdf


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_reader_navigation_selection_highlight_progress(qapp, mgr, tmp_path):
    from app.ui.context import Context
    from app.ui.reader import ReaderWindow
    ctx = Context(mgr)
    svc = ctx.svc
    _, bid = svc.add_pdf(make_pdf(tmp_path / "r.pdf", tuple(f"Page number {i} unique{i}word" for i in range(1, 7))))
    w = ReaderWindow(ctx, ctx.lib_id, bid)
    assert w.ok
    w.show(); qapp.processEvents()
    pv = w.pv
    assert pv.doc.page_count == 6
    for mode in ("single", "double", "continuous"):
        pv.set_mode(mode); qapp.processEvents()
        pv.go_to(3); qapp.processEvents()
        assert pv.cur == 3
        pv.step(1); assert pv.cur >= 4
        pv.viewport().grab()  # paints without error
    pv.set_zoom(1.5); pv.set_fit("page"); pv.set_rotation(90); pv.set_rotation(0)
    pv.set_mode("continuous"); pv.go_to(0); qapp.processEvents()
    # selection over the text line of page 1 -> real text extracted
    ox, oy = pv._page_origin(0)
    z = pv.zoom
    pv.sel = (0, QPointF(60 * z, 80 * z), QPointF(400 * z, 110 * z))
    class E:  # minimal mouse release event
        def button(self): return Qt.LeftButton
    pv.mouseReleaseEvent(E())
    assert "Page number 1" in pv.sel_text
    w.highlight_selection()
    assert len(svc.highlights(bid, 1)) == 1
    w.find_edit.setText("unique4word"); w.do_find()
    assert w.res_list.count() == 1 and pv.cur == 3
    w.add_bookmark(); assert len(svc.bookmarks(bid)) == 1
    w._save_progress()
    assert svc.progress(bid)["page"] == 4
    w.grab().save(str(tmp_path / "reader.png"))
    w.close()
    w2 = ReaderWindow(ctx, ctx.lib_id, bid)  # resumes last page
    assert w2.pv.cur == 3
    w2.close()
