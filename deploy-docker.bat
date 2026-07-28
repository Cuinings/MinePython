@echo off
cd /d "%~dp0"
setlocal

echo [1/3] Preparing host secret files (compose bind-mount needs them to exist)...
if not exist .jwt_secret ( type nul > .jwt_secret && echo       created empty .jwt_secret )
if not exist .env ( type nul > .env && echo       created empty .env )

echo [2/3] Building and starting container...
docker compose up -d --build

echo [3/3] Container status:
docker compose ps

echo.
echo Deploy finished. Open http://localhost:8000
echo Admin login: admin / admin123  (change the password ASAP)
echo DB migrations (incl. the new suggestions table) are applied automatically on startup.
endlocal
