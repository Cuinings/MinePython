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
    && chown -R appuser:appuser /app
USER appuser

# Persist runtime data (uploads + sqlite db + logs + encryption key) via volumes
# declared in docker-compose.yml. Do NOT bake secrets into the image.

# Health check hits the OpenAPI docs endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

EXPOSE 8000

CMD ["python", "server.py"]
