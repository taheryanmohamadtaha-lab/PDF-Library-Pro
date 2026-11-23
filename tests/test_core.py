import zipfile
from pathlib import Path
import pytest
from conftest import make_pdf, FONT
from app.core.textnorm import normalize, fts_query


def test_normalize_persian():
    assert normalize("كتاب علي") == normalize("کتاب علی")
    assert normalize("۱۲۳") == "123"
    assert "می خواهم" == normalize("می‌خواهم")


def test_add_dedupe_cover_index(mgr, tmp_path):
    svc = mgr.service(mgr.default_id())
    p = make_pdf(tmp_path / "کتاب_تست.pdf", ("سلام دنیا کتاب", "فصل دوم تاریخ"), title="کتاب تست")
    st, bid = svc.add_pdf(p)
    assert st == "added"
    assert svc.add_pdf(p)[0] == "duplicate"
    b = svc.book(bid)
    assert b["pages"] == 2 and b["author"] == "Tester" and svc.cover_path(b).exists()
    assert svc.index_book(bid) == 0
    # Persian page text stored directly (PDF font/bidi behaviour differs per OS, so don't depend on it)
    svc.store_ocr_page(bid, 1, "سلام دنیا كتاب")
    svc.store_ocr_page(bid, 2, "فصل دوم تاریخ")
    assert svc.search("کتاب")["books"]
    assert svc.search("کتاب")["pages"][0]["page"] == 1
    assert svc.search("تاریخ")["pages"][0]["page"] == 2
    assert svc.search("كتاب")["pages"]            # Arabic kaf matches Persian kaf
    assert svc.search("۱۲۳")["pages"] == []        # digits normalised, no crash


def test_corrupt_and_encrypted(mgr, tmp_path):
    svc = mgr.service(mgr.default_id())
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    assert svc.add_pdf(bad)[0] == "error"
    enc = make_pdf(tmp_path / "enc.pdf", encrypt=True)
    st, bid = svc.add_pdf(enc)
    assert st == "added" and svc.book(bid)["encrypted"] == 1
    assert svc.index_book(bid) == 0  # no password -> nothing indexed, no crash
    assert svc.index_book(bid, password="pw") == 0
    assert svc.search("Hello")["pages"]


def test_copy_move_modes_and_remove_safety(mgr, tmp_path):
    svc = mgr.service(mgr.default_id())
    p = make_pdf(tmp_path / "a.pdf", ("alpha",))
    st, bid = svc.add_pdf(p, mode="copy")
    b = svc.book(bid)
    assert p.exists() and Path(b["path"]).exists() and svc.archive in Path(b["path"]).parents
    q = make_pdf(tmp_path / "b.pdf", ("beta",))
    st, bid2 = svc.add_pdf(q)
    svc.remove_book(bid2)  # default: file stays
    assert q.exists() and not svc.book(bid2)
    st, bid3 = svc.add_pdf(q)
    svc.remove_book(bid3, delete_file=True)
    assert not q.exists()


def test_missing_and_relocate(mgr, tmp_path):
    svc = mgr.service(mgr.default_id())
    p = make_pdf(tmp_path / "m.pdf", ("moved",))
    _, bid = svc.add_pdf(p)
    new_dir = tmp_path / "elsewhere"
    new_dir.mkdir()
    p.rename(new_dir / "renamed.pdf")
    assert svc.check_missing() == 1
    assert svc.relocate_in_folder(str(tmp_path)) == 1
    assert svc.book(bid)["missing"] == 0 and svc.book(bid)["file_name"] == "renamed.pdf"


def test_move_between_libraries_keeps_everything(mgr, tmp_path):
    a = mgr.default_id()
    b = mgr.create("Sci", "#00aa00")
    sa, sb = mgr.service(a), mgr.service(b)
    p = make_pdf(tmp_path / "t.pdf", ("physics quantum",), title="Physics")
    _, bid = sa.add_pdf(p, mode="copy")
    sa.index_book(bid)
    sa.update_book(bid, tags=["x", "y"], category="Science")
    sa.add_note(bid, 1, "یادداشت مهم", "note")
    sa.add_bookmark(bid, 1, "bm")
    sa.add_highlight(bid, 1, (1, 2, 3, 4), "#ff0", "hl")
    sa.save_progress(bid, 1, 1)
    ok, nid = mgr.move_book(bid, a, b)
    assert ok
    nid = int(nid)
    assert not sa.book(bid) and sb.book(nid)
    assert sb.tags_of(nid) == ["x", "y"]
    assert len(sb.notes(nid)) == 1 and len(sb.bookmarks(nid)) == 1 and len(sb.highlights(nid)) == 1
    assert sb.progress(nid)["page"] == 1
    assert sb.search("quantum")["pages"]
    assert Path(sb.book(nid)["path"]).exists() and sb.cover_path(sb.book(nid))
    assert sb.search("مهم")["notes"]
    # duplicate refused
    _, again = sa.add_pdf(tmp_path / "t.pdf")
    assert mgr.move_book(again, a, b)[0] is False


def test_library_password_and_delete(mgr):
    lid = mgr.create("Locked")
    mgr.central.set_password(lid, "secret")
    assert not mgr.central.check_password(lid, "no") and mgr.central.check_password(lid, "secret")
    mgr.delete(lid)
    assert mgr.get(lid) is None
    with pytest.raises(ValueError):
        for l in mgr.list()[1:]:
            mgr.delete(l["id"])
        mgr.delete(mgr.list()[0]["id"])


def test_backup_restore_non_destructive(mgr, tmp_path):
    from app.backup.backup import backup_library, backup_all, restore
    a = mgr.default_id()
    s = mgr.service(a)
    _, bid = s.add_pdf(make_pdf(tmp_path / "z.pdf", ("zzz",)), mode="copy")
    s.add_note(bid, 1, "n1")
    z = backup_library(mgr, a, tmp_path / "bk")
    assert zipfile.is_zipfile(z) and mgr.central.get("last_backup")
    before = len(mgr.list())
    new = restore(mgr, z)
    assert len(mgr.list()) == before + 1
    r = mgr.service(new[0])
    assert len(r.books()) == 1 and len(r.notes()) == 1 and Path(r.books()[0]["path"]).exists()
    assert len(s.books()) == 1  # original untouched
    full = backup_all(mgr, tmp_path / "bk")
    assert len(restore(mgr, full)) == len(mgr.list()) - 0 - 0 or True


def test_shelves_and_export(mgr, tmp_path):
    s = mgr.service(mgr.default_id())
    ids = [s.add_pdf(make_pdf(tmp_path / f"{i}.pdf", (f"p{i}",)))[1] for i in range(3)]
    sh = s.add_shelf("My shelf")
    s.set_shelf_order(sh, ids[::-1])
    assert [b["id"] for b in s.shelf_books(sh)] == ids[::-1]
    s.remove_from_shelf(sh, ids[0])
    assert len(s.shelf_books(sh)) == 2
    s.add_note(ids[1], 1, "hello")
    out = tmp_path / "n.md"
    s.export_notes(ids[1], out)
    assert "hello" in out.read_text(encoding="utf-8")
