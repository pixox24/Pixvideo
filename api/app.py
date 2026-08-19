# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Pixelle-Video FastAPI Application

Main FastAPI app with all routers and middleware.

Run this script to start the FastAPI server:
    uv run python api/app.py
    
Or with custom settings:
    uv run python api/app.py --host 127.0.0.1 --port 8080 --reload
"""

import sys
from pathlib import Path

# Add project root to sys.path for module imports
# This ensures imports work correctly in both development and packaged environments
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import argparse
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from api.config import api_config
from api.dependencies import get_pixelle_video, shutdown_pixelle_video

# Import routers
from api.routers import (
    configuration_router,
    content_router,
    files_router,
    frame_router,
    health_router,
    history_router,
    image_router,
    llm_router,
    projects_router,
    resources_router,
    specialist_router,
    style_slots_router,
    tasks_router,
    tts_router,
    uploads_router,
    video_router,
    workbench_router,
)
from api.tasks import task_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("🚀 Starting Pixelle-Video API...")
    await task_manager.start()
    try:
        from pixelle_video.utils.ffmpeg_scratch import cleanup_ffmpeg_scratch

        cleanup_ffmpeg_scratch(max_age_hours=24.0)
    except Exception as exc:
        logger.warning(f"Failed to clean ffmpeg scratch: {exc}")
    try:
        core = await get_pixelle_video()
    except Exception as exc:
        logger.warning(f"Failed to initialize persisted workbench jobs: {exc}")
    else:
        if core.project_generation:
            try:
                await core.project_generation.resume_active_runs()
            except Exception as exc:
                logger.warning(f"Failed to resume project generation runs: {exc}")
                try:
                    core.project_generation.fail_all_active_runs(
                        error=f"Failed to resume after restart: {exc}"
                    )
                except Exception as fail_exc:
                    logger.warning(f"Failed to abandon active generation runs: {fail_exc}")
        if core.workbench_jobs:
            try:
                # Scene image/tts jobs are in-memory only — abandon so UI stops polling.
                core.workbench_jobs.abandon_orphan_scene_jobs()
            except Exception as exc:
                logger.warning(f"Failed to abandon orphan workbench jobs: {exc}")
            try:
                await core.workbench_jobs.resume_active_exports(task_manager)
            except Exception as exc:
                logger.warning(f"Failed to resume workbench exports: {exc}")
    logger.info("✅ Pixelle-Video API started successfully\n")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Pixelle-Video API...")
    await task_manager.stop()
    await shutdown_pixelle_video()
    logger.info("✅ Pixelle-Video API shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Pixelle-Video API",
    description="""
    ## Pixelle-Video - AI Video Generation Platform API
    
    ### Features
    - 🤖 **LLM**: Large language model integration
    - 🔊 **TTS**: Text-to-speech synthesis
    - 🎨 **Image**: AI image generation
    - 📝 **Content**: Automated content generation
    - 🎬 **Video**: End-to-end video generation
    
    ### Video Generation Modes
    - **Sync**: `/api/video/generate/sync` - For small videos (< 30s)
    - **Async**: `/api/video/generate/async` - For large videos with task tracking
    
    ### Getting Started
    1. Check health: `GET /health`
    2. Generate narrations: `POST /api/content/narration`
    3. Generate video: `POST /api/video/generate/sync` or `/async`
    4. Track task progress: `GET /api/tasks/{task_id}`
    """,
    version="0.1.0",
    docs_url=api_config.docs_url,
    redoc_url=api_config.redoc_url,
    openapi_url=api_config.openapi_url,
    lifespan=lifespan,
)

# Add CORS middleware
if api_config.cors_enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=api_config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(f"CORS enabled for origins: {api_config.cors_origins}")

# Include routers
# Health check (no prefix)
app.include_router(health_router)

# API routers (with /api prefix)
app.include_router(llm_router, prefix=api_config.api_prefix)
app.include_router(tts_router, prefix=api_config.api_prefix)
app.include_router(image_router, prefix=api_config.api_prefix)
app.include_router(content_router, prefix=api_config.api_prefix)
app.include_router(video_router, prefix=api_config.api_prefix)
app.include_router(tasks_router, prefix=api_config.api_prefix)
app.include_router(files_router, prefix=api_config.api_prefix)
app.include_router(resources_router, prefix=api_config.api_prefix)
app.include_router(frame_router, prefix=api_config.api_prefix)
app.include_router(configuration_router, prefix=api_config.api_prefix)
app.include_router(history_router, prefix=api_config.api_prefix)
app.include_router(workbench_router, prefix=api_config.api_prefix)
app.include_router(projects_router, prefix=api_config.api_prefix)
app.include_router(uploads_router, prefix=api_config.api_prefix)
app.include_router(specialist_router, prefix=api_config.api_prefix)
app.include_router(style_slots_router, prefix=api_config.api_prefix)


_frontend_dist = _project_root / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        """Development fallback when the React bundle has not been built yet."""
        return {
            "service": "Pixelle-Video API",
            "web_ui": "Run `npm run build` in frontend/ to serve the React workbench here.",
            "docs": api_config.docs_url,
            "health": "/health",
        }


if __name__ == "__main__":
    import uvicorn
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Start Pixelle-Video API Server")
    parser.add_argument("--host", default=api_config.host, help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    
    args = parser.parse_args()
    
    # Print startup banner
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    Pixelle-Video API Server                      ║
╚══════════════════════════════════════════════════════════════╝

Starting server at http://{args.host}:{args.port}
API Docs: http://{args.host}:{args.port}/docs
ReDoc: http://{args.host}:{args.port}/redoc

Press Ctrl+C to stop the server
""")
    
    # Start server
    uvicorn.run(
        "api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
