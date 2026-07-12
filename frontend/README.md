# Pixvideo React Workbench

This directory contains the React/Vite workbench. A production bundle is served by FastAPI at `http://localhost:8000` when `frontend/dist` exists.

## Requirements

- Node.js 22+
- The Pixvideo FastAPI backend for API-backed workflows

## Commands

```bash
# Install locked dependencies
npm ci

# Run the Vite development server at http://localhost:5173
npm run dev

# Type-check the frontend
npm run lint

# Build frontend/dist for FastAPI, Docker, or the Windows package
npm run build
```

To serve the production bundle locally, run the build command above and then start the backend from the project root:

```bash
uv run python api/app.py --host 127.0.0.1 --port 8000
```
