# Pixvideo

## AI Editing Workbench

Quick Create can save 1-100 scenes as a project and open a three-column editing workbench. Each scene supports narration and prompt edits, image or TTS regeneration, project-local image uploads, explicit candidate selection, and an audio-driven single-track timeline where visuals may be held longer but never shortened below their audio.

Export preflight freezes an immutable revision and reuses the existing subtitle, BGM, template, and FFmpeg pipeline. Historical tasks can be opened without deleting the original history, while direct video generation remains available as a fast bypass. This release does not include a cross-project asset library, collaboration, or a full multi-track editor.

Pixvideo is an AI short-video generation tool. It can connect script generation, voice synthesis, image/video generation, template rendering, and final video composition from a topic, script, or uploaded media.

## Features

- Topic-to-video generation with script, prompts, narration, visuals, and final output.
- Custom script mode for turning existing text into narrated videos.
- Multiple pipelines, including standard videos, image-to-video, digital human, and motion transfer.
- Browser-based workbench for configuration, task creation, previews, and history.
- Production-safe Quick Create with per-scene prompts, independent batch jobs, preflight review, draft recovery, idempotent submission, cancellation, and consistent history state.
- Configurable LLM, TTS, ComfyUI/RunningHub workflows, templates, and video settings.

## Requirements

- Python 3.11+
- Node.js 22+
- uv
- ffmpeg

On macOS, install ffmpeg with Homebrew:

```bash
brew install ffmpeg
```

## Quick Start

```bash
git clone <your-repo-url>
cd Pixvideo
uv sync
cp config.example.yaml config.yaml
cd frontend && npm ci && npm run build && cd ..
uv run python api/app.py --host 127.0.0.1 --port 8000
```

Then open:

```text
http://localhost:8000
```

You can also use the launch script:

```bash
./start_web.sh
```

On Windows:

```bat
start_web.bat
```

## Configuration

Before the first run, copy and edit the example config:

```bash
cp config.example.yaml config.yaml
```

Common settings include:

- LLM provider and API key
- TTS provider
- Image/video generation workflows
- Output directory
- Template and video parameters

## Useful Commands

```bash
# Build and start the Web UI and API
cd frontend && npm run build && cd ..
uv run python api/app.py --host 127.0.0.1 --port 8000

# Local runs reuse resources/example.png and do not call image providers by default
# Use this only when real image generation is explicitly required
PIXELLE_USE_REAL_IMAGE_API=1 uv run python api/app.py --host 127.0.0.1 --port 8000

# Optional: use another existing image for the offline flow
PIXELLE_TEST_IMAGE_PATH=/absolute/path/existing.png uv run python api/app.py

# Frontend development server with hot reload (port 5173)
cd frontend && npm run dev

# Run the example generator
uv run python examples/generate_video.py

# Run tests
uv run --extra dev pytest

# Lint
uv run --extra dev ruff check .
```

## Project Structure

```text
api/             FastAPI API
frontend/        React Web workbench
pixelle_video/   Core generation logic and services
templates/       Video frame templates
resources/       Example assets and static files
tests/           Test suite
docs/            Documentation
```

Note: the Python package directory is still named `pixelle_video/` because it is part of the import path. Renaming it requires updating imports and tests together.

## License

Apache-2.0
