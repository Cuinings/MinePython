#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "[1/3] Preparing host secret files..."
[ -f .jwt_secret ] || : > .jwt_secret
[ -f .env ] || : > .env

echo "[2/3] Building and starting container..."
docker compose up -d --build

echo "[3/3] Container status:"
docker compose ps

echo
echo "Deploy finished. Open http://localhost:8000"
echo "Admin login: admin / admin123  (change the password ASAP)"
echo "DB migrations (incl. the new suggestions table) are applied automatically on startup."
