# -*- coding: utf-8 -*-
"""User module service layer (ARCH-6).

Holds business logic extracted from the FastAPI routers so that the route
modules stay thin (request parsing + permission guards + response shaping).
Routers import from here; symbols still consumed by other modules are
re-exported from their original homes (e.g. :mod:`modules.user.auth`
re-exports ``authenticate_token`` / ``purge_expired_tokens``).
"""

from modules.user.services.auth_service import (
    authenticate_token,
    clear_ip_failures,
    clear_login_failures,
    ip_throttled,
    login_locked,
    login_user,
    purge_expired_tokens,
    register_ip_failure,
    register_login_failure,
)
from modules.user.services.user_service import (
    approve_user,
    batch_user_action,
    change_password,
    create_user,
    deactivate_user,
    delete_user,
    reject_user,
    register_user,
    update_user,
    user_to_dict,
)

__all__ = [
    "authenticate_token",
    "clear_ip_failures",
    "clear_login_failures",
    "ip_throttled",
    "login_locked",
    "login_user",
    "purge_expired_tokens",
    "register_ip_failure",
    "register_login_failure",
    "approve_user",
    "batch_user_action",
    "change_password",
    "create_user",
    "deactivate_user",
    "delete_user",
    "reject_user",
    "register_user",
    "update_user",
    "user_to_dict",
]
