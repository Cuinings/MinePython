@echo off
cd /d "%~dp0"

:: MinePython 一键启动（HTTP 模式）
:: 优先使用项目内虚拟环境 .venv313，其次 .venv，最后系统 python

if exist ".venv313\Scripts\python.exe" (
    echo [MinePython] 使用 .venv313 虚拟环境启动（HTTP :8000）...
    ".venv313\Scripts\python.exe" server.py
) else if exist ".venv\Scripts\python.exe" (
    echo [MinePython] 使用 .venv 虚拟环境启动（HTTP :8000）...
    ".venv\Scripts\python.exe" server.py
) else (
    echo [MinePython] 未找到虚拟环境，尝试系统 python...
    python server.py
)

pause
