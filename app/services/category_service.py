# -*- coding: utf-8 -*-
"""Category business logic (ARCH-6).

List / delete / organize operations on the file-category structure. The route
handlers in :mod:`app.categories` keep the RBAC ``Depends`` guards and response
wrapping; the work happens here.
"""

import os
import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.config as _cfg
from app.database import ExtCategory, File as FileModel, SessionLocal, orm_to_dict
from app.utils import _audit_log, _delete_file, _delete_tree


def list_categories(db: Session) -> list[dict]:
    """Return all categories with file count and total size, sorted by name."""
    rows = (
        db.execute(
            select(
                FileModel.category.label("category"),
                func.count().label("count"),
                func.coalesce(func.sum(FileModel.size), 0).label("total_size"),
            )
            .group_by(FileModel.category)
            .order_by(FileModel.category)
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Extension -> category mapping (P1-4). DB-backed, cached in-process.
# The hot path (upload classification) reads the cache; CRUD endpoints mutate
# the table AND refresh the cache so in-flight requests see changes at once.
# ---------------------------------------------------------------------------
_EXT_CACHE: dict[str, str] | None = None


def _load_ext_cache(db: Session) -> dict[str, str]:
    global _EXT_CACHE
    rows = db.execute(select(ExtCategory.extension, ExtCategory.category)).all()
    _EXT_CACHE = {ext: cat for ext, cat in rows}
    return _EXT_CACHE


def categorize(filename: str, db: Session | None = None) -> str:
    """Map a filename to its category using the DB-backed mapping (P1-4).

    Unknown extensions fall back to ``DEFAULT_CATEGORY``. The mapping is loaded
    (and cached) from the DB on first use; pass ``db`` to reuse a session.
    """
    global _EXT_CACHE
    if _EXT_CACHE is None:
        if db is None:
            with SessionLocal() as s:
                _load_ext_cache(s)
        else:
            _load_ext_cache(db)
    ext = Path(filename).suffix.lower()
    return _EXT_CACHE.get(ext, _cfg.DEFAULT_CATEGORY)


def list_ext_rules(db: Session) -> list[dict]:
    """Return all extension -> category mapping rows (admin, category:manage)."""
    rows = (
        db.execute(select(ExtCategory).order_by(ExtCategory.extension))
        .scalars()
        .all()
    )
    return [orm_to_dict(r) for r in rows]


def upsert_ext_rule(db: Session, extension: str, category: str) -> dict:
    """Create or update an extension -> category rule; refreshes the cache."""
    ext = extension.lower()
    if not ext.startswith("."):
        ext = "." + ext
    if not category or not category.strip():
        raise HTTPException(400, "category is required")
    rule = db.execute(
        select(ExtCategory).where(ExtCategory.extension == ext)
    ).scalar_one_or_none()
    if rule is None:
        rule = ExtCategory(extension=ext, category=category.strip())
        db.add(rule)
    else:
        rule.category = category.strip()
    db.commit()
    db.refresh(rule)
    _load_ext_cache(db)  # invalidate cache
    return orm_to_dict(rule)


def delete_ext_rule(db: Session, extension: str) -> None:
    """Delete an extension -> category rule; refreshes the cache."""
    ext = extension.lower()
    if not ext.startswith("."):
        ext = "." + ext
    rule = db.execute(
        select(ExtCategory).where(ExtCategory.extension == ext)
    ).scalar_one_or_none()
    if rule is None:
        raise HTTPException(404, f"Rule for extension '{ext}' not found")
    db.delete(rule)
    db.commit()
    _load_ext_cache(db)  # invalidate cache


def delete_category(db: Session, category: str) -> None:
    """Delete a category and all files within it (physical + DB)."""
    rows = db.execute(select(FileModel).where(FileModel.category == category)).scalars().all()
    for row in rows:
        _delete_file(_cfg.UPLOAD_DIR / row.filepath)
    db.execute(FileModel.__table__.delete().where(FileModel.category == category))
    db.commit()

    cat_dir = _cfg.UPLOAD_DIR / category
    if cat_dir.exists() and cat_dir.is_dir():
        _delete_tree(cat_dir)

    _audit_log("delete_category", category)


def organize_root() -> int:
    """Move scattered files in uploads/ root into their proper category folders.

    Returns the number of files moved.
    """
    count = 0
    for item in _cfg.UPLOAD_DIR.iterdir():
        if not item.is_file():
            continue
        cat = categorize(item.name)
        dest_dir = UPLOAD_DIR / cat
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / item.name
        if not dest.exists():
            shutil.move(str(item), str(dest))
        else:
            uid = uuid.uuid4().hex[:8]
            shutil.move(str(item), str(dest_dir / f"{uid}_{item.name}"))
        count += 1

    if count == 0:
        return 0
    _audit_log("organize", f"{count} files")
    return count
