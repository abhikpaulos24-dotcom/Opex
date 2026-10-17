@echo off
REM OpEx one-click start for Windows. Double-click this file.
REM It installs what it needs the first time (about 3-5 minutes), then opens OpEx in your browser.
cd /d "%~dp0"
echo.
echo   Starting OpEx - keep this window open while you use the app.
echo.

set "UV=uv"
where uv >nul 2>nul
if errorlevel 1 (
  if not exist "%USERPROFILE%\.local\bin\uv.exe" (
    echo   Installing uv ^(a small tool that installs the right Python for OpEx^)...
    powershell -ExecutionPolicy ByPass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
  )
  set "UV=%USERPROFILE%\.local\bin\uv.exe"
)

if not exist .env (
  echo   Creating your settings file ^(.env^)...
  copy .env.example .env >nul
)
if not exist .venv (
  echo   Setting up Python 3.12...
  "%UV%" venv .venv --python 3.12
)
echo   Installing OpEx's Python packages ^(first time only takes a few minutes^)...
"%UV%" pip install --quiet --python .venv\Scripts\python.exe -r backend\requirements.txt
if errorlevel 1 goto :failed

if not exist models\rul_model.joblib (
  echo   Training the AI models from the datasets ^(about 1 minute^)...
  pushd backend
  ..\.venv\Scripts\python.exe -m pipeline.run_all
  popd
)

echo.
echo   OpEx is starting at http://localhost:8000  ^(close this window to stop it^)
echo.
start "" cmd /c "timeout /t 6 >nul & start http://localhost:8000"
.venv\Scripts\uvicorn.exe app.main:app --app-dir backend --host 127.0.0.1 --port 8000
goto :eof

:failed
echo   Something went wrong while installing. See HOW_TO_RUN.md, section "If something goes wrong".
pause
