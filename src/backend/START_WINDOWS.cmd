@echo off
setlocal
cd /d "%~dp0"
title Perishable Food Inventory - M1 Backend
echo This starts the local synthetic-data demonstration backend.
echo.
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher was not found. Install Python 3.12 from python.org.
  echo Then close this window and double-click START_WINDOWS.cmd again.
  pause
  exit /b 1
)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo Python 3.11 or newer is required. Python 3.12 is recommended.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating the project Python environment...
  py -3 -m venv .venv
  if errorlevel 1 goto failed
)
echo Installing/checking project dependencies. Internet access is needed.
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto failed
if not exist ".env" copy /y ".env.example" ".env" >nul
if errorlevel 1 goto failed
echo Creating/upgrading the database...
".venv\Scripts\python.exe" -m alembic upgrade head
if errorlevel 1 goto failed
echo Loading fictional demo data if it has not already been loaded...
".venv\Scripts\python.exe" -m scripts.seed
if errorlevel 1 goto failed
echo.
echo When the server reports startup complete, open:
echo http://127.0.0.1:8000/docs
echo Keep this window open. Press Ctrl+C to stop the server.
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Setup stopped. Read the error above or send a screenshot to your teammate.
echo If port 8000 is in use, stop the previous server window first.
pause
exit /b 1
