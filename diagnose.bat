@echo off
REM Quick diagnostic for MinePython HTTPS startup issues.
REM Run this in the project root; it prints each dependency check and pauses
REM only on errors so you can read them.

cd /d "%~dp0"

echo ============================================================
echo  MinePython diagnostics
echo ============================================================
echo.

echo [1] Python interpreter in .venv?
if exist ".venv\Scripts\python.exe" (
    echo       found: .venv\Scripts\python.exe
    .venv\Scripts\python.exe --version
) else (
    echo       NOT FOUND (falling back to PATH)
    python --version
)
echo.

echo [2] cryptography module?
.venv\Scripts\python.exe -c "import cryptography; print('       cryptography', cryptography.__version__)" 2>nul
if errorlevel 1 (
    python -c "import cryptography; print('       cryptography', cryptography.__version__)" 2>nul
    if errorlevel 1 echo       NOT INSTALLED -- run: pip install cryptography
)
echo.

echo [3] WebUSB ADB bundle present?
if exist "static\js\webadb.bundle.js" (
    for %%A in ("static\js\webadb.bundle.js") do echo       webadb.bundle.js %%~zA bytes
) else (
    echo       MISSING -- run: python download_webadb.py
)
if exist "static\js\webadb-importmap.json" (
    echo       webadb-importmap.json ok
) else (
    echo       webadb-importmap.json MISSING
)
if exist "static\js\vendor" (
    for /f %%B in ('dir /b /a-d "static\js\vendor" 2^>nul ^| find /v /c ""') do echo       vendor dirs: %%B
) else (
    echo       vendor/ MISSING
)
echo.

echo [4] SSL cert present?
if exist "ssl\cert.pem" (
    for %%A in ("ssl\cert.pem") do echo       cert.pem %%~zA bytes
) else (
    echo       cert.pem MISSING -- will be generated on next run_https.bat
)
if exist "ssl\key.pem" (
    echo       key.pem ok
) else (
    echo       key.pem MISSING
)
echo.

echo [5] Port 8000 in use?
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo       PID %%a is holding port 8000
)
if errorlevel 1 echo       port 8000 is free
echo.

echo [6] gen_cert.py dry-run (auto-detect LAN IPs)?
.venv\Scripts\python.exe gen_cert.py 2>nul
if errorlevel 1 python gen_cert.py 2>nul
echo.

echo [7] Detected IPs (via PowerShell):
powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' }).IPAddress"
echo.

echo ============================================================
echo  Diagnostic complete. Press any key to exit.
pause >nul
