# -*- coding: utf-8 -*-
"""Feature-request / suggestion board (功能需求建议栏).

All endpoints are mounted under ``/api/suggest``:

* ``POST   /``            submit a suggestion        (any logged-in user)
* ``GET    /``            list suggestions           (own rows; admins/reviewer see all)
* ``GET    /{id}``        get one                    (owner or ``suggest:view``)
* ``PATCH  /{id}``        update status              (admin only, ``suggest:manage``)
* ``DELETE /{id}``        delete                     (owner or ``suggest:manage``)

Access is enforced server-side, never by the client:
* Regular users are hard-scoped to their own rows (a ``scope=all`` they send is
  ignored) — identical defence-in-depth model to the audit log.
* Only ``suggest:view`` holders may read all rows.
* Only ``suggest:manage`` holders (admin) may change a suggestion's status.
* Status changes and deletions are written to the audit log.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from modules.user.auth import get_permissions_for_role, require_permission
from modules.user.database import Suggestion, User, SessionLocal, get_db, orm_to_dict
from modules.user.utils import _audit_log, _client_ip, _now_str

router = APIRouter(prefix="/api/suggest", tags=["Suggestion"])

MAX_PAGE_SIZE = 200

STATUS_VALUES = {"pending", "accepted", "rejected", "done"}
CATEGORY_VALUES = {"feature", "ux", "bug", "other"}


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class SuggestionCreate(BaseModel):
    title: str
    body: str = ""
    category: str = "other"


class SuggestionStatusUpdate(BaseModel):
    status: str
    admin_note: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _suggest_to_dict(db, s: Suggestion) -> dict:
    """Convert a Suggestion row to a dict, attaching the operator's nickname."""
    d = orm_to_dict(s)
    nick = db.execute(
        select(User.nickname).where(User.username == s.username)
    ).scalar_one_or_none()
    d["nickname"] = (nick or "") or s.username
    return d


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("")
async def create_suggestion(
    body: SuggestionCreate,
    db=Depends(get_db),
    user: dict = Depends(require_permission("suggest:submit")),
    request: Request = None,
):
    """Create a new suggestion (any authenticated user)."""
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "标题不能为空")
    if len(title) > 120:
        raise HTTPException(400, "标题过长（最多 120 字）")
    category = body.category if body.category in CATEGORY_VALUES else "other"
    s = Suggestion(
        username=user["username"],
        title=title,
        body=(body.body or "").strip(),
        category=category,
        status="pending",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    _audit_log("suggest_create", user["username"], title, _client_ip(request))
    return {"ok": True, "suggestion": _suggest_to_dict(db, s)}


@router.get("")
async def list_suggestions(
    db=Depends(get_db),
    user: dict = Depends(require_permission("suggest:submit")),
    page: int = 1,
    page_size: int = 50,
    status: str = "",
    search: str = "",
    scope: str = "",
):
    """List suggestions, server-scoped to the caller's permissions.

    Regular users always see only their own rows. Admins/reviewers may pass
    ``scope=all`` to see every suggestion, or ``scope=self`` to narrow to theirs.
    """
    perms = get_permissions_for_role(user["role"])
    can_view_all = "suggest:view" in perms
    see_all = can_view_all and scope == "all"

    stmt = select(Suggestion)
    if not see_all:
        # Hard scope: regular users (and admins who ask for "self") only see own.
        stmt = stmt.where(Suggestion.username == user["username"])
    if status:
        stmt = stmt.where(Suggestion.status == status)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(Suggestion.title.like(like) | Suggestion.body.like(like))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))
    offset = (page - 1) * page_size
    rows = db.execute(
        stmt.order_by(Suggestion.id.desc()).limit(page_size).offset(offset)
    ).scalars().all()

    return {
        "items": [_suggest_to_dict(db, r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "scope": "all" if see_all else "self",
        "can_view_all": can_view_all,
    }


@router.get("/{sid}")
async def get_suggestion(
    sid: int,
    db=Depends(get_db),
    user: dict = Depends(require_permission("suggest:submit")),
):
    """Fetch a single suggestion (owner or ``suggest:view`` holder)."""
    s = db.get(Suggestion, sid)
    if not s:
        raise HTTPException(404, "建议不存在")
    perms = get_permissions_for_role(user["role"])
    if "suggest:view" not in perms and s.username != user["username"]:
        raise HTTPException(403, "无权查看该建议")
    return {"suggestion": _suggest_to_dict(db, s)}


@router.patch("/{sid}")
async def update_suggestion(
    sid: int,
    body: SuggestionStatusUpdate,
    db=Depends(get_db),
    user: dict = Depends(require_permission("suggest:manage")),
    request: Request = None,
):
    """Change a suggestion's status / admin note (admin only)."""
    if body.status not in STATUS_VALUES:
        raise HTTPException(400, "非法状态")
    s = db.get(Suggestion, sid)
    if not s:
        raise HTTPException(404, "建议不存在")
    old = s.status
    s.status = body.status
    if body.admin_note is not None:
        s.admin_note = body.admin_note
    s.updated_at = _now_str()
    db.commit()
    _audit_log(
        "suggest_status",
        user["username"],
        f"{s.title} [{old}→{body.status}]",
        _client_ip(request),
    )
    return {"ok": True, "suggestion": _suggest_to_dict(db, s)}


@router.delete("/{sid}")
async def delete_suggestion(
    sid: int,
    db=Depends(get_db),
    user: dict = Depends(require_permission("suggest:submit")),
    request: Request = None,
):
    """Delete a suggestion (owner, or admin via ``suggest:manage``)."""
    s = db.get(Suggestion, sid)
    if not s:
        raise HTTPException(404, "建议不存在")
    perms = get_permissions_for_role(user["role"])
    if "suggest:manage" not in perms and s.username != user["username"]:
        raise HTTPException(403, "无权删除该建议")
    title = s.title
    db.delete(s)
    db.commit()
    _audit_log("suggest_delete", user["username"], title, _client_ip(request))
    return {"ok": True}
