@echo off
cd /d "%~dp0"
if exist ".venv313\Scripts\python.exe" (
    ".venv313\Scripts\python.exe" start_https.py
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" start_https.py
) else (
    python start_https.py
)
pause
