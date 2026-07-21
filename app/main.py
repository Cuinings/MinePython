# -*- coding: utf-8 -*-
"""
File Server v4.2 — main application entry point.
Assembles FastAPI app, registers routers, serves Web UI.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.auth import router as auth_router
from app.admin import router as admin_router
from app.files import router as files_router
from app.categories import router as categories_router
from app.database import init_db

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = FastAPI(
    title="File Server",
    version="4.2.0",
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
