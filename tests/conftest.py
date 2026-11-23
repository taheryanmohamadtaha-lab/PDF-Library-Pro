import os, sys
from pathlib import Path
import pymupdf, pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
FONT = next((p for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                         r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\tahoma.ttf"] if Path(p).exists()), None)


def make_pdf(path: Path, pages=("Hello world", "Second page"), title="", encrypt=False):
    doc = pymupdf.open()
    for t in pages:
        pg = doc.new_page()
        if any('\u0600' <= ch <= '\u06ff' for ch in t):
            t = t[::-1]  # fake PDF has no bidi shaping; reverse so extraction yields logical order
        if FONT:
            pg.insert_text((72, 100), t, fontname="f1", fontfile=FONT, fontsize=14)
        else:
            pg.insert_text((72, 100), t)
        pg.insert_text((72, 140), "x" * 30)
    if title:
        doc.set_metadata({"title": title, "author": "Tester"})
    if encrypt:
        doc.save(str(path), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    else:
        doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFLP_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def mgr(home):
    from app.libraries.manager import LibraryManager
    m = LibraryManager(home)
    yield m
    m.close_all()
