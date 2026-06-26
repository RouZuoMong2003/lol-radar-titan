@echo off
REM =============================================================================
REM LoL Radar Engine - 零配置启动脚本 (Windows)
REM
REM 用法：
REM   start.bat           启动 Flask (http://127.0.0.1:8080)
REM   start.bat static    仅起内置静态服务器（不需任何依赖）
REM
REM 首次运行会自动建 .venv\ 并装依赖。
REM =============================================================================
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo [X] Python not found. Install Python 3.10+ from https://www.python.org/downloads/
  echo     and tick "Add Python to PATH" during install.
  pause
  exit /b 1
)

python -c "import sys; print('Python: %%d.%%d' %% sys.version_info[:2])"

if "%1"=="static" (
  if not defined PORT set PORT=8080
  echo Static mode: http://127.0.0.1:%PORT%/
  cd web
  python -m http.server %PORT%
  exit /b
)

if not exist ".venv\" (
  echo Creating virtualenv .venv\ ...
  python -m venv .venv
)

call .venv\Scripts\activate.bat

if not exist ".venv\.deps_installed" (
  echo Installing dependencies ...
  python -m pip install --upgrade pip >nul
  python -m pip install -r requirements.txt
  echo. > .venv\.deps_installed
)

if not defined PORT set PORT=8080
echo.
echo LoL Radar Engine starting ...
echo   Radar : http://127.0.0.1:%PORT%/
echo   Charts: http://127.0.0.1:%PORT%/charts.html
echo   API   : http://127.0.0.1:%PORT%/api/seasons
echo   Ctrl+C to stop
echo.

python server\app.py