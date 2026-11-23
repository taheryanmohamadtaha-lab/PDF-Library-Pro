"""ZIP backup & non-destructive restore."""
import json
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from ..core.config import APP_VERSION
from ..libraries.manager import LibraryManager


def _add_library(zf: zipfile.ZipFile, mgr: LibraryManager, lib, prefix: str, include_archive: bool):
    db, svc = mgr.open(lib["id"])
    with tempfile.TemporaryDirectory() as td:
        snap = Path(td) / "library.db"
        db.snapshot_to(snap)
        zf.write(snap, f"{prefix}library.db")
    for c in svc.covers.glob("*.jpg"):
        zf.write(c, f"{prefix}covers/{c.name}")
    if include_archive and svc.archive.exists():
        for f in svc.archive.iterdir():
            zf.write(f, f"{prefix}archive/{f.name}")
    # human-readable notes/bookmarks export (independent of the DB format)
    export = {"notes": [dict(r) for r in svc.notes()],
              "bookmarks": [dict(r) for r in db.q("SELECT * FROM bookmarks")],
              "highlights": [dict(r) for r in db.q("SELECT * FROM highlights")]}
    zf.writestr(f"{prefix}notes_export.json", json.dumps(export, ensure_ascii=False, indent=1))
    zf.writestr(f"{prefix}meta.json", json.dumps({"name": lib["name"], "color": lib["color"], "icon": lib["icon"]},
                                                 ensure_ascii=False))


def backup_library(mgr: LibraryManager, lib_id: int, dest_dir: Path, include_archive=True) -> Path:
    lib = mgr.get(lib_id)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"backup_{lib['name']}_{datetime.now():%Y%m%d_%H%M%S}.zip".replace("/", "_")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"kind": "library", "version": APP_VERSION}))
        _add_library(zf, mgr, lib, "", include_archive)
    mgr.central.set(f"last_backup_{lib_id}", datetime.now().isoformat(timespec="seconds"))
    mgr.central.set("last_backup", datetime.now().isoformat(timespec="seconds"))
    return out


def backup_all(mgr: LibraryManager, dest_dir: Path, include_archive=True) -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"backup_full_{datetime.now():%Y%m%d_%H%M%S}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({"kind": "full", "version": APP_VERSION}))
        # settings only; API keys are never stored in the central DB in clear text
        zf.writestr("settings.json", json.dumps({r["key"]: r["value"] for r in mgr.central.q("SELECT * FROM settings")
                                                  if "key" not in r["key"].lower()}, ensure_ascii=False))
        for lib in mgr.list():
            _add_library(zf, mgr, lib, f"libraries/{lib['id']}/", include_archive)
    mgr.central.set("last_backup", datetime.now().isoformat(timespec="seconds"))
    return out


def restore(mgr: LibraryManager, zip_path: Path) -> list[int]:
    """Restore as NEW libraries; existing data is never overwritten."""
    created = []
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            raise ValueError("not a PDF Library Pro backup")
        prefixes = sorted({n.rsplit("library.db", 1)[0] for n in names if n.endswith("library.db")})
        for pre in prefixes:
            meta = json.loads(zf.read(pre + "meta.json")) if pre + "meta.json" in names else {}
            lid = mgr.create((meta.get("name") or "Restored") + " (restored)", meta.get("color", "#7c5cff"),
                             meta.get("icon", "library"))
            mgr.close(lid)
            folder = Path(mgr.get(lid)["path"])
            for n in names:
                if n.startswith(pre) and not n.endswith("/") and (pre or "/" not in n or n.split("/")[0] in
                                                                    ("covers", "archive") or True):
                    rel = n[len(pre):]
                    if rel.split("/")[0] in ("library.db", "covers", "archive"):
                        target = folder / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(n) as src, open(target, "wb") as dst:
                            dst.write(src.read())
            # fix archive paths that referenced the old location
            db, svc = mgr.open(lid)
            for b in db.q("SELECT id,path FROM books"):
                fn = Path(b["path"]).name
                cand = svc.archive / fn
                if not Path(b["path"]).exists() and cand.exists():
                    db.x("UPDATE books SET path=? WHERE id=?", (str(cand), b["id"]))
            svc.check_missing()
            created.append(lid)
    return created
