@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" if not exist ".venv\pyvenv.cfg" (
    echo Found an incomplete virtual environment. Moving it aside.
    ren ".venv" ".venv-broken-%RANDOM%"
)
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m ensurepip --upgrade
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements-tested.txt
if errorlevel 1 goto failed
echo.
echo Setup complete. Double-click Open Atlas.cmd.
if /i not "%~1"=="--no-pause" pause
exit /b 0
:failed
echo Setup failed. Check the message above and confirm Python is installed.
if /i not "%~1"=="--no-pause" pause
exit /b 1
