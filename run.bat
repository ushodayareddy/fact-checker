@echo off
setlocal
cd /d "%~dp0"

for %%T in (uv npm ollama) do (
  where %%T >nul 2>&1
  if errorlevel 1 (
    echo [X] %%T not found. Run setup.bat first.
    pause
    exit /b 1
  )
)

ollama list >nul 2>&1
if errorlevel 1 (
  echo Starting Ollama server...
  start "Ollama" /min ollama serve
  timeout /t 6 /nobreak >nul
)

echo Starting backend on http://127.0.0.1:8000 ...
start "Fact Checker Backend" /d "%~dp0backend" cmd /k uv run uvicorn app.main:app --port 8000

echo Starting frontend on http://localhost:5173 ...
start "Fact Checker Frontend" /d "%~dp0frontend" cmd /k npm run dev

timeout /t 8 /nobreak >nul
start "" http://localhost:5173
echo.
echo Close the Backend and Frontend windows to stop the app.
