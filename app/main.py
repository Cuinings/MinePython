# -*- coding: utf-8 -*-
"""
File Server v4.5 — main application entry point (SQLAlchemy + RBAC).
Assembles FastAPI app, registers routers, serves Web UI.
"""

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.auth import purge_expired_tokens
from app.auth import router as auth_router
from app.admin import router as admin_router
from app.files import router as files_router
from app.categories import router as categories_router
from app.audit import router as audit_router
from app.cleanup import run_cleanup, scan_and_report
from app import config as app_config
from app.config import (
    ORPHAN_CLEANUP_AUTO,
    ORPHAN_CLEANUP_INTERVAL_SECONDS,
    TOKEN_CLEANUP_INTERVAL_SECONDS,
)
from app.database import SessionLocal, init_db
from app.logging_config import setup_logging
from app.utils import _client_ip

setup_logging()

log = logging.getLogger("fileserver")

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title="File Server",
    version="4.4.0",
    description=(
        "文件服务器 REST API —— 提供用户鉴权、文件上传 / 下载 / 管理、"
        "分类整理与管理员控制台等接口。点击下方按钮进入 Swagger 在线文档，"
        "可交互式浏览并调试所有端点。"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS is locked to explicit origins (never "*" together with credentials).
# Override via the CORS_ORIGINS env var (comma-separated) when serving the UI
# from a different domain.
_CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    duration = (time.time() - start) * 1000
    # Correlation id echoed back to the client for traceability.
    response.headers["X-Request-ID"] = request_id
    # Structured access log (consumed as JSON by the rotating file handler).
    log.info(
        f"{request.method} {request.url.path} → {response.status_code} ({duration:.0f}ms)",
        extra={
            "event": "http_request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round(duration, 1),
            "client_ip": _client_ip(request),
            "request_id": request_id,
        },
    )
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Attach baseline security response headers to every response."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data: https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "font-src 'self' data: https://cdn.jsdelivr.net",
    )
    response.headers.setdefault(
        "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
    )
    # HSTS is only enforced over HTTPS; harmless (and ignored) over plain HTTP.
    response.headers.setdefault(
        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
    )
    return response


# ---------------------------------------------------------------------------
# Gate interactive API docs behind DEBUG (R3)
# ---------------------------------------------------------------------------
_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}


@app.middleware("http")
async def gate_api_docs(request: Request, call_next):
    """Block interactive docs/OpenAPI when not in debug mode (R3)."""
    if not app_config.DEBUG and request.url.path in _DOCS_PATHS:
        return JSONResponse(status_code=403, content={"detail": "Not found"})
    return await call_next(request)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
    # ARCH-1: never leak internal exception strings to the client in production.
    # Only attach `error` when DEBUG is enabled (trusted dev environments).
    content = {"detail": "Internal server error"}
    if app_config.DEBUG:
        content["error"] = str(exc)
    return JSONResponse(status_code=500, content=content)


# Register API routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(files_router)
app.include_router(categories_router)
app.include_router(audit_router)


# ---------------------------------------------------------------------------
# Web UI — static assets (common.css + js/ modules) + per-module pages.
# Each HTML page is re-read from disk on every request (hot reload).
# ---------------------------------------------------------------------------
WEB_ROOT = Path(__file__).parent.parent
STATIC_DIR = WEB_ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _load_html(name: str) -> str:
    """Load an HTML page from disk with utf-8 encoding (hot reload)."""
    html_path = WEB_ROOT / name
    if not html_path.exists():
        return f"<h1>{name} not found</h1>"
    return html_path.read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
@app.get("/index.html", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=_load_html("index.html"))


@app.get("/files.html", response_class=HTMLResponse)
async def files_page():
    return HTMLResponse(content=_load_html("files.html"))


@app.get("/users.html", response_class=HTMLResponse)
async def users_page():
    return HTMLResponse(content=_load_html("users.html"))


@app.get("/audit.html", response_class=HTMLResponse)
async def audit_page():
    """审计日志独立入口 —— 所有登录用户均可访问（匿名用户在前端会被重定向回登录页）。"""
    return HTMLResponse(content=_load_html("audit.html"))


@app.get("/api", response_class=HTMLResponse)
@app.get("/api/", response_class=HTMLResponse)
async def api_home():
    """Swagger API 独立主页入口 —— 与文件管理 UI 分离、无需登录的文档门户。"""
    html = _load_html("api.html")
    html = (
        html.replace("__TITLE__", app.title)
        .replace("__VERSION__", app.version)
        .replace("__DESCRIPTION__", app.description or "")
    )
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Background: periodically purge expired session tokens (ARCH-3)
# ---------------------------------------------------------------------------
async def _token_cleanup_loop():
    """Sweep expired token rows on a fixed interval until the app stops."""
    while True:
        await asyncio.sleep(TOKEN_CLEANUP_INTERVAL_SECONDS)
        try:
            removed = purge_expired_tokens()
            if removed:
                log.info(
                    "Purged expired session tokens",
                    extra={"event": "token_cleanup", "removed": removed},
                )
        except Exception:  # pragma: no cover - defensive, never kill the loop
            log.exception("Token cleanup sweep failed")


# ---------------------------------------------------------------------------
# Background: periodically scan (and optionally clean) orphaned files (P1-6)
# ---------------------------------------------------------------------------
async def _orphan_scan_loop():
    """Optionally sweep disk/DB orphans on a fixed interval (off by default).

    When ``ORPHAN_CLEANUP_AUTO`` is true the sweep deletes orphans on its own;
    otherwise it only reports (the operator runs POST /api/admin/cleanup for a
    real deletion). The interval is 0 -> the loop never starts.
    """
    while True:
        await asyncio.sleep(ORPHAN_CLEANUP_INTERVAL_SECONDS)
        try:
            if ORPHAN_CLEANUP_AUTO:
                with SessionLocal() as db:
                    res = run_cleanup(db, target="both", dry_run=False)
                log.info(
                    "Orphan auto-cleanup",
                    extra={"event": "orphan_cleanup",
                           "deleted_disk": res["deleted_disk"],
                           "deleted_db": res["deleted_db"]},
                )
            else:
                scan_and_report()
        except Exception:  # pragma: no cover - defensive, never kill the loop
            log.exception("Orphan scan failed")


# ---------------------------------------------------------------------------
# Startup: init database
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    init_db()
    # ARCH-3: clear any tokens that expired while the server was down, then
    # keep sweeping in the background so the tokens table stays bounded.
    removed = purge_expired_tokens()
    log.info(
        "File Server v4.6 started",
        extra={"event": "startup", "expired_tokens_purged": removed},
    )
    if TOKEN_CLEANUP_INTERVAL_SECONDS and TOKEN_CLEANUP_INTERVAL_SECONDS > 0:
        asyncio.create_task(_token_cleanup_loop())
    if ORPHAN_CLEANUP_INTERVAL_SECONDS and ORPHAN_CLEANUP_INTERVAL_SECONDS > 0:
        asyncio.create_task(_orphan_scan_loop())
