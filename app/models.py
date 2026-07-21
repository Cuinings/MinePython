# -*- coding: utf-8 -*-
"""Pydantic request/response models."""

from pydantic import BaseModel


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


class AdminUserRequest(BaseModel):
    username: str
    password: str
    nickname: str | None = None
    role: str | None = None
    status: str | None = None
