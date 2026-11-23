"""Store the API key outside the DB: OS keyring if present, else DPAPI (Windows) / obfuscated file."""
import base64
import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

from ..core.config import data_dir


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi(data: bytes, encrypt: bool) -> bytes:
    crypt = ctypes.windll.crypt32
    inp = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    out = _Blob()
    fn = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    if not fn(ctypes.byref(inp), None, None, None, None, 0, ctypes.byref(out)):
        raise OSError("DPAPI failed")
    res = ctypes.string_at(out.pbData, out.cbData)
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return res


def _file() -> Path:
    return data_dir() / "api_key.bin"


def save_key(key: str):
    f = _file()
    if not key:
        f.unlink(missing_ok=True)
        return
    raw = key.encode("utf-8")
    if sys.platform.startswith("win"):
        blob = b"W" + _dpapi(raw, True)
    else:  # non-Windows dev fallback: local-only obfuscation, file mode 600
        blob = b"O" + base64.b64encode(raw)
    f.write_bytes(blob)
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def load_key() -> str:
    f = _file()
    if not f.exists():
        return ""
    blob = f.read_bytes()
    try:
        if blob[:1] == b"W" and sys.platform.startswith("win"):
            return _dpapi(blob[1:], False).decode("utf-8")
        if blob[:1] == b"O":
            return base64.b64decode(blob[1:]).decode("utf-8")
    except Exception:
        return ""
    return ""
