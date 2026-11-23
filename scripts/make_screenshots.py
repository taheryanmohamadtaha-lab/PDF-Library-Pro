"""Generate real screenshots of the running app (offscreen) using demo PDFs with coloured covers."""
import os, sys, tempfile, time
from pathlib import Path
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pymupdf
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp())
os.environ["PDFLP_HOME"] = str(tmp / "home")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BOOKS = [("Clean Code", "R. Martin", "Programming", "#1f6feb"), ("Algorithms", "Sedgewick", "Programming", "#8250df"),
         ("Quantum Physics", "Feynman", "Science", "#cf222e"), ("World History", "Harari", "History", "#9a6700"),
         ("Organic Chemistry", "Clayden", "Science", "#1a7f37"), ("Deep Learning", "Goodfellow", "Programming", "#bc4c00"),
         ("Anatomy Atlas", "Netter", "Medical", "#0a7d8c"), ("Persian Poetry", "Hafez", "Literature", "#a40e8c"),
         ("Linear Algebra", "Strang", "Science", "#24292f"), ("Economics 101", "Mankiw", "Economics", "#2da44e"),
         ("Design Patterns", "GoF", "Programming", "#6639ba"), ("Astronomy", "Sagan", "Science", "#0969da")]


def pdf(path, title, author, color):
    d = pymupdf.open()
    for n in range(1, 13):
        pg = d.new_page()
        if n == 1:
            c = tuple(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
            pg.draw_rect(pg.rect, color=c, fill=c)
            pg.insert_textbox(pymupdf.Rect(40, 200, 555, 420), title, fontname="b", fontfile=FONT, fontsize=44,
                              color=(1, 1, 1), align=1)
            pg.insert_textbox(pymupdf.Rect(40, 700, 555, 760), author, fontname="b", fontfile=FONT, fontsize=20,
                              color=(1, 1, 1), align=1)
        else:
            pg.insert_textbox(pymupdf.Rect(72, 90, 520, 760),
                              f"{title}\n\nChapter {n - 1}\n\n" + ("Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 40),
                              fontname="b", fontfile=FONT, fontsize=11)
    d.set_metadata({"title": title, "author": author})
    d.set_toc([[1, f"Chapter {i}", i + 1] for i in range(1, 6)])
    d.save(str(path))


app = QApplication([])
from app.libraries.manager import LibraryManager
from app.main import build_window, load_font
mgr = LibraryManager()
font = load_font(); app.setFont(QFont(font, 10))
ctx, win = build_window(app, mgr, font)
win.resize(1400, 880); win.show()
svc = ctx.svc
src = tmp / "pdfs"; src.mkdir()
for t, a, c, col in BOOKS:
    p = src / f"{t}.pdf"; pdf(p, t, a, col)
    st, bid = svc.add_pdf(p, "copy")
    svc.index_book(bid)
    svc.update_book(bid, category=c, author=a, tags=[c.lower()])
for i, b in enumerate(svc.books()):
    if i % 3 == 0:
        svc.save_progress(b["id"], 3 + i, 12)
    if i in (0, 4):
        svc.update_book(b["id"], favorite=1)
svc.add_note(svc.books()[0]["id"], 2, "نکته مهم این فصل")
mgr.create("کتابخانه علمی", "#10b981", "bookopen"); mgr.create("آرشیو اسناد", "#f59e0b", "folder")
for cat, _ in svc.distinct("category"):
    sid = svc.add_shelf(cat)
    for b in svc.books("b.category=?", (cat,)):
        svc.add_to_shelf(sid, b["id"])
ctx.booksChanged.emit()
def pump(n=10):
    for _ in range(n): app.processEvents(); time.sleep(0.02)
for name, page in (("dashboard", win.p_dash), ("all_books", win.p_all), ("shelf", win.p_shelf), ("libraries", win.p_libs),
                   ("assistant", win.p_ai), ("settings", win.p_set), ("backup", win.p_backup)):
    win.stack.setCurrentWidget(page); pump(); win.grab().save(str(OUT / f"{name}.png"))
win.search.setText("lorem"); win.do_search(); pump(); win.grab().save(str(OUT / "search.png"))
win.p_all.set_view("list"); win.stack.setCurrentWidget(win.p_all); pump(); win.grab().save(str(OUT / "list.png"))
ctx.openBook.emit(ctx.lib_id, svc.books()[0]["id"], 2); pump()
r = next(iter(win.readers.values())); r.resize(1200, 850); pump()
r.pv.set_fit("width"); r.side.setVisible(True); pump(); r.grab().save(str(OUT / "reader.png"))
print("saved", sorted(p.name for p in OUT.iterdir()))
