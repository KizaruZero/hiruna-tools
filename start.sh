#!/usr/bin/env bash
# Start media-tools locally.
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "WARNING: ffmpeg not found — audio extraction (MP3/M4A/WAV) will not work."
  echo "Install it:  sudo apt install ffmpeg   (or: brew install ffmpeg)"
fi

if [ -f ".env" ]; then
  set -a; . ./.env; set +a
fi

echo "Starting media-tools on http://${HOST:-127.0.0.1}:${PORT:-8000} ..."
.venv/bin/python -m app
