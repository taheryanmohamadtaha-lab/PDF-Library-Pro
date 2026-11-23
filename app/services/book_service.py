"""Book operations for one library: add, index, edit, search, remove."""
import hashlib
import logging
import re
import shutil
from pathlib import Path
from typing import Callable, Optional

import pymupdf

from ..core.textnorm import fts_query, normalize
from ..database.library_db import LibraryDB

log = logging.getLogger("pdflp.books")
COVER_W = 420


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def split_text(text: str, limit: int = 1200) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for para in re.split(r"\n+", text):
        while len(para) > limit:
            cut = para.rfind(" ", 0, limit)
            cut = cut if cut > 200 else limit
            if cur:
                out.append(cur)
                cur = ""
            out.append(para[:cut])
            para = para[cut:].lstrip()
        if len(cur) + len(para) + 1 > limit and cur:
            out.append(cur)
            cur = ""
        cur = (cur + "\n" + para).strip()
    if cur:
        out.append(cur)
    return out


class BookService:
    def __init__(self, db: LibraryDB, libdir: Path):
        self.db = db
        self.libdir = Path(libdir)
        self.covers = self.libdir / "covers"
        self.archive = self.libdir / "archive"
        self.covers.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ add
    def add_pdf(self, path, mode: str = "link", source_dir: str = "") -> tuple[str, object]:
        """Returns ('added', id) | ('duplicate', id) | ('error', message)."""
        p = Path(path)
        try:
            if not p.is_file():
                return "error", "file not found"
            digest = sha256_file(p)
            row = self.db.one("SELECT id FROM books WHERE sha256=?", (digest,))
            if row:
                return "duplicate", row["id"]
            try:
                doc = pymupdf.open(str(p))
            except Exception as e:  # corrupt / not a pdf
                return "error", f"cannot open: {e}"
            encrypted = bool(doc.needs_pass)
            meta, pages = {}, 0
            if not encrypted:
                meta = doc.metadata or {}
                pages = doc.page_count
                if pages == 0:
                    doc.close()
                    return "error", "empty pdf"
            title = (meta.get("title") or "").strip()
            if not title or len(title) < 2 or title.lower().endswith((".pdf", ".doc", ".docx")):
                title = p.stem.replace("_", " ").strip()
            author = (meta.get("author") or "").strip()
            dest = p
            if mode in ("copy", "move"):
                self.archive.mkdir(exist_ok=True)
                dest = self.archive / p.name
                n = 1
                while dest.exists():
                    dest = self.archive / f"{p.stem}_{n}{p.suffix}"
                    n += 1
                shutil.copy2(p, dest)
                if sha256_file(dest) != digest:
                    dest.unlink(missing_ok=True)
                    doc.close()
                    return "error", "copy verification failed"
                if mode == "move":
                    try:
                        p.unlink()
                    except OSError as e:
                        log.warning("could not remove original after move: %s", e)
            bid = self.db.x(
                "INSERT INTO books(title,file_name,path,sha256,size,pages,author,publisher,description,encrypted,source_dir)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (title, p.name, str(dest), digest, dest.stat().st_size, pages, author,
                 "", (meta.get("subject") or "").strip(),
                 int(encrypted), source_dir or str(p.parent)))
            if not encrypted:
                self._make_cover(doc, bid)
            doc.close()
            self._refresh_books_fts(bid)
            return "added", bid
        except Exception as e:
            log.exception("add_pdf failed")
            return "error", str(e)

    def _make_cover(self, doc, bid: int, page_no: int = 0):
        try:
            page = doc[page_no]
            zoom = COVER_W / max(page.rect.width, 1)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            out = self.covers / f"{bid}.jpg"
            pix.save(str(out), jpg_quality=82)
            self.db.x("UPDATE books SET cover=? WHERE id=?", (out.name, bid))
        except Exception:
            log.exception("cover failed")

    def set_cover_from_image(self, bid: int, image_path: str):
        from PIL import Image
        im = Image.open(image_path).convert("RGB")
        im.thumbnail((COVER_W, COVER_W * 2))
        out = self.covers / f"{bid}.jpg"
        im.save(out, quality=85)
        self.db.x("UPDATE books SET cover=? WHERE id=?", (out.name, bid))

    def set_cover_from_page(self, bid: int, page_no: int, password: str = ""):
        b = self.book(bid)
        doc = pymupdf.open(b["path"])
        if doc.needs_pass and not doc.authenticate(password):
            raise ValueError("password")
        self._make_cover(doc, bid, page_no)
        doc.close()

    def cover_path(self, b) -> Optional[Path]:
        if b["cover"]:
            p = self.covers / b["cover"]
            return p if p.exists() else None
        return None

    # ---------------------------------------------------------------- index
    def index_book(self, bid: int, password: str = "", progress: Callable[[int, int], None] = None,
                   cancel: Callable[[], bool] = None) -> int:
        """Extract text of every page into FTS + RAG chunks. Returns pages that had no text."""
        b = self.book(bid)
        if not b or not Path(b["path"]).exists():
            return 0
        doc = pymupdf.open(b["path"])
        if doc.needs_pass and not (password and doc.authenticate(password)):
            doc.close()
            return 0
        n = doc.page_count
        empty = 0
        with self.db.lock:
            self.db.conn.execute("DELETE FROM pages_fts WHERE book_id=? AND page IN "
                                 "(SELECT page FROM file_index WHERE book_id=? AND ocr=0)", (bid, bid))
            self.db.conn.execute("DELETE FROM file_index WHERE book_id=? AND ocr=0", (bid,))
            self.db.conn.execute("DELETE FROM chunks_fts WHERE book_id=? AND chunk_id IN "
                                 "(SELECT id FROM document_chunks WHERE book_id=? AND page_start NOT IN "
                                 "(SELECT page FROM file_index WHERE book_id=? AND ocr=1))", (bid, bid, bid))
            self.db.conn.execute("DELETE FROM document_chunks WHERE book_id=? AND page_start NOT IN "
                                 "(SELECT page FROM file_index WHERE book_id=? AND ocr=1)", (bid, bid))
            for i in range(n):
                if cancel and cancel():
                    break
                txt = doc[i].get_text("text") or ""
                has = len(txt.strip()) > 20
                if has:
                    self._store_page(bid, i + 1, txt, ocr=0)
                else:
                    empty += 1
                    self.db.conn.execute("INSERT OR REPLACE INTO file_index VALUES(?,?,0,0)", (bid, i + 1))
                if i % 20 == 0:
                    self.db.conn.commit()
                    if progress:
                        progress(i + 1, n)
            else:
                self.db.conn.execute("UPDATE books SET indexed=1 WHERE id=?", (bid,))
            self.db.conn.commit()
        doc.close()
        if progress:
            progress(n, n)
        return empty

    def _store_page(self, bid: int, page: int, text: str, ocr: int):
        """Caller must hold db.lock."""
        c = self.db.conn
        c.execute("DELETE FROM pages_fts WHERE book_id=? AND page=?", (bid, page))
        c.execute("INSERT INTO pages_fts(text,book_id,page) VALUES(?,?,?)", (normalize(text), bid, page))
        c.execute("INSERT OR REPLACE INTO file_index VALUES(?,?,?,1)", (bid, page, ocr))
        for piece in split_text(text):
            cur = c.execute("INSERT INTO document_chunks(book_id,page_start,page_end,text) VALUES(?,?,?,?)",
                            (bid, page, page, piece))
            c.execute("INSERT INTO chunks_fts(text,chunk_id,book_id) VALUES(?,?,?)",
                      (normalize(piece), cur.lastrowid, bid))

    def store_ocr_page(self, bid: int, page: int, text: str):
        with self.db.lock:
            c = self.db.conn
            c.execute("DELETE FROM chunks_fts WHERE chunk_id IN (SELECT id FROM document_chunks "
                      "WHERE book_id=? AND page_start=?)", (bid, page))
            c.execute("DELETE FROM document_chunks WHERE book_id=? AND page_start=?", (bid, page))
            self._store_page(bid, page, text, ocr=1)
            c.commit()

    def pages_without_text(self, bid: int) -> list[int]:
        return [r[0] for r in self.db.q("SELECT page FROM file_index WHERE book_id=? AND has_text=0 ORDER BY page",
                                        (bid,))]

    # ----------------------------------------------------------------- read
    def book(self, bid: int):
        return self.db.one("SELECT * FROM books WHERE id=?", (bid,))

    def books(self, where: str = "", args=(), order: str = "added_at DESC"):
        sql = "SELECT b.*, COALESCE(p.percent,0) AS percent, COALESCE(p.page,0) AS cur_page FROM books b " \
              "LEFT JOIN reading_progress p ON p.book_id=b.id"
        if where:
            sql += " WHERE " + where
        sql += " ORDER BY " + order
        return self.db.q(sql, args)

    def tags_of(self, bid: int) -> list[str]:
        return [r[0] for r in self.db.q("SELECT t.name FROM tags t JOIN book_tags bt ON bt.tag_id=t.id "
                                        "WHERE bt.book_id=? ORDER BY t.name", (bid,))]

    def all_tags(self) -> list[str]:
        return [r[0] for r in self.db.q("SELECT name FROM tags ORDER BY name")]

    def update_book(self, bid: int, tags: list[str] = None, **fields):
        allowed = {"title", "author", "translator", "publisher", "category", "description", "favorite"}
        fields = {k: v for k, v in fields.items() if k in allowed}
        if fields:
            sets = ",".join(f"{k}=?" for k in fields)
            self.db.x(f"UPDATE books SET {sets} WHERE id=?", (*fields.values(), bid))
        for k in ("author", "category"):
            if fields.get(k):
                self.db.x(f"INSERT OR IGNORE INTO {'authors' if k == 'author' else 'categories'}(name) VALUES(?)",
                          (fields[k],))
        if tags is not None:
            with self.db.lock:
                self.db.conn.execute("DELETE FROM book_tags WHERE book_id=?", (bid,))
                for t in {t.strip() for t in tags if t.strip()}:
                    self.db.conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (t,))
                    tid = self.db.conn.execute("SELECT id FROM tags WHERE name=?", (t,)).fetchone()[0]
                    self.db.conn.execute("INSERT OR IGNORE INTO book_tags VALUES(?,?)", (bid, tid))
                self.db.conn.commit()
        self._refresh_books_fts(bid)

    def _refresh_books_fts(self, bid: int):
        b = self.book(bid)
        if not b:
            return
        vals = [normalize(str(b[k] or "")) for k in
                ("title", "file_name", "author", "translator", "publisher", "category")]
        vals.append(normalize(" ".join(self.tags_of(bid))))
        vals.append(normalize(b["description"] or ""))
        with self.db.lock:
            self.db.conn.execute("DELETE FROM books_fts WHERE book_id=?", (bid,))
            self.db.conn.execute("INSERT INTO books_fts(title,file_name,author,translator,publisher,category,tags,"
                                 "description,book_id) VALUES(?,?,?,?,?,?,?,?,?)", (*vals, bid))
            self.db.conn.commit()

    def touch_opened(self, bid: int, page: int):
        self.db.x("UPDATE books SET last_opened=CURRENT_TIMESTAMP WHERE id=?", (bid,))
        self.db.x("INSERT INTO reading_history(book_id,page) VALUES(?,?)", (bid, page))

    def save_progress(self, bid: int, page: int, total: int, zoom: float = 0, mode: str = "continuous"):
        pct = round(100 * page / max(total, 1), 1)
        self.db.x("INSERT INTO reading_progress(book_id,page,percent,zoom,mode,updated_at) "
                  "VALUES(?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(book_id) DO UPDATE SET page=excluded.page,"
                  "percent=excluded.percent,zoom=excluded.zoom,mode=excluded.mode,updated_at=CURRENT_TIMESTAMP",
                  (bid, page, pct, zoom, mode))

    def progress(self, bid: int):
        return self.db.one("SELECT * FROM reading_progress WHERE book_id=?", (bid,))

    # --------------------------------------------------------------- remove
    def remove_book(self, bid: int, delete_file: bool = False):
        b = self.book(bid)
        if not b:
            return
        with self.db.lock:
            c = self.db.conn
            c.execute("DELETE FROM pages_fts WHERE book_id=?", (bid,))
            c.execute("DELETE FROM books_fts WHERE book_id=?", (bid,))
            c.execute("DELETE FROM chunks_fts WHERE book_id=?", (bid,))
            c.execute("DELETE FROM notes_fts WHERE note_id IN (SELECT id FROM notes WHERE book_id=?)", (bid,))
            c.execute("DELETE FROM books WHERE id=?", (bid,))
            c.commit()
        cp = self.covers / (b["cover"] or "")
        if b["cover"] and cp.exists():
            cp.unlink(missing_ok=True)
        in_archive = self.archive in Path(b["path"]).parents
        if delete_file or in_archive:
            # archive copies belong to the library; originals only go with explicit user confirmation
            if in_archive or delete_file:
                Path(b["path"]).unlink(missing_ok=True)

    # ------------------------------------------------------- missing files
    def check_missing(self) -> int:
        n = 0
        for b in self.db.q("SELECT id,path,missing FROM books"):
            miss = 0 if Path(b["path"]).exists() else 1
            if miss != b["missing"]:
                self.db.x("UPDATE books SET missing=? WHERE id=?", (miss, b["id"]))
            n += miss
        return n

    def relocate_book(self, bid: int, new_path: str) -> bool:
        b = self.book(bid)
        p = Path(new_path)
        if not b or not p.is_file() or sha256_file(p) != b["sha256"]:
            return False
        self.db.x("UPDATE books SET path=?, file_name=?, missing=0 WHERE id=?", (str(p), p.name, bid))
        return True

    def relocate_in_folder(self, folder: str) -> int:
        """Look for moved files (same SHA-256) under a folder."""
        missing = {b["sha256"]: b["id"] for b in self.db.q("SELECT id,sha256 FROM books WHERE missing=1")}
        sizes = {b["size"] for b in self.db.q("SELECT size FROM books WHERE missing=1")}
        found = 0
        if not missing:
            return 0
        for f in Path(folder).rglob("*.pdf"):
            try:
                if f.stat().st_size not in sizes:
                    continue
                h = sha256_file(f)
            except OSError:
                continue
            if h in missing and self.relocate_book(missing[h], str(f)):
                found += 1
        return found

    # --------------------------------------------------------------- search
    def search(self, text: str, limit: int = 60) -> dict:
        """Returns {'books': [rows], 'pages': [{book_id,page,snippet}], 'notes': [...]}"""
        q = fts_query(text)
        if not q:
            return {"books": [], "pages": [], "notes": []}
        try:
            ids = [r[0] for r in self.db.q("SELECT book_id FROM books_fts WHERE books_fts MATCH ? LIMIT ?",
                                           (q, limit))]
            pages = [dict(r) for r in self.db.q(
                "SELECT book_id, page, snippet(pages_fts,0,'[',']','…',12) AS snippet FROM pages_fts "
                "WHERE pages_fts MATCH ? ORDER BY rank LIMIT ?", (q, limit))]
            notes = [dict(r) for r in self.db.q(
                "SELECT n.id, n.book_id, n.page, n.kind, n.text FROM notes_fts f JOIN notes n ON n.id=f.note_id "
                "WHERE notes_fts MATCH ? LIMIT ?", (q, limit))]
        except Exception:
            log.exception("search failed")
            return {"books": [], "pages": [], "notes": []}
        books = [self.book(i) for i in ids]
        return {"books": [b for b in books if b], "pages": pages, "notes": notes}

    def suggest(self, prefix: str, limit: int = 8) -> list[str]:
        q = fts_query(prefix)
        if not q:
            return []
        rows = self.db.q("SELECT b.title FROM books_fts f JOIN books b ON b.id=f.book_id "
                         "WHERE books_fts MATCH ? LIMIT ?", (q, limit))
        return [r[0] for r in rows]

    # ------------------------------------------------- bookmarks / notes
    def add_bookmark(self, bid, page, label=""):
        return self.db.x("INSERT INTO bookmarks(book_id,page,label) VALUES(?,?,?)", (bid, page, label))

    def bookmarks(self, bid):
        return self.db.q("SELECT * FROM bookmarks WHERE book_id=? ORDER BY page", (bid,))

    def delete_bookmark(self, bm_id):
        self.db.x("DELETE FROM bookmarks WHERE id=?", (bm_id,))

    def add_note(self, bid, page, text, kind="note"):
        nid = self.db.x("INSERT INTO notes(book_id,page,kind,text) VALUES(?,?,?,?)", (bid, page, kind, text))
        self.db.x("INSERT INTO notes_fts(text,note_id) VALUES(?,?)", (normalize(text), nid))
        return nid

    def update_note(self, nid, text):
        self.db.x("UPDATE notes SET text=? WHERE id=?", (text, nid))
        self.db.x("DELETE FROM notes_fts WHERE note_id=?", (nid,))
        self.db.x("INSERT INTO notes_fts(text,note_id) VALUES(?,?)", (normalize(text), nid))

    def delete_note(self, nid):
        self.db.x("DELETE FROM notes WHERE id=?", (nid,))
        self.db.x("DELETE FROM notes_fts WHERE note_id=?", (nid,))

    def notes(self, bid=None, kind=None):
        sql, args = "SELECT n.*, b.title FROM notes n JOIN books b ON b.id=n.book_id", []
        cond = []
        if bid:
            cond.append("n.book_id=?")
            args.append(bid)
        if kind:
            cond.append("n.kind=?")
            args.append(kind)
        if cond:
            sql += " WHERE " + " AND ".join(cond)
        return self.db.q(sql + " ORDER BY n.created_at DESC", args)

    def add_highlight(self, bid, page, rect, color, text=""):
        return self.db.x("INSERT INTO highlights(book_id,page,x0,y0,x1,y1,color,text) VALUES(?,?,?,?,?,?,?,?)",
                         (bid, page, *rect, color, text))

    def highlights(self, bid, page=None):
        if page is None:
            return self.db.q("SELECT * FROM highlights WHERE book_id=? ORDER BY page", (bid,))
        return self.db.q("SELECT * FROM highlights WHERE book_id=? AND page=?", (bid, page))

    def delete_highlight(self, hid):
        self.db.x("DELETE FROM highlights WHERE id=?", (hid,))

    def export_notes(self, bid, dest: Path, fmt="md"):
        b = self.book(bid)
        lines = [f"# {b['title']}", ""]
        for n in self.notes(bid):
            lines.append(f"- [{n['kind']}] p.{n['page']}: {n['text']}")
        for h in self.highlights(bid):
            if h["text"]:
                lines.append(f"- [highlight] p.{h['page']}: {h['text']}")
        for bm in self.bookmarks(bid):
            lines.append(f"- [bookmark] p.{bm['page']}: {bm['label']}")
        Path(dest).write_text("\n".join(lines), encoding="utf-8")

    # ---------------------------------------------------------- stats/lists
    def stats(self) -> dict:
        r = self.db.one("SELECT COUNT(*) n, COALESCE(SUM(pages),0) p, COALESCE(SUM(size),0) s FROM books")
        return {"books": r["n"], "pages": r["p"], "size": r["s"],
                "favorites": self.db.one("SELECT COUNT(*) FROM books WHERE favorite=1")[0],
                "notes": self.db.one("SELECT COUNT(*) FROM notes")[0],
                "bookmarks": self.db.one("SELECT COUNT(*) FROM bookmarks")[0],
                "reading": self.db.one("SELECT COUNT(*) FROM reading_progress WHERE percent>0 AND percent<100")[0]}

    def distinct(self, col: str) -> list[tuple[str, int]]:
        assert col in ("author", "category", "publisher", "source_dir", "translator")
        return [(r[0], r[1]) for r in self.db.q(
            f"SELECT {col}, COUNT(*) FROM books WHERE {col}<>'' GROUP BY {col} ORDER BY COUNT(*) DESC, {col}")]

    # --------------------------------------------------------------- shelves
    def shelves(self):
        return self.db.q("SELECT * FROM shelves ORDER BY position, id")

    def add_shelf(self, name, style="wood", color="#8a5a2b"):
        return self.db.x("INSERT INTO shelves(name,style,color,position) VALUES(?,?,?,"
                         "(SELECT COALESCE(MAX(position),0)+1 FROM shelves))", (name, style, color))

    def update_shelf(self, sid, **f):
        for k, v in f.items():
            if k in ("name", "style", "color"):
                self.db.x(f"UPDATE shelves SET {k}=? WHERE id=?", (v, sid))

    def delete_shelf(self, sid):
        self.db.x("DELETE FROM shelves WHERE id=?", (sid,))

    def shelf_books(self, sid):
        return self.db.q("SELECT b.* FROM shelf_books s JOIN books b ON b.id=s.book_id WHERE s.shelf_id=? "
                         "ORDER BY s.position", (sid,))

    def set_shelf_order(self, sid, book_ids: list[int]):
        with self.db.lock:
            self.db.conn.execute("DELETE FROM shelf_books WHERE shelf_id=?", (sid,))
            self.db.conn.executemany("INSERT OR IGNORE INTO shelf_books VALUES(?,?,?)",
                                     [(sid, b, i) for i, b in enumerate(book_ids)])
            self.db.conn.commit()

    def add_to_shelf(self, sid, bid):
        ids = [b["id"] for b in self.shelf_books(sid)]
        if bid not in ids:
            self.set_shelf_order(sid, ids + [bid])

    def remove_from_shelf(self, sid, bid):
        self.set_shelf_order(sid, [b["id"] for b in self.shelf_books(sid) if b["id"] != bid])
