FROM python:3.13-slim

WORKDIR /app

# Install system deps (none needed currently, kept for future extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create volume for persistent data
VOLUME ["/app/uploads", "/app/server.db"]

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/docs || exit 1

EXPOSE 8000

CMD ["python", "server.py"]
