# -*- coding: utf-8 -*-
"""Orphan detection & cleanup (P1-6).

An "orphan" is one of two things:
  * a physical file under ``UPLOAD_DIR`` that no ``files.filepath`` row
    references (disk orphan), or
  * a ``files`` row whose ``filepath`` does not exist on disk (DB orphan).

Both forms come from the non-atomic upload/delete paths this module's sibling
cleanup task (ARCH-7) is designed to minimise. Here we provide:
  * ``find_disk_orphans`` / ``find_db_orphans`` — pure detection,
  * ``run_cleanup`` — a dry-run preview or a real deletion (audit-logged),
  * ``scan_and_report`` — used by the optional background sweep in ``main.py``.
"""

import logging
from pathlib import Path

from sqlalchemy import select

from app.config import UPLOAD_DIR
from app.database import File as FileModel

log = logging.getLogger("fileserver.cleanup")

# Temporary upload files written by the atomic save path start with this prefix;
# they are transient, not orphans, and must never be reported/removed by cleanup.
_TMP_PREFIX = ".tmp_"


def find_disk_orphans(db) -> list[Path]:
    """Return physical files under UPLOAD_DIR not referenced by any file row."""
    valid = {r[0] for r in db.execute(select(FileModel.filepath)).all()}
    orphans: list[Path] = []
    for p in UPLOAD_DIR.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith(_TMP_PREFIX):
            continue
        rel = str(p.relative_to(UPLOAD_DIR)).replace("\\", "/")
        if rel not in valid:
            orphans.append(p)
    return orphans


def find_db_orphans(db) -> list[FileModel]:
    """Return ``files`` rows whose ``filepath`` is missing on disk."""
    rows = db.execute(select(FileModel)).scalars().all()
    return [r for r in rows if not (UPLOAD_DIR / r.filepath).exists()]


def run_cleanup(db, target: str = "both", dry_run: bool = True) -> dict:
    """Detect orphans and optionally remove them.

    ``target`` is one of ``"disk"`` / ``"db"`` / ``"both"``.
    When ``dry_run`` is True nothing is deleted and the caller should only
    inspect the returned counts / sample paths.
    """
    disk = find_disk_orphans(db) if target in ("disk", "both") else []
    drows = find_db_orphans(db) if target in ("db", "both") else []

    deleted_disk = 0
    deleted_db = 0
    if not dry_run:
        for p in disk:
            try:
                p.unlink()
                deleted_disk += 1
            except OSError as exc:
                log.warning("Failed to remove disk orphan %s: %s", p, exc)
        if drows:
            for r in drows:
                db.delete(r)
            db.commit()
            deleted_db = len(drows)

    return {
        "dry_run": dry_run,
        "target": target,
        "disk_orphan_count": len(disk),
        "disk_orphan_samples": [str(p.relative_to(UPLOAD_DIR)) for p in disk[:20]],
        "db_orphan_count": len(drows),
        "deleted_disk": deleted_disk,
        "deleted_db": deleted_db,
    }


def scan_and_report() -> dict:
    """Run detection (no deletion) and return a summary for logging."""
    with db_session() as db:
        disk = find_disk_orphans(db)
        drows = find_db_orphans(db)
    summary = {"disk_orphans": len(disk), "db_orphans": len(drows)}
    if summary["disk_orphans"] or summary["db_orphans"]:
        log.warning("Orphan scan: %s disk orphans, %s DB orphans", len(disk), len(drows))
    else:
        log.info("Orphan scan: none found")
    return summary


# Lazily import the session factory to avoid a circular import at module load
# (database.py imports from config, not from us, but keeping this local is safe).
def db_session():
    from app.database import SessionLocal
    return SessionLocal()
