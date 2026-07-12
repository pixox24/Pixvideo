#!/bin/bash
set -u

# macOS Finder shortcut for launching the Pixelle-Video React workbench.
cd "$(dirname "$0")"

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

clear
echo "Starting Pixelle-Video..."
echo "Project folder: $(pwd)"
echo

if ! command -v uv >/dev/null 2>&1; then
  echo "[ERROR] uv was not found."
  echo "Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
  echo
  read -r -p "Press Enter to close this window..."
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[WARN] ffmpeg was not found. The Web UI can start, but video generation may fail."
  echo "On macOS, install it with: brew install ffmpeg"
  echo
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[ERROR] npm was not found. Install Node.js 22+ first."
  echo
  read -r -p "Press Enter to close this window..."
  exit 1
fi

if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend dependencies..."
  (cd frontend && npm ci)
fi

echo "Building React workbench..."
(cd frontend && npm run build)

echo "Opening http://localhost:8000 ..."
(sleep 3 && open "http://localhost:8000") >/dev/null 2>&1 &

uv run python api/app.py --host 127.0.0.1 --port 8000

status=$?
echo
echo "Pixelle-Video exited with status $status."
read -r -p "Press Enter to close this window..."
exit "$status"
