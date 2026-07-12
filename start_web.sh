#!/bin/bash
# Build and serve the Pixelle-Video React workbench.

set -e

cd "$(dirname "$0")"

echo "🚀 Building and starting Pixelle-Video..."
echo ""

if ! command -v npm >/dev/null 2>&1; then
    echo "❌ Error: npm was not found. Install Node.js 22+ first."
    exit 1
fi

if [ ! -d frontend/node_modules ]; then
    echo "📦 Installing frontend dependencies..."
    (cd frontend && npm ci)
fi

echo "🏗️  Building React workbench..."
(cd frontend && npm run build)

echo "🌐 Web UI & API: http://127.0.0.1:8000"
echo "📚 API Docs:     http://127.0.0.1:8000/docs"
exec uv run python api/app.py --host 127.0.0.1 --port 8000
