"""Per-library SQLite database with simple versioned migrations."""
import sqlite3
import threading
from pathlib import Path

MIGRATIONS = [
    # ---- v1 ----
    """
    CREATE TABLE books(
        id INTEGER PRIMARY KEY, title TEXT NOT NULL, file_name TEXT, path TEXT, sha256 TEXT UNIQUE,
        size INTEGER DEFAULT 0, pages INTEGER DEFAULT 0, author TEXT DEFAULT '', translator TEXT DEFAULT '',
        publisher TEXT DEFAULT '', category TEXT DEFAULT '', description TEXT DEFAULT '', cover TEXT DEFAULT '',
        favorite INTEGER DEFAULT 0, encrypted INTEGER DEFAULT 0, missing INTEGER DEFAULT 0,
        indexed INTEGER DEFAULT 0, source_dir TEXT DEFAULT '', added_at TEXT DEFAULT CURRENT_TIMESTAMP,
        last_opened TEXT);
    CREATE TABLE authors(id INTEGER PRIMARY KEY, name TEXT UNIQUE);
    CREATE TABLE categories(id INTEGER PRIMARY KEY, name TEXT UNIQUE, parent TEXT DEFAULT '');
    CREATE TABLE tags(id INTEGER PRIMARY KEY, name TEXT UNIQUE);
    CREATE TABLE book_tags(book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
        tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE, PRIMARY KEY(book_id, tag_id));
    CREATE TABLE shelves(id INTEGER PRIMARY KEY, name TEXT NOT NULL, style TEXT DEFAULT 'wood',
        color TEXT DEFAULT '#8a5a2b', position INTEGER DEFAULT 0);
    CREATE TABLE shelf_books(shelf_id INTEGER REFERENCES shelves(id) ON DELETE CASCADE,
        book_id INTEGER REFERENCES books(id) ON DELETE CASCADE, position INTEGER DEFAULT 0,
        PRIMARY KEY(shelf_id, book_id));
    CREATE TABLE bookmarks(id INTEGER PRIMARY KEY, book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
        page INTEGER, label TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE notes(id INTEGER PRIMARY KEY, book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
        page INTEGER DEFAULT 0, kind TEXT DEFAULT 'note', text TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE highlights(id INTEGER PRIMARY KEY, book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
        page INTEGER, x0 REAL, y0 REAL, x1 REAL, y1 REAL, color TEXT DEFAULT '#ffe066', text TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE reading_progress(book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
        page INTEGER DEFAULT 0, percent REAL DEFAULT 0, zoom REAL DEFAULT 0, mode TEXT DEFAULT 'continuous',
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE reading_history(id INTEGER PRIMARY KEY, book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
        page INTEGER, opened_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE file_index(book_id INTEGER REFERENCES books(id) ON DELETE CASCADE, page INTEGER,
        ocr INTEGER DEFAULT 0, has_text INTEGER DEFAULT 0, PRIMARY KEY(book_id, page));
    CREATE VIRTUAL TABLE pages_fts USING fts5(text, book_id UNINDEXED, page UNINDEXED, tokenize='unicode61');
    CREATE VIRTUAL TABLE books_fts USING fts5(title, file_name, author, translator, publisher, category, tags,
        description, book_id UNINDEXED, tokenize='unicode61');
    CREATE VIRTUAL TABLE notes_fts USING fts5(text, note_id UNINDEXED, tokenize='unicode61');
    CREATE TABLE document_chunks(id INTEGER PRIMARY KEY, book_id INTEGER REFERENCES books(id) ON DELETE CASCADE,
        page_start INTEGER, page_end INTEGER, text TEXT);
    CREATE VIRTUAL TABLE chunks_fts USING fts5(text, chunk_id UNINDEXED, book_id UNINDEXED, tokenize='unicode61');
    CREATE TABLE embeddings_metadata(chunk_id INTEGER PRIMARY KEY, model TEXT, dim INTEGER, vector BLOB);
    CREATE TABLE ai_conversations(id INTEGER PRIMARY KEY, title TEXT, book_ids TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE ai_messages(id INTEGER PRIMARY KEY, conversation_id INTEGER REFERENCES ai_conversations(id)
        ON DELETE CASCADE, role TEXT, content TEXT, sources TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE INDEX idx_books_cat ON books(category); CREATE INDEX idx_books_author ON books(author);
    CREATE INDEX idx_notes_book ON notes(book_id); CREATE INDEX idx_chunks_book ON document_chunks(book_id);
    """,
]


class LibraryDB:
    """Thread-safe wrapper around one library's SQLite file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self):
        with self.lock:
            ver = self.conn.execute("PRAGMA user_version").fetchone()[0]
            for i in range(ver, len(MIGRATIONS)):
                self.conn.executescript("BEGIN;" + MIGRATIONS[i] + "COMMIT;")
                self.conn.execute(f"PRAGMA user_version={i + 1}")
            self.conn.commit()

    def q(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchone()

    def x(self, sql, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur.lastrowid

    def many(self, sql, rows):
        with self.lock:
            self.conn.executemany(sql, rows)
            self.conn.commit()

    def get_setting(self, key, default=None):
        r = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return r[0] if r else default

    def set_setting(self, key, value):
        self.x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, str(value)))

    def integrity_ok(self) -> bool:
        return self.one("PRAGMA integrity_check")[0] == "ok"

    def snapshot_to(self, dest: Path):
        """Consistent copy using SQLite's online backup API."""
        with self.lock:
            out = sqlite3.connect(str(dest))
            try:
                self.conn.backup(out)
            finally:
                out.close()

    def close(self):
        with self.lock:
            try:
                self.conn.commit()
                self.conn.close()
            except Exception:
                pass
