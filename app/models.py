# -*- coding: utf-8 -*-
"""Pydantic request/response models."""

from pydantic import BaseModel, ConfigDict


class AuthRequest(BaseModel):
    username: str
    password: str
    nickname: str | None = None


class AuthResponse(BaseModel):
    ok: bool
    token: str | None = None
    message: str = ""
    role: str | None = None
    nickname: str | None = None
    permissions: list[str] = []
    require_password_change: bool = False


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


class DeactivateRequest(BaseModel):
    password: str | None = None  # optional confirmation password


class AdminUserRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    nickname: str | None = None
    role: str | None = None
    status: str | None = None


class PathsRequest(BaseModel):
    """Body for batch file operations: a list of stored file paths."""
    paths: list[str] = []


class AdminBatchRequest(BaseModel):
    """Body for batch user operations: target ids + an action."""
    ids: list[int] = []
    action: str  # "approve" | "reject" | "delete"


# ---------------------------------------------------------------------------
# Response models (ARCH-5) — document & validate the stable read endpoints.
#
# Item models use ``extra="allow"`` so that adding a column to an ORM model (or
# a computed field) is forward-compatible and never silently dropped from the
# JSON response. The wrapper shapes stay explicit for a clean OpenAPI contract.
# ---------------------------------------------------------------------------
class FileItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    filename: str
    category: str
    filepath: str
    path: str
    size: int
    size_human: str
    uploaded_by: str
    uploader_nickname: str
    uploaded_at: str


class FileListResponse(BaseModel):
    files: list[FileItem]
    total: int
    page: int
    page_size: int


class UserItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    username: str
    nickname: str
    role: str
    status: str


class UserListResponse(BaseModel):
    users: list[UserItem]


class PendingUserItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    username: str


class PendingResponse(BaseModel):
    count: int
    users: list[PendingUserItem]


class AuditItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    username: str
    action: str
    target: str
    ip: str
    created_at: str


class AuditListResponse(BaseModel):
    logs: list[AuditItem]


class AuditLogsResponse(BaseModel):
    """Response for the public, permission-scoped audit endpoint (/api/audit/logs).

    ``scope`` is ``"self"`` for regular users (server-filtered to their own
    rows) or ``"all"`` for admins/reviewers. ``can_view_all`` mirrors the
    caller's ``audit:view`` permission so the UI can show the right controls.
    """

    model_config = ConfigDict(extra="allow")
    logs: list[AuditItem]
    total: int
    page: int
    page_size: int
    scope: str
    can_view_all: bool


class CategoryItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    category: str
    count: int
    total_size: int


class CategoryListResponse(BaseModel):
    categories: list[CategoryItem]


class ExtCategoryRuleRequest(BaseModel):
    """Body for creating/updating an extension -> category mapping rule (P1-4)."""

    extension: str
    category: str


class ExtCategoryRuleItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    extension: str
    category: str
    created_at: str


class ExtCategoryRuleListResponse(BaseModel):
    rules: list[ExtCategoryRuleItem]
