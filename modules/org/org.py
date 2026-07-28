# -*- coding: utf-8 -*-
"""Organization structure (组织架构) — departments tree + members CRUD.

All endpoints are mounted under ``/api/org``:

Departments (org:manage to write, org:view to read):
* ``POST   /departments``        create a department (optionally under a parent)
* ``GET    /departments``        flat list with direct member counts
* ``GET    /tree``               nested department tree with member counts
* ``GET    /departments/{id}``   get one department
* ``PUT    /departments/{id}``   rename / move / reorder / describe
* ``DELETE /departments/{id}``   delete (cascades to children + members)

Members (org:manage to write, org:view to read):
* ``GET    /users``              candidate users (with current department, if any)
* ``POST   /members``            add a user to a department (a user belongs to
                                 at most ONE department; already-assigned → 400)
* ``GET    /members``            list members (filter by department / user / search)
* ``GET    /departments/{id}/members``  members of one department
* ``PUT    /members/{id}``       update a member's title and/or transfer (调岗)
* ``DELETE /members/{id}``       remove a member

Cardinality: department → members is one-to-many; each member (user) belongs to
exactly one department (unique ``user_id`` in ``org_members``).

Access is server-enforced via RBAC dependencies; every mutation is written to the
audit log (same defence-in-depth model as the suggestion board).
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from modules.user.auth import require_permission
from modules.user.database import (
    OrgDepartment,
    OrgMember,
    User,
    get_db,
    orm_to_dict,
)
from modules.user.utils import _audit_log, _client_ip

router = APIRouter(prefix="/api/org", tags=["Organization"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class DepartmentCreate(BaseModel):
    name: str
    parent_id: int | None = None  # 0 (client-side) or None = root
    sort_order: int = 0
    description: str = ""


class DepartmentUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None  # 0 / None = root; omitted = leave unchanged
    sort_order: int | None = None
    description: str | None = None


class MemberAdd(BaseModel):
    department_id: int
    user_id: int
    title: str = ""


class MemberUpdate(BaseModel):
    title: str | None = None
    department_id: int | None = None  # present = transfer the member (调岗)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _norm_parent(pid: int | None) -> int | None:
    """Client sends 0 / null / omitted to mean "root"; normalize to None."""
    return None if (pid is None or pid == 0) else int(pid)


def _dept_to_dict(d: OrgDepartment, member_count: int = 0) -> dict:
    out = orm_to_dict(d)
    out["member_count"] = member_count
    return out


def _member_to_dict(db: Session, m: OrgMember) -> dict:
    d = orm_to_dict(m)
    user = db.execute(select(User).where(User.id == m.user_id)).scalar_one_or_none()
    dept = db.execute(
        select(OrgDepartment).where(OrgDepartment.id == m.department_id)
    ).scalar_one_or_none()
    d["username"] = user.username if user else "unknown"
    d["nickname"] = (user.nickname or "") if user else ""
    d["role"] = user.role if user else ""
    d["department_name"] = dept.name if dept else ""
    return d


def _would_create_cycle(db: Session, dept_id: int, new_parent_id: int | None) -> bool:
    """Return True if setting ``dept_id.parent_id = new_parent_id`` forms a loop."""
    if new_parent_id is None:
        return False
    if new_parent_id == dept_id:
        return True
    # Walk up from the proposed parent; if we meet dept_id, it's a cycle.
    cur = db.get(OrgDepartment, new_parent_id)
    seen = set()
    while cur is not None and cur.id not in seen:
        if cur.id == dept_id:
            return True
        seen.add(cur.id)
        cur = db.get(OrgDepartment, cur.parent_id) if cur.parent_id is not None else None
    return False


def _member_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(OrgMember.department_id, func.count(OrgMember.id))
        .group_by(OrgMember.department_id)
    ).all()
    return {did: cnt for did, cnt in rows}


def _build_tree(departments: list[OrgDepartment], counts: dict[int, int]) -> list[dict]:
    nodes = {d.id: _dept_to_dict(d, counts.get(d.id, 0)) for d in departments}
    for n in nodes.values():
        n["children"] = []
    roots = []
    for d in departments:
        node = nodes[d.id]
        if d.parent_id is not None and d.parent_id in nodes:
            nodes[d.parent_id]["children"].append(node)
        else:
            roots.append(node)
    # Sort each level by sort_order then name for a stable display.
    def _sort(nlist):
        nlist.sort(key=lambda n: (n["sort_order"], n["name"]))
        for n in nlist:
            _sort(n["children"])

    _sort(roots)
    return roots


# ---------------------------------------------------------------------------
# Department routes
# ---------------------------------------------------------------------------
@router.post("/departments")
async def create_department(
    body: DepartmentCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("org:manage")),
    request: Request = None,
):
    """Create a department, optionally nested under ``parent_id``."""
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "部门名称不能为空")
    if len(name) > 120:
        raise HTTPException(400, "部门名称过长（最多 120 字）")
    parent_id = _norm_parent(body.parent_id)
    if parent_id is not None:
        parent = db.get(OrgDepartment, parent_id)
        if not parent:
            raise HTTPException(404, "父部门不存在")
    dept = OrgDepartment(
        name=name,
        parent_id=parent_id,
        sort_order=body.sort_order,
        description=(body.description or "").strip(),
    )
    db.add(dept)
    db.commit()
    db.refresh(dept)
    _audit_log("org_dept_create", f"{name} (id={dept.id})", user["username"], _client_ip(request))
    return {"ok": True, "department": _dept_to_dict(dept)}


@router.get("/departments")
async def list_departments(
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("org:view")),
):
    """Flat list of all departments with their direct member counts."""
    depts = db.execute(select(OrgDepartment).order_by(OrgDepartment.sort_order, OrgDepartment.name)).scalars().all()
    counts = _member_counts(db)
    return {"departments": [_dept_to_dict(d, counts.get(d.id, 0)) for d in depts]}


@router.get("/tree")
async def org_tree(
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("org:view")),
):
    """Nested department tree (with member counts) for the org chart view."""
    depts = db.execute(select(OrgDepartment)).scalars().all()
    counts = _member_counts(db)
    return {"tree": _build_tree(depts, counts)}


@router.get("/departments/{dept_id}")
async def get_department(
    dept_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("org:view")),
):
    """Fetch a single department."""
    dept = db.get(OrgDepartment, dept_id)
    if not dept:
        raise HTTPException(404, "部门不存在")
    return {"department": _dept_to_dict(dept, _member_counts(db).get(dept.id, 0))}


@router.put("/departments/{dept_id}")
async def update_department(
    dept_id: int,
    body: DepartmentUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("org:manage")),
    request: Request = None,
):
    """Rename / move / reorder / describe a department.

    Only the fields present in the request body are changed (``exclude_unset``),
    so a partial update never clobbers fields the client did not send. A ``0`` or
    ``null`` ``parent_id`` moves the department to the root; an explicit id nests
    it — cycle-free (a department cannot become its own descendant).
    """
    dept = db.get(OrgDepartment, dept_id)
    if not dept:
        raise HTTPException(404, "部门不存在")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        name = (data["name"] or "").strip()
        if not name:
            raise HTTPException(400, "部门名称不能为空")
        if len(name) > 120:
            raise HTTPException(400, "部门名称过长（最多 120 字）")
        dept.name = name
    if "sort_order" in data and data["sort_order"] is not None:
        dept.sort_order = int(data["sort_order"])
    if "description" in data and data["description"] is not None:
        dept.description = (data["description"] or "").strip()
    if "parent_id" in data:
        new_parent = _norm_parent(data["parent_id"])
        if new_parent is not None:
            if not db.get(OrgDepartment, new_parent):
                raise HTTPException(404, "父部门不存在")
            if _would_create_cycle(db, dept.id, new_parent):
                raise HTTPException(400, "不能将部门移动到其自身或其子部门下")
        dept.parent_id = new_parent
    db.commit()
    _audit_log("org_dept_update", f"{dept.name} (id={dept.id})", user["username"], _client_ip(request))
    return {"ok": True, "department": _dept_to_dict(dept, _member_counts(db).get(dept.id, 0))}


@router.delete("/departments/{dept_id}")
async def delete_department(
    dept_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("org:manage")),
    request: Request = None,
):
    """Delete a department. Cascades to child departments and their members."""
    dept = db.get(OrgDepartment, dept_id)
    if not dept:
        raise HTTPException(404, "部门不存在")
    child_count = db.scalar(
        select(func.count(OrgDepartment.id)).where(OrgDepartment.parent_id == dept_id)
    ) or 0
    member_count = db.scalar(
        select(func.count(OrgMember.id)).where(OrgMember.department_id == dept_id)
    ) or 0
    name = dept.name
    db.delete(dept)
    db.commit()
    _audit_log(
        "org_dept_delete",
        f"{name} (id={dept_id}, 子部门={child_count}, 成员={member_count})",
        user["username"],
        _client_ip(request),
    )
    return {
        "ok": True,
        "message": f"部门 '{name}' 已删除（含 {child_count} 个子部门、{member_count} 名成员）",
    }


# ---------------------------------------------------------------------------
# Member routes
# ---------------------------------------------------------------------------
@router.get("/users")
async def list_candidate_users(
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("org:view")),
):
    """Lightweight user list for the add-member dropdown.

    Each entry carries the user's current department (or ``null``). The frontend
    labels already-assigned users with their current department but still lets
    the admin pick them — selecting one and saving will transfer (调岗) that
    member to the target department, since a user belongs to at most one
    department.
    """
    users = db.execute(select(User).order_by(User.username)).scalars().all()
    memberships = {
        m.user_id: m
        for m in db.execute(select(OrgMember)).scalars().all()
    }
    dept_names = {
        d.id: d.name for d in db.execute(select(OrgDepartment)).scalars().all()
    }
    out = []
    for u in users:
        m = memberships.get(u.id)
        out.append({
            "id": u.id,
            "username": u.username,
            "nickname": u.nickname,
            "role": u.role,
            "department_id": m.department_id if m else None,
            "department_name": dept_names.get(m.department_id, "") if m else "",
            "member_id": m.id if m else None,
        })
    return {"users": out}


@router.post("/members")
async def add_member(
    body: MemberAdd,
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("org:manage")),
    request: Request = None,
):
    """Add a user to a department (a user belongs to at most one department).

    * not assigned yet → a new membership row is created;
    * already in this very department → idempotent (returns the existing row);
    * already in **another** department → the membership is moved (调岗) to the
      selected department in place, so a member can be adjusted to any department
      without first removing them. Returns ``transferred: true`` in that case.
    """
    dept = db.get(OrgDepartment, body.department_id)
    if not dept:
        raise HTTPException(404, "部门不存在")
    target = db.get(User, body.user_id)
    if not target:
        raise HTTPException(404, "用户不存在")
    existing = db.execute(
        select(OrgMember).where(OrgMember.user_id == body.user_id)
    ).scalar_one_or_none()
    if existing:
        if existing.department_id == body.department_id:
            return {"ok": True, "member": _member_to_dict(db, existing), "duplicate": True}
        # Move the member to the requested department (keep/refresh title).
        old_dept = db.get(OrgDepartment, existing.department_id)
        if body.title:
            existing.title = (body.title or "").strip()
        existing.department_id = body.department_id
        db.commit()
        db.refresh(existing)
        info = _member_to_dict(db, existing)
        _audit_log(
            "org_member_transfer",
            f"{target.username}: {old_dept.name if old_dept else existing.department_id} → {dept.name}",
            user["username"],
            _client_ip(request),
        )
        return {"ok": True, "member": info, "transferred": True}
    member = OrgMember(
        department_id=body.department_id,
        user_id=body.user_id,
        title=(body.title or "").strip(),
    )
    db.add(member)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "该用户已属于其他部门（一名成员只能属于一个部门）")
    db.refresh(member)
    _audit_log(
        "org_member_add",
        f"{target.username} → {dept.name}",
        user["username"],
        _client_ip(request),
    )
    return {"ok": True, "member": _member_to_dict(db, member)}


@router.get("/members")
async def list_members(
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("org:view")),
    department_id: int = 0,
    user_id: int = 0,
    search: str = "",
):
    """List members, optionally filtered by department / user / search."""
    stmt = select(OrgMember)
    if department_id:
        stmt = stmt.where(OrgMember.department_id == department_id)
    if user_id:
        stmt = stmt.where(OrgMember.user_id == user_id)
    rows = db.execute(stmt.order_by(OrgMember.id.desc())).scalars().all()

    # Filter by username/nickname/title (search) in memory to avoid a heavy join
    # on every call; datasets for an org chart are small.
    out = [_member_to_dict(db, m) for m in rows]
    if search:
        q = search.strip().lower()
        out = [
            m for m in out
            if q in (m["username"] or "").lower()
            or q in (m["nickname"] or "").lower()
            or q in (m["title"] or "").lower()
            or q in (m["department_name"] or "").lower()
        ]
    return {"members": out, "total": len(out)}


@router.get("/departments/{dept_id}/members")
async def list_department_members(
    dept_id: int,
    db: Session = Depends(get_db),
    _: dict = Depends(require_permission("org:view")),
):
    """Members of a single department."""
    if not db.get(OrgDepartment, dept_id):
        raise HTTPException(404, "部门不存在")
    rows = db.execute(
        select(OrgMember).where(OrgMember.department_id == dept_id).order_by(OrgMember.id)
    ).scalars().all()
    return {"members": [_member_to_dict(db, m) for m in rows]}


@router.put("/members/{member_id}")
async def update_member(
    member_id: int,
    body: MemberUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("org:manage")),
    request: Request = None,
):
    """Update a member's title (职位) and/or transfer them to another department (调岗).

    Because a user belongs to exactly one department, a transfer is an in-place
    update of ``department_id`` on the same membership row.
    """
    member = db.get(OrgMember, member_id)
    if not member:
        raise HTTPException(404, "成员记录不存在")
    data = body.model_dump(exclude_unset=True)
    moved_from = None
    if "title" in data and data["title"] is not None:
        member.title = (data["title"] or "").strip()
    if "department_id" in data and data["department_id"] is not None:
        new_dept_id = int(data["department_id"])
        if new_dept_id != member.department_id:
            new_dept = db.get(OrgDepartment, new_dept_id)
            if not new_dept:
                raise HTTPException(404, "目标部门不存在")
            old_dept = db.get(OrgDepartment, member.department_id)
            moved_from = old_dept.name if old_dept else str(member.department_id)
            member.department_id = new_dept_id
    db.commit()
    info = _member_to_dict(db, member)
    detail = f"{info['username']} → {info['department_name']}"
    if moved_from:
        detail = f"{info['username']}: {moved_from} → {info['department_name']} (调岗)"
    _audit_log("org_member_update", detail, user["username"], _client_ip(request))
    return {"ok": True, "member": info}


@router.delete("/members/{member_id}")
async def remove_member(
    member_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_permission("org:manage")),
    request: Request = None,
):
    """Remove a member from their department."""
    member = db.get(OrgMember, member_id)
    if not member:
        raise HTTPException(404, "成员记录不存在")
    info = _member_to_dict(db, member)
    db.delete(member)
    db.commit()
    _audit_log(
        "org_member_remove",
        f"{info['username']} ← {info['department_name']}",
        user["username"],
        _client_ip(request),
    )
    return {"ok": True}
