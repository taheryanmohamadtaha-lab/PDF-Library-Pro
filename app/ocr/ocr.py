"""Optional OCR through an installed Tesseract (never modifies the PDF)."""
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional

import pymupdf

from ..services.book_service import BookService

log = logging.getLogger("pdflp.ocr")
WIN_PATHS = [r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"]


def find_tesseract() -> Optional[str]:
    env = os.environ.get("TESSERACT_CMD")
    if env and Path(env).exists():
        return env
    exe = shutil.which("tesseract")
    if exe:
        return exe
    for p in WIN_PATHS:
        if Path(p).exists():
            return p
    return None


def available_langs(exe: str) -> list[str]:
    try:
        out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=15).stdout
        return [l.strip() for l in out.splitlines()[1:] if l.strip()]
    except Exception:
        return []


def ocr_pages(svc: BookService, bid: int, pages: Optional[list[int]] = None, langs: str = "fas+eng",
              password: str = "", progress: Callable[[int, int], None] = None,
              cancel: Callable[[], bool] = None) -> tuple[int, str]:
    """Returns (pages_done, message)."""
    exe = find_tesseract()
    if not exe:
        return 0, "tesseract-not-installed"
    have = set(available_langs(exe))
    wanted = [l for l in langs.split("+") if l in have] or (["eng"] if "eng" in have else [])
    if not wanted:
        return 0, "no-language-data"
    b = svc.book(bid)
    doc = pymupdf.open(b["path"])
    if doc.needs_pass and not doc.authenticate(password):
        return 0, "password"
    todo = pages or svc.pages_without_text(bid)
    done = 0
    with tempfile.TemporaryDirectory() as td:
        for i, pno in enumerate(todo):
            if cancel and cancel():
                break
            img = Path(td) / "p.png"
            doc[pno - 1].get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), alpha=False).save(str(img))
            flags = 0x08000000 if sys.platform.startswith("win") else 0  # CREATE_NO_WINDOW
            try:
                r = subprocess.run([exe, str(img), "stdout", "-l", "+".join(wanted)], capture_output=True,
                                   timeout=180, creationflags=flags)
                text = r.stdout.decode("utf-8", "ignore")
            except Exception:
                log.exception("tesseract failed on page %s", pno)
                continue
            if text.strip():
                svc.store_ocr_page(bid, pno, text)
                done += 1
            if progress:
                progress(i + 1, len(todo))
    doc.close()
    return done, "ok"
