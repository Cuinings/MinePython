@echo off
setlocal
cd /d %~dp0

echo [webadb] Checking Node.js on this server ...
where node >nul 2>&1
if errorlevel 1 (
    echo [webadb] Node.js is NOT installed on this server.
    echo [webadb] Trying Python fallback (download_webadb.py) ...
    where python >nul 2>&1
    if not errorlevel 1 (
        python download_webadb.py
        if errorlevel 1 (
            echo [webadb] Python fallback failed.
            pause
            exit /b 1
        )
        pause
        exit /b 0
    )
    echo [webadb] Python is also NOT available.
    echo [webadb] Please install Node.js LTS from https://nodejs.org , then re-run this script.
    echo [webadb] (Or run: winget install OpenJS.NodeJS)
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version') do set NVER=%%i
echo [webadb] Node.js %NVER% found.

if not exist _webadb_build mkdir _webadb_build
cd _webadb_build

if not exist package.json (
    echo {"name":"webadb-build","version":"1.0.0","private":true} > package.json
)

echo [webadb] Installing @yume-chan/adb@0.0.19 + backend + esbuild ...
call npm install --no-audit --no-fund --silent @yume-chan/adb@0.0.19 @yume-chan/adb-backend-webusb@0.0.19 esbuild
if errorlevel 1 (
    echo [webadb] npm install failed. Check network / npm registry access.
    pause
    exit /b 1
)

echo [webadb] Writing entry file ...
(
echo export { Adb } from "@yume-chan/adb";
echo export { AdbWebUsbBackend } from "@yume-chan/adb-backend-webusb";
) > entry.mjs

echo [webadb] Bundling to static/js/webadb.bundle.js ...
call .\node_modules\.bin\esbuild entry.mjs --bundle --format=esm --target=chrome90 --outfile=../static/js/webadb.bundle.js
if errorlevel 1 (
    echo [webadb] esbuild failed.
    pause
    exit /b 1
)

cd ..
echo [webadb] DONE. Created: static/js/webadb.bundle.js
echo [webadb] Next: restart the server (run_https.bat) and open the page over HTTPS.
pause
