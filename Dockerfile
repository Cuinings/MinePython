FROM python:3.13-slim

WORKDIR /app

# Install system deps (curl is used by the healthcheck below).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY . .

# Run as a non-root user (least privilege). Create the runtime data dirs and
# hand ownership to that user so uploads / db / logs / fernet key are writable.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/uploads /app/logs \
    && touch /app/.fernet_key \
    && chown -R appuser:appuser /app \
    && chmod +x /entrypoint.sh

# The entrypoint runs as ROOT (no USER directive below) so it can chown the
# bind-mounted host files (./.env, ./.fernet_key) to the non-root runtime
# user. It then drops privileges via su before launching the app -- that is
# what makes admin-UI setting changes persist to the mounted .env.
ENTRYPOINT ["/entrypoint.sh"]

# Health check hits the OpenAPI docs endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

EXPOSE 8000
