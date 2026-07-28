# -*- coding: utf-8 -*-
"""模块共用层：FastAPI 应用工厂、共享中间件、异常处理、静态资源与页面服务。

四个模块（user / files / audit / apidocs）都通过 :func:`create_app` 构建各自的
FastAPI 应用，组合不同的路由器与页面；合并入口 :mod:`modules.combined` 也用它把
四个模块挂到同一个应用（端口 8000）。所有安全头、请求日志、API 文档开关、全局异常
处理、后台清理任务都集中在这里，保证行为一致。
"""

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from modules.user import config as user_config
from modules.user.config import (
    AUDIT_LOG_RETENTION_DAYS,
    ORPHAN_CLEANUP_AUTO,
    ORPHAN_CLEANUP_INTERVAL_SECONDS,
    PERMISSION_CACHE_REFRESH_SECONDS,
    REFRESH_TOKEN_CLEANUP_INTERVAL_SECONDS,
)
from modules.user.database import SessionLocal, init_db, refresh_permissions
from modules.user.auth import purge_expired_tokens
from modules.user.logging_config import setup_logging
from modules.user.utils import _client_ip, purge_audit_log

# Web UI 根目录（项目根，存 index.html / files.html / users.html / audit.html / api.html）
WEB_ROOT = Path(__file__).parent.parent
STATIC_DIR = WEB_ROOT / "static"
STATIC_DIR.mkdir(exist_ok=True)

log = logging.getLogger("fileserver")

_DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}


async def global_exception_handler(request: Request, exc: Exception):
    """Global 500 handler — never leak internal exception strings in production.

    Only attach ``error`` when DEBUG is enabled (trusted dev environments).
    Imported directly by the security tests, so it lives at module level.
    """
    log.error(
        f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True
    )
    content = {"detail": "Internal server error"}
    if user_config.DEBUG:
        content["error"] = str(exc)
    return JSONResponse(status_code=500, content=content)


def _load_html(name: str) -> str:
    """Load an HTML page from disk with utf-8 encoding (hot reload)."""
    html_path = WEB_ROOT / name
    if not html_path.exists():
        return f"<h1>{name} not found</h1>"
    return html_path.read_text(encoding="utf-8")


def _register_page(app: FastAPI, path: str, name: str) -> None:
    """Register a single HTML page route, capturing ``name`` per-call."""

    @app.get(path, response_class=HTMLResponse)
    async def page():
        # no-store: the inlined import map lives inside the HTML, so the page
        # itself must never be cached or ADB install keeps using a stale map.
        return HTMLResponse(content=_load_html(name), headers={"Cache-Control": "no-store"})

    page.__name__ = f"page_{name}"


