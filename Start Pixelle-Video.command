#!/bin/bash
set -u

# macOS Finder shortcut for launching the Pixelle-Video React workbench.
cd "$(dirname "$0")"

# Prefer ffmpeg-full (libass/subtitles/drawtext) over the default Homebrew ffmpeg.
# Without libass, styled ASS subtitles fall back to a static PIL overlay.
for _ffdir in /opt/homebrew/opt/ffmpeg-full/bin /usr/local/opt/ffmpeg-full/bin; do
  if [ -x "$_ffdir/ffmpeg" ]; then
    export PATH="$_ffdir:$PATH"
    break
  fi
done
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
  echo "On macOS, install it with: brew install ffmpeg-full"
  echo
elif ! ffmpeg -hide_banner -filters 2>/dev/null | grep -q "subtitles"; then
  echo "[WARN] Current ffmpeg has no 'subtitles' filter (libass)."
  echo "Styled subtitles (punctuation split / custom font) need: brew install ffmpeg-full"
  echo "Then restart this app so PATH picks up /opt/homebrew/opt/ffmpeg-full/bin"
  echo
else
  echo "ffmpeg: $(command -v ffmpeg) (subtitles filter OK)"
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
