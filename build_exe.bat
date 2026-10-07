@echo off
REM Developed by diogorafael
setlocal

cd /d "%~dp0"

echo.
echo Developed by diogorafael
echo A criar Ferramenta Router MEO para Windows...
echo.

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=py -3"
) else (
    set "PYTHON=python"
)

%PYTHON% --version >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Python nao foi encontrado.
    echo Instala Python a partir de https://www.python.org/downloads/windows/
    echo Confirma que a opcao "Add python.exe to PATH" esta selecionada.
    pause
    exit /b 1
)

%PYTHON% -m venv .venv-build
if %ERRORLEVEL% NEQ 0 (
    echo Falhou a criacao do ambiente de build.
    pause
    exit /b 1
)

call ".venv-build\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo Falhou a instalacao das dependencias de build.
    pause
    exit /b 1
)

pyinstaller ^
    --clean ^
    --onefile ^
    --console ^
    --name "MEO-Router-Tool" ^
    meo_router_tool.py

if %ERRORLEVEL% NEQ 0 (
    echo A build falhou.
    pause
    exit /b 1
)

echo.
echo Concluido.
echo O EXE standalone esta aqui:
echo %CD%\dist\MEO-Router-Tool.exe
echo.
pause
