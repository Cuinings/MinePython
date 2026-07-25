#!/bin/sh
set -e

# The app runs as the non-root user (uid 10001) for least privilege.
# Bind-mounted host files (./.env, ./.fernet_key) keep their host
# ownership, so the runtime user can't write them -- and admin-UI changes
# to settings (persisted via _write_env_key) would silently fail to stick.
# Fix ownership here (we are still root), then drop privileges.
chown appuser:appuser /app/.env 2>/dev/null || true
chown appuser:appuser /app/.fernet_key 2>/dev/null || true

# Drop to the non-root user and exec the app (replaces this shell so
# signals are delivered correctly).
exec su appuser -s /bin/sh -c "python server.py"
