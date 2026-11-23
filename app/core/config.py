"""Paths, logging and app constants."""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "PDF Library Pro"
APP_VERSION = "1.0.0"


def data_dir() -> Path:
    env = os.environ.get("PDFLP_HOME")
    if env:
        p = Path(env)
    elif sys.platform.startswith("win"):
        p = Path(os.environ.get("APPDATA", str(Path.home()))) / "PDFLibraryPro"
    else:
        p = Path.home() / ".pdflibrarypro"
    p.mkdir(parents=True, exist_ok=True)
    return p


def resource_path(*parts: str) -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "app" / "resources" / Path(*parts)
    return Path(__file__).resolve().parents[1] / "resources" / Path(*parts)


def setup_logging() -> logging.Logger:
    log = logging.getLogger("pdflp")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    logdir = data_dir() / "logs"
    logdir.mkdir(exist_ok=True)
    h = RotatingFileHandler(logdir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(h)

    def hook(et, ev, tb):
        log.error("Unhandled exception", exc_info=(et, ev, tb))
        sys.__excepthook__(et, ev, tb)

    sys.excepthook = hook
    return log
