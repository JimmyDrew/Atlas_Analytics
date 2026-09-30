@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto setup
".venv\Scripts\python.exe" -c "import pandas, openpyxl, PIL, pypdf, tkinter" >nul 2>&1
if errorlevel 1 goto setup
goto launch
:setup
echo Installing missing project dependencies. This may take a minute.
call "Setup Atlas.cmd" --no-pause
if errorlevel 1 (
    pause
    exit /b 1
)
:launch
".venv\Scripts\python.exe" desktop_app.py
if errorlevel 1 (
    echo.
    echo If dependencies are missing, double-click Setup Atlas.cmd first.
    pause
)