def create_app(
    title: str,
    version: str,
    description: str,
    routers: list,
    extra_pages: list[tuple[str, str]] | None = None,
    include_api_docs: bool = True,
) -> FastAPI:
    """Build a FastAPI app with the shared middleware / handlers / pages.

    * ``routers`` — API routers to include (e.g. ``[auth_router, files_router]``).
    * ``extra_pages`` — list of ``(route_path, html_filename)`` served as HTML.
    * ``include_api_docs`` — when True, serve ``/docs``, ``/redoc``,
      ``/openapi.json`` and the ``/api`` doc-portal page (gated by DEBUG in prod).
    """
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        removed = purge_expired_tokens()
        log.info(
            "Module app started",
            extra={"event": "startup", "expired_tokens_purged": removed},
        )
        # Horizontal-scaling safety net: Postgres + a shared JWT secret are
        # required for instances to agree on token validity. Warn loudly if the
        # former is set but the latter is not (auto-generated per-instance
        # secrets would make instances reject each other's tokens).
        if user_config.DATABASE_URL and not user_config.JWT_SECRET:
            log.warning(
                "DATABASE_URL is set (multi-instance) but JWT_SECRET is not — "
                "each instance will generate its own secret and reject the "
                "others' access tokens. Set a shared JWT_SECRET for all instances.",
                extra={"event": "config_warn", "issue": "missing_shared_jwt_secret"},
            )
        if REFRESH_TOKEN_CLEANUP_INTERVAL_SECONDS and REFRESH_TOKEN_CLEANUP_INTERVAL_SECONDS > 0:
            asyncio.create_task(_token_cleanup_loop())
        if PERMISSION_CACHE_REFRESH_SECONDS and PERMISSION_CACHE_REFRESH_SECONDS > 0:
            asyncio.create_task(_permission_cache_loop())
        if AUDIT_LOG_RETENTION_DAYS and AUDIT_LOG_RETENTION_DAYS > 0:
            asyncio.create_task(_audit_cleanup_loop())
        if ORPHAN_CLEANUP_INTERVAL_SECONDS and ORPHAN_CLEANUP_INTERVAL_SECONDS > 0:
            asyncio.create_task(_orphan_scan_loop())
        yield

    app = FastAPI(
        title=title,
        version=version,
        description=description,
        docs_url="/docs" if include_api_docs else None,
        redoc_url="/redoc" if include_api_docs else None,
        openapi_url="/openapi.json" if include_api_docs else None,
        lifespan=lifespan,
    )

    # CORS is locked to explicit origins (never "*" together with credentials).
    _CORS_ORIGINS = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
        ).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Force "Cache-Control: no-store" on EVERY response (HTML pages,
    # /static mount, API JSON). This is what actually stops the browser
    # from caching i18n.js / webadb2.bundle.js / vendor2 ES modules
    # and re-running a stale inlined import map — which made WebUSB ADB
    # install fail with "缺少 Adb / AdbWebUsbBackend". Starlette's
    # StaticFiles does not accept a `headers` kwarg here, so a global
    # middleware is the reliable way to set it.
    class _NoStoreMiddleware:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            async def _send(message):
                if message["type"] == "http.response.start":
                    headers = message.get("headers") or []
                    # drop any pre-existing cache-control, then set no-store
                    headers = [
                        (k, v) for (k, v) in headers
                        if k.lower() != b"cache-control"
                    ]
                    headers.append((b"cache-control", b"no-store"))
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, _send)

    app.add_middleware(_NoStoreMiddleware)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        duration = (time.time() - start) * 1000
        response.headers["X-Request-ID"] = request_id
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
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        path = request.url.path
        if path.startswith("/api/preview/"):
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            frame_ancestors = "frame-ancestors 'self';"
        else:
            response.headers.setdefault("X-Frame-Options", "DENY")
            frame_ancestors = "frame-ancestors 'none';"
        # connect-src must allow the same origins the API accepts (CORS), so
        # that fetch()/XHR from the web UI is not blocked by the browser when
        # the page is opened via 127.0.0.1 while the API is on localhost (or
        # vice-versa). Without this, the browser silently rejects the request
        # with a "Failed to fetch" network error even though the server is fine.
        connect_src = "connect-src 'self'" + "".join(
            f" {o}" for o in _CORS_ORIGINS
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            + connect_src
            + "; "
            "img-src 'self' data: https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' data: https://cdn.jsdelivr.net; "
            + frame_ancestors,
        )
        return response

    @app.middleware("http")
    async def gate_api_docs(request: Request, call_next):
        """Block interactive docs/OpenAPI unless explicitly enabled (R3).

        Controlled by API_DOCS_ENABLED (which defaults to DEBUG for
        safe-by-default), so docs can stay reachable even with DEBUG off.
        """
        if not user_config.API_DOCS_ENABLED and request.url.path in _DOCS_PATHS:
            return JSONResponse(status_code=403, content={"detail": "Not found"})
        return await call_next(request)

    app.add_exception_handler(Exception, global_exception_handler)

    # Register API routers
    for router in routers:
        app.include_router(router)

    # Static assets (common.css + js/ modules).
    # NOTE: StaticFiles does NOT accept a `headers` kwarg in this Starlette
    # build, so the no-store header is injected globally by the
    # NoStoreMiddleware defined below (covers the /static mount AND the
    # HTML pages). Without it the browser caches i18n.js /
    # webadb2.bundle.js / vendor2 ES modules and keeps running a stale
    # inlined import map, which makes WebUSB ADB install fail with
    # "缺少 Adb / AdbWebUsbBackend".
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Explicit handler for /static/js/** — serves the browser-side WebUSB ADB
    # bundle (webadb.bundle.js) and the localised ya-webadb vendor ES modules.
    # Starlette's StaticFiles mount intermittently returns 404 for these files
    # on some Windows/Python builds even though the file exists on disk, which
    # breaks the dynamic import(). Serving them via FileResponse sidesteps that
    # and guarantees the ES module graph resolves. Registered as a route (above
    # the mount) so it takes precedence for everything under /static/js/.
    _JS_MIME = {
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".json": "application/json",
        ".css": "text/css",
        ".map": "application/json",
    }

    @app.get("/static/js/{filepath:path}")
    async def serve_static_js(filepath: str):
        target = (STATIC_DIR / "js" / filepath).resolve()
        base = STATIC_DIR.resolve()
        # Prevent path traversal outside the static dir.
        if target != base and not str(target).startswith(str(base) + os.sep):
            return JSONResponse(status_code=403, content={"detail": "forbidden"})
        if not target.is_file():
            return JSONResponse(status_code=404, content={"detail": "not found: " + filepath})
        ext = target.suffix.lower()
        media = _JS_MIME.get(ext, "application/octet-stream")
        # no-store (not no-cache) — dev assets must never be served from a
        # browser cache, otherwise a stale inlined import map in files.html
        # keeps pointing at the deprecated vendor/ build and ADB install fails.
        return FileResponse(str(target), media_type=media, headers={"Cache-Control": "no-store"})

    # Public branding endpoint — the web UI fetches this on load to render the
    # project name dynamically (page <title> + header), so rebranding needs only
    # the APP_NAME env var. No auth: the name is public and non-sensitive.
    @app.get("/api/app-info")
    async def app_info():
        # Read the live branding name (not app.title, which is fixed at startup)
        # so an admin rename via /api/admin/site shows up without a restart.
        bundle_path = STATIC_DIR / "js" / "webadb.bundle.js"
        return {
            "name": user_config.APP_NAME,
            "version": app.version,
            "static_dir": str(STATIC_DIR),
            "webadb_bundle_exists": bundle_path.exists(),
            "webadb_bundle_size": bundle_path.stat().st_size if bundle_path.exists() else 0,
        }

    # Favicon — the browser auto-requests /favicon.ico on every page, so we
    # serve a branded SVG to avoid a 404 in the console. An SVG favicon works in
    # all modern browsers and covers index.html, login.html, files.html, etc.
    @app.get("/favicon.ico")
    async def favicon():
        svg = STATIC_DIR / "favicon.svg"
        if not svg.is_file():
            return JSONResponse(status_code=404, content={"detail": "not found"})
        return FileResponse(
            str(svg),
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # Main app shell at "/" and "/index.html"
    @app.get("/", response_class=HTMLResponse)
    @app.get("/index.html", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(content=_load_html("index.html"), headers={"Cache-Control": "no-store"})

    # Per-module extra pages (e.g. /files.html, /users.html, /audit.html)
    for path, name in extra_pages or []:
        _register_page(app, path, name)

    # Swagger API portal page (/api, /api/) — separated from the file UI.
    if include_api_docs:

        @app.get("/api", response_class=HTMLResponse)
        @app.get("/api/", response_class=HTMLResponse)
        async def api_home():
            html = _load_html("api.html")
            html = (
                html.replace("__TITLE__", app.title)
                .replace("__VERSION__", app.version)
                .replace("__DESCRIPTION__", app.description or "")
            )
            return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})

    # ------------------------------------------------------------------
    # Background: periodically purge expired refresh tokens (ARCH-9)
    # ------------------------------------------------------------------
    async def _token_cleanup_loop():
        while True:
            await asyncio.sleep(REFRESH_TOKEN_CLEANUP_INTERVAL_SECONDS)
            try:
                removed = purge_expired_tokens()
                if removed:
                    log.info(
                        "Purged expired refresh tokens",
                        extra={"event": "token_cleanup", "removed": removed},
                    )
            except Exception:  # pragma: no cover - defensive
                log.exception("Token cleanup sweep failed")

    # ------------------------------------------------------------------
    # Background: periodically reload the in-memory role->permission cache so
    # permission changes propagate across instances (ARCH-10).
    # ------------------------------------------------------------------
    async def _permission_cache_loop():
        while True:
            await asyncio.sleep(PERMISSION_CACHE_REFRESH_SECONDS)
            try:
                refresh_permissions()
            except Exception:  # pragma: no cover - defensive
                log.exception("Permission cache refresh failed")

    # ------------------------------------------------------------------
    # Background: periodically purge old audit_log rows (retention policy).
    # ------------------------------------------------------------------
    async def _audit_cleanup_loop():
        while True:
            await asyncio.sleep(max(AUDIT_LOG_RETENTION_DAYS * 60, 60))
            try:
                removed = purge_audit_log()
                if removed:
                    log.info(
                        "Purged old audit logs",
                        extra={"event": "audit_cleanup", "removed": removed},
                    )
            except Exception:  # pragma: no cover - defensive
                log.exception("Audit cleanup sweep failed")

    # ------------------------------------------------------------------
    # Background: optionally scan (and delete) orphaned files (P1-6)
    # run_cleanup is imported lazily so modules that don't bundle the
    # files module never pull it in.
    # ------------------------------------------------------------------
    async def _orphan_scan_loop():
        while True:
            await asyncio.sleep(ORPHAN_CLEANUP_INTERVAL_SECONDS)
            try:
                if ORPHAN_CLEANUP_AUTO:
                    from modules.files.cleanup import run_cleanup

                    with SessionLocal() as db:
                        res = run_cleanup(db, target="both", dry_run=False)
                    log.info(
                        "Orphan auto-cleanup",
                        extra={
                            "event": "orphan_cleanup",
                            "deleted_disk": res["deleted_disk"],
                            "deleted_db": res["deleted_db"],
                        },
                    )
                else:
                    from modules.files.cleanup import scan_and_report

                    scan_and_report()
            except Exception:  # pragma: no cover - defensive
                log.exception("Orphan scan failed")

    return app


def run(app: FastAPI, host: str, port: int) -> None:
    """Run a module app with uvicorn, delegating logging to our own config."""
    import uvicorn

    setup_logging()
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=False,
        log_config=None,  # we own logging (see modules.user.logging_config)
        access_log=False,  # our request middleware logs structurally
    )
