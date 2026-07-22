# -*- coding: utf-8 -*-
"""Category endpoints: list, delete, organize root files (RBAC-gated).

The file-category business logic lives in :mod:`modules.files.services.category_service`;
these handlers keep only the RBAC ``Depends`` guards and response shaping.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from modules.user.auth import require_permission, require_permission_allow_anonymous
from modules.user.database import get_db
from modules.user.models import (
    CategoryListResponse,
    ExtCategoryRuleListResponse,
    ExtCategoryRuleRequest,
)
from modules.files.services import category_service

router = APIRouter(prefix="/api", tags=["Category"])


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories(
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission_allow_anonymous("file:list")),
):
    """List all categories with file count and total size."""
    return {"categories": category_service.list_categories(db)}


@router.get("/categories/mapping", response_model=ExtCategoryRuleListResponse)
async def list_ext_category_mapping(
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("category:manage")),
):
    """List the extension -> category mapping rules (requires category:manage)."""
    return {"rules": category_service.list_ext_rules(db)}


@router.put("/categories/mapping", response_model=ExtCategoryRuleListResponse)
async def upsert_ext_category_rule(
    body: ExtCategoryRuleRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("category:manage")),
):
    """Create or update an extension -> category rule (requires category:manage)."""
    category_service.upsert_ext_rule(db, body.extension, body.category)
    return {"rules": category_service.list_ext_rules(db)}


@router.delete("/categories/mapping/{extension}")
async def delete_ext_category_rule(
    extension: str,
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("category:manage")),
):
    """Delete an extension -> category rule (requires category:manage)."""
    category_service.delete_ext_rule(db, extension)
    return {"ok": True, "message": f"Rule for '{extension}' deleted"}


@router.delete("/categories/{category}")
async def delete_category(
    category: str,
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("category:manage")),
):
    """Delete a category and all files within it (requires category:manage)."""
    category_service.delete_category(db, category)
    return {"ok": True, "message": f"Category '{category}' deleted"}


@router.post("/organize")
async def organize_root(
    _: dict = Depends(require_permission("category:manage")),
):
    """Move scattered files in uploads/ root into their proper category folders."""
    count = category_service.organize_root()
    if count == 0:
        return {"ok": True, "message": "No files to organize"}
    return {"ok": True, "message": f"Organized {count} file(s)"}
