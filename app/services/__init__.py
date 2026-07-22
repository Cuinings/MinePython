# -*- coding: utf-8 -*-
"""Service layer (ARCH-6).

Holds business logic extracted from the FastAPI routers so that
``app/*_router`` modules stay thin (request parsing + permission guards +
response shaping only). Routers import from here; symbols still consumed by
other modules are re-exported from their original homes (e.g.
:mod:`app.auth` re-exports ``authenticate_token`` / ``purge_expired_tokens``).
"""
