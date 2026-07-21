# -*- coding: utf-8 -*-
"""
File Server v4.3 — main application entry point.
Assembles FastAPI app, registers routers, serves Web UI.
"""

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.auth import router as auth_router
from app.admin import router as admin_router
from app.files import router as files_router
from app.categories import router as categories_router
from app.database import init_db

log = logging.getLogger("fileserver")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title="File Server",
    version="4.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    response = await call_next(request)
    duration = (time.time() - start) * 1000
    log.info(f"{request.method} {request.url.path} → {response.status_code} ({duration:.0f}ms)")
    return response


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


# Register API routers
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(files_router)
app.include_router(categories_router)


# ---------------------------------------------------------------------------
# Web UI — serve index.html (re-reads from disk on every request)
# ---------------------------------------------------------------------------
def _load_html() -> str:
    """Load index.html from disk with utf-8 encoding."""
    html_path = Path(__file__).parent.parent / "index.html"
    if not html_path.exists():
        return "<h1>index.html not found</h1>"
    return html_path.read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=_load_html())


# ---------------------------------------------------------------------------
# Startup: init database
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    init_db()
    log.info("File Server v4.3 started")
