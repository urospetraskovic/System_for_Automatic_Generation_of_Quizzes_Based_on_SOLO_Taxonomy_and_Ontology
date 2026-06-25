@echo off
REM Start SOLO Quiz Generator (Ollama + Flask backend + React frontend).
REM Mirrors the manual flow documented in START_GUIDE.md.
REM Each service opens in its own window so you can see its logs and Ctrl-C it independently.

setlocal
set "ROOT=%~dp0"

echo ========================================
echo SOLO Taxonomy Quiz Generator
echo ========================================
echo.

REM --- Prerequisites ---

if not exist "%ROOT%backend\venv\Scripts\python.exe" (
    echo [ERROR] Backend venv not found at %ROOT%backend\venv
    echo Create it with:
    echo     cd backend
    echo     python -m venv venv
    echo     venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

if not exist "%ROOT%frontend\node_modules" (
    echo [ERROR] frontend\node_modules not found.
    echo Install with:
    echo     cd frontend
    echo     npm install
    pause
    exit /b 1
)

REM Ollama is optional: only needed for local LLM generation. Detect it; skip if absent.
set "OLLAMA_EXE="
if exist "%USERPROFILE%\AppData\Local\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=1"
if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_EXE=1"

REM --- Launch services in their own console windows ---

if defined OLLAMA_EXE (
    echo [1/3] Starting Ollama on port 11435...
    start "Ollama"  powershell.exe -NoExit -NoProfile -ExecutionPolicy Bypass -File "%ROOT%ollama.ps1" serve
) else (
    echo [1/3] Ollama not installed - skipping. Local generation disabled; rest of the app runs normally.
)

echo [2/3] Starting backend (Flask API on :5000)...
start "Backend" cmd /k "cd /d "%ROOT%backend" && "%ROOT%backend\venv\Scripts\python.exe" app.py"

echo [3/3] Starting frontend (React dev server on :3000)...
start "Frontend" cmd /k "cd /d "%ROOT%frontend" && npm start"

echo.
echo ========================================
echo Services started in separate windows:
echo   Ollama   http://127.0.0.1:11435
echo   Backend  http://localhost:5000
echo   Frontend http://localhost:3000
echo.
echo Close each window (or Ctrl-C inside it) to stop that service.
echo ========================================
echo.

endlocal
