"""Central database: library registry + global settings."""
import hashlib
import os
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS libraries(id INTEGER PRIMARY KEY, name TEXT NOT NULL, color TEXT DEFAULT '#7c5cff',
  icon TEXT DEFAULT 'library', path TEXT NOT NULL, is_default INTEGER DEFAULT 0, pw_hash TEXT DEFAULT '',
  pw_salt TEXT DEFAULT '', position INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""


def hash_pw(pw: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, 120_000).hex()


class CentralDB:
    def __init__(self, path: Path):
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
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

    def get(self, key, default=None):
        r = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return r[0] if r else default

    def set(self, key, value):
        self.x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, str(value)))

    def set_password(self, lib_id: int, pw: str):
        if not pw:
            self.x("UPDATE libraries SET pw_hash='', pw_salt='' WHERE id=?", (lib_id,))
            return
        salt = os.urandom(16)
        self.x("UPDATE libraries SET pw_hash=?, pw_salt=? WHERE id=?", (hash_pw(pw, salt), salt.hex(), lib_id))

    def check_password(self, lib_id: int, pw: str) -> bool:
        r = self.one("SELECT pw_hash, pw_salt FROM libraries WHERE id=?", (lib_id,))
        if not r or not r["pw_hash"]:
            return True
        return hash_pw(pw, bytes.fromhex(r["pw_salt"])) == r["pw_hash"]

    def close(self):
        with self.lock:
            self.conn.commit()
            self.conn.close()
