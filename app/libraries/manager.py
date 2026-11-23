"""Multi-library manager: independent DB per library + central registry."""
import logging
import shutil
from pathlib import Path
from typing import Optional

from ..core.config import data_dir
from ..database.central import CentralDB
from ..database.library_db import LibraryDB
from ..services.book_service import BookService

log = logging.getLogger("pdflp.libs")


class LibraryManager:
    def __init__(self, home: Optional[Path] = None):
        self.home = Path(home) if home else data_dir()
        self.home.mkdir(parents=True, exist_ok=True)
        self.central = CentralDB(self.home / "central.db")
        self._open: dict[int, tuple[LibraryDB, BookService]] = {}
        if not self.list():
            self.create("کتابخانه شخصی", "#7c5cff", "library", default=True)

    # ------------------------------------------------------------- registry
    def list(self):
        return self.central.q("SELECT * FROM libraries ORDER BY position, id")

    def get(self, lib_id: int):
        return self.central.one("SELECT * FROM libraries WHERE id=?", (lib_id,))

    def default_id(self) -> int:
        r = self.central.one("SELECT id FROM libraries WHERE is_default=1")
        return r["id"] if r else self.list()[0]["id"]

    def create(self, name: str, color="#7c5cff", icon="library", path: str = "", default=False) -> int:
        name = name.strip() or "Library"
        lid = self.central.x("INSERT INTO libraries(name,color,icon,path,position) VALUES(?,?,?,?,"
                             "(SELECT COALESCE(MAX(position),0)+1 FROM libraries))", (name, color, icon, "tmp"))
        folder = Path(path) if path else self.home / "libraries" / str(lid)
        folder.mkdir(parents=True, exist_ok=True)
        self.central.x("UPDATE libraries SET path=? WHERE id=?", (str(folder), lid))
        LibraryDB(folder / "library.db").close()  # create + migrate
        if default or len(self.list()) == 1:
            self.set_default(lid)
        return lid

    def update(self, lib_id: int, **f):
        for k, v in f.items():
            if k in ("name", "color", "icon"):
                self.central.x(f"UPDATE libraries SET {k}=? WHERE id=?", (v, lib_id))

    def set_default(self, lib_id: int):
        self.central.x("UPDATE libraries SET is_default=0")
        self.central.x("UPDATE libraries SET is_default=1 WHERE id=?", (lib_id,))

    def delete(self, lib_id: int, delete_data: bool = True):
        """Removes the library. User's original PDFs outside the archive are never touched."""
        if len(self.list()) <= 1:
            raise ValueError("cannot delete the last library")
        lib = self.get(lib_id)
        self.close(lib_id)
        self.central.x("DELETE FROM libraries WHERE id=?", (lib_id,))
        if delete_data and lib:
            shutil.rmtree(lib["path"], ignore_errors=True)
        if not self.central.one("SELECT 1 FROM libraries WHERE is_default=1"):
            self.set_default(self.list()[0]["id"])

    # ---------------------------------------------------------------- access
    def open(self, lib_id: int) -> tuple[LibraryDB, BookService]:
        if lib_id not in self._open:
            lib = self.get(lib_id)
            folder = Path(lib["path"])
            db = LibraryDB(folder / "library.db")
            self._open[lib_id] = (db, BookService(db, folder))
        return self._open[lib_id]

    def service(self, lib_id: int) -> BookService:
        return self.open(lib_id)[1]

    def close(self, lib_id: int):
        if lib_id in self._open:
            self._open.pop(lib_id)[0].close()

    def close_all(self):
        for k in list(self._open):
            self.close(k)
        self.central.close()

    def stats(self, lib_id: int) -> dict:
        return self.service(lib_id).stats()

    # ---------------------------------------------------------------- moving
    def move_book(self, book_id: int, src_id: int, dst_id: int) -> tuple[bool, str]:
        """Move a book with notes, bookmarks, highlights, progress, history and text index."""
        if src_id == dst_id:
            return False, "same library"
        sdb, ssvc = self.open(src_id)
        ddb, dsvc = self.open(dst_id)
        b = ssvc.book(book_id)
        if not b:
            return False, "not found"
        if ddb.one("SELECT id FROM books WHERE sha256=?", (b["sha256"],)):
            return False, "duplicate"
        path = Path(b["path"])
        new_path = b["path"]
        if ssvc.archive in path.parents and path.exists():
            dsvc.archive.mkdir(exist_ok=True)
            dest = dsvc.archive / path.name
            n = 1
            while dest.exists():
                dest = dsvc.archive / f"{path.stem}_{n}{path.suffix}"
                n += 1
            shutil.copy2(path, dest)
            new_path = str(dest)
        cols = [c for c in b.keys() if c not in ("id",)]
        with ddb.lock:
            c = ddb.conn
            try:
                cur = c.execute(f"INSERT INTO books({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                                [new_path if k == "path" else b[k] for k in cols])
                nid = cur.lastrowid
                for t in ssvc.tags_of(book_id):
                    c.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (t,))
                    tid = c.execute("SELECT id FROM tags WHERE name=?", (t,)).fetchone()[0]
                    c.execute("INSERT OR IGNORE INTO book_tags VALUES(?,?)", (nid, tid))
                for r in sdb.q("SELECT page,label,created_at FROM bookmarks WHERE book_id=?", (book_id,)):
                    c.execute("INSERT INTO bookmarks(book_id,page,label,created_at) VALUES(?,?,?,?)", (nid, *r))
                for r in sdb.q("SELECT page,kind,text,created_at FROM notes WHERE book_id=?", (book_id,)):
                    cur = c.execute("INSERT INTO notes(book_id,page,kind,text,created_at) VALUES(?,?,?,?,?)",
                                    (nid, *r))
                    from ..core.textnorm import normalize
                    c.execute("INSERT INTO notes_fts(text,note_id) VALUES(?,?)", (normalize(r["text"]), cur.lastrowid))
                for r in sdb.q("SELECT page,x0,y0,x1,y1,color,text,created_at FROM highlights WHERE book_id=?",
                               (book_id,)):
                    c.execute("INSERT INTO highlights(book_id,page,x0,y0,x1,y1,color,text,created_at) "
                              "VALUES(?,?,?,?,?,?,?,?,?)", (nid, *r))
                for r in sdb.q("SELECT page,percent,zoom,mode,updated_at FROM reading_progress WHERE book_id=?",
                               (book_id,)):
                    c.execute("INSERT INTO reading_progress(book_id,page,percent,zoom,mode,updated_at) "
                              "VALUES(?,?,?,?,?,?)", (nid, *r))
                for r in sdb.q("SELECT page,opened_at FROM reading_history WHERE book_id=?", (book_id,)):
                    c.execute("INSERT INTO reading_history(book_id,page,opened_at) VALUES(?,?,?)", (nid, *r))
                for r in sdb.q("SELECT page,ocr,has_text FROM file_index WHERE book_id=?", (book_id,)):
                    c.execute("INSERT OR REPLACE INTO file_index VALUES(?,?,?,?)", (nid, *r))
                for r in sdb.q("SELECT text,page FROM pages_fts WHERE book_id=?", (book_id,)):
                    c.execute("INSERT INTO pages_fts(text,book_id,page) VALUES(?,?,?)", (r["text"], nid, r["page"]))
                for r in sdb.q("SELECT id,page_start,page_end,text FROM document_chunks WHERE book_id=?", (book_id,)):
                    cur = c.execute("INSERT INTO document_chunks(book_id,page_start,page_end,text) VALUES(?,?,?,?)",
                                    (nid, r["page_start"], r["page_end"], r["text"]))
                    from ..core.textnorm import normalize as nz
                    c.execute("INSERT INTO chunks_fts(text,chunk_id,book_id) VALUES(?,?,?)",
                              (nz(r["text"]), cur.lastrowid, nid))
                if b["category"]:
                    c.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (b["category"],))
                if b["author"]:
                    c.execute("INSERT OR IGNORE INTO authors(name) VALUES(?)", (b["author"],))
                c.commit()
            except Exception:
                c.rollback()
                log.exception("move_book failed")
                return False, "database error"
        cover = ssvc.cover_path(b)
        if cover:
            shutil.copy2(cover, dsvc.covers / f"{nid}.jpg")
            ddb.x("UPDATE books SET cover=? WHERE id=?", (f"{nid}.jpg", nid))
        dsvc._refresh_books_fts(nid)
        # remove from source without deleting the physical file (it now lives in dst or at original path)
        with sdb.lock:
            sdb.conn.execute("DELETE FROM pages_fts WHERE book_id=?", (book_id,))
            sdb.conn.execute("DELETE FROM books_fts WHERE book_id=?", (book_id,))
            sdb.conn.execute("DELETE FROM chunks_fts WHERE book_id=?", (book_id,))
            sdb.conn.execute("DELETE FROM notes_fts WHERE note_id IN (SELECT id FROM notes WHERE book_id=?)",
                             (book_id,))
            sdb.conn.execute("DELETE FROM books WHERE id=?", (book_id,))
            sdb.conn.commit()
        if cover:
            cover.unlink(missing_ok=True)
        if ssvc.archive in path.parents and new_path != b["path"]:
            path.unlink(missing_ok=True)
        return True, str(nid)
