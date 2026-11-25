@echo off
setlocal
cd /d "%~dp0"
echo === Fact Checker setup (Windows) ===

set NEED_RESTART=0

where winget >nul 2>&1
if errorlevel 1 (
  echo [!] winget not found. Install "App Installer" from the Microsoft Store, or install uv, Node.js and Ollama manually.
  goto :check
)

where uv >nul 2>&1
if errorlevel 1 (
  echo Installing uv...
  winget install -e --id astral-sh.uv --accept-source-agreements --accept-package-agreements
  set NEED_RESTART=1
)
where node >nul 2>&1
if errorlevel 1 (
  echo Installing Node.js LTS...
  winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
  set NEED_RESTART=1
)
where ollama >nul 2>&1
if errorlevel 1 (
  echo Installing Ollama...
  winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
  set NEED_RESTART=1
)

if "%NEED_RESTART%"=="1" (
  echo.
  echo Tools were just installed. Close this window, open a NEW terminal, and run setup.bat again
  echo so the updated PATH is picked up.
  pause
  exit /b 0
)

:check
for %%T in (uv node npm ollama) do (
  where %%T >nul 2>&1
  if errorlevel 1 (
    echo [X] %%T is not on PATH. Install it, open a new terminal, and rerun setup.bat.
    pause
    exit /b 1
  )
)

echo.
echo === Backend dependencies ===
pushd backend
uv sync --python 3.12
if errorlevel 1 ( popd & echo [X] Backend install failed. & pause & exit /b 1 )
popd

echo.
echo === Frontend dependencies ===
pushd frontend
call npm install
if errorlevel 1 ( popd & echo [X] Frontend install failed. & pause & exit /b 1 )
popd

echo.
echo === Ollama models ===
ollama list >nul 2>&1
if errorlevel 1 (
  echo Starting Ollama server...
  start "Ollama" /min ollama serve
  timeout /t 6 /nobreak >nul
)
echo Pulling qwen3:14b (about 9 GB, can take a while)...
ollama pull qwen3:14b
if errorlevel 1 (
  echo [!] qwen3:14b pull failed. If the tag does not exist, run:  ollama pull gemma3:12b
  echo     and set FC_REASONING_MODEL=gemma3:12b before running run.bat
)
ollama pull bge-m3
if errorlevel 1 echo [!] bge-m3 pull failed. Retrieval ranking will fall back to keyword overlap.

echo.
echo Setup finished. Start the app with run.bat
pause
