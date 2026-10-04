@echo off
REM Start media-tools locally (Windows).
cd /d "%~dp0"

if not exist ".venv" (
  echo Creating virtualenv...
  python -m venv .venv
)
.venv\Scripts\pip install -q -r requirements.txt

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo WARNING: ffmpeg not found - audio extraction ^(MP3/M4A/WAV^) will not work.
)

echo Starting media-tools on http://127.0.0.1:8000 ...
.venv\Scripts\python -m app
