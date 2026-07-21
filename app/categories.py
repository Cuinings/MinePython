# -*- coding: utf-8 -*-
"""Category endpoints: list, delete, organize root files."""

import shutil

from fastapi import APIRouter, HTTPException

from app.database import get_db
from app.utils import _categorize

router = APIRouter(prefix="/api", tags=["Category"])


@router.get("/categories")
async def list_categories():
    """List all categories with file count and total size."""
    db = get_db()
    rows = db.execute(
        "SELECT category, COUNT(*) as count, SUM(size) as total_size FROM files GROUP BY category ORDER BY category"
    ).fetchall()
    db.close()
    return {"categories": [dict(r) for r in rows]}


@router.delete("/categories/{category}")
async def delete_category(category: str):
    """Delete a category and all files within it."""
    from app.config import UPLOAD_DIR
    db = get_db()
    rows = db.execute("SELECT filepath FROM files WHERE category = ?", (category,)).fetchall()
    for row in rows:
        fp = UPLOAD_DIR / row["filepath"]
        if fp.exists():
            fp.unlink()
    db.execute("DELETE FROM files WHERE category = ?", (category,))
    db.commit()
    db.close()

    cat_dir = UPLOAD_DIR / category
    if cat_dir.exists() and cat_dir.is_dir():
        shutil.rmtree(cat_dir)

    return {"ok": True, "message": f"Category '{category}' deleted"}


@router.post("/organize")
async def organize_root():
    """Move scattered files in uploads/ root into their proper category folders."""
    from app.config import UPLOAD_DIR
    import os

    count = 0
    for item in UPLOAD_DIR.iterdir():
        if not item.is_file():
            continue
        cat = _categorize(item.name)
        dest_dir = UPLOAD_DIR / cat
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / item.name
        if not dest.exists():
            shutil.move(str(item), str(dest))
            count += 1
        else:
            # File name collision: add UUID
            import uuid
            uid = uuid.uuid4().hex[:8]
            shutil.move(str(item), str(dest_dir / f"{uid}_{item.name}"))
            count += 1

    if count == 0:
        return {"ok": True, "message": "No files to organize"}

    return {"ok": True, "message": f"Organized {count} file(s)"}
