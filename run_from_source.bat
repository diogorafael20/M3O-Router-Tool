@echo off
REM Developed by diogorafael20
setlocal

cd /d "%~dp0"

echo Developed by diogorafael20 

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 -m pip install -r requirements.txt
    py -3 meo_router_tool.py
) else (
    python -m pip install -r requirements.txt
    python meo_router_tool.py
)

pause
