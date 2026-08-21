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
Video generation endpoints

Asynchronous video generation used by Quick Create.
"""

import os

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.schemas.video import (
    VideoGenerateAsyncResponse,
    VideoGenerateRequest,
)
from api.tasks import TaskType, task_manager

router = APIRouter(prefix="/video", tags=["Video Generation"])


def path_to_url(request: Request, file_path: str) -> str:
    """
    Convert file path to accessible URL
    
    Handles both absolute and relative paths, extracting the path relative
    to the output directory for URL construction.
    
    Args:
        request: FastAPI Request object (provides base_url from actual request)
        file_path: Absolute or relative file path
    
    Returns:
        Full URL to access the file
    
    Examples:
        Windows: G:\\...\\output\\20251205_233630_c939\\final.mp4
              -> http://localhost:8000/api/files/20251205_233630_c939/final.mp4
        
        Linux:   /home/user/.../output/20251205_233630_c939/final.mp4
              -> http://localhost:8000/api/files/20251205_233630_c939/final.mp4
        
        Domain:  With domain request -> https://your-domain.com/api/files/...
    """
    import os
    from pathlib import Path
    
    # Normalize path separators to forward slashes first (for cross-platform compatibility)
    file_path = file_path.replace("\\", "/")
    
    # Check if it's an absolute path (works for both Windows and Linux)
    is_absolute = os.path.isabs(file_path) or Path(file_path).is_absolute()
    
    if is_absolute:
        # Find "output" in the path and get everything after it
        # Split by / to work with normalized paths
        parts = file_path.split("/")
        try:
            output_idx = parts.index("output")
            # Get all parts after "output" and join them
            relative_parts = parts[output_idx + 1:]
            file_path = "/".join(relative_parts)
        except ValueError:
            # If "output" not in path, use the filename only
            file_path = Path(file_path).name
    else:
        # If relative path starting with "output/", remove it
        if file_path.startswith("output/"):
            file_path = file_path[7:]  # Remove "output/"
    
    # Build URL using request's base_url (automatically matches the request host)
    base_url = str(request.base_url).rstrip('/')
    return f"{base_url}/api/files/{file_path}"


def _resolve_media_size(request_body: VideoGenerateRequest) -> tuple[int, int]:
    """Resolve media dimensions from request or selected template."""
    if request_body.media_width and request_body.media_height:
        return request_body.media_width, request_body.media_height

    if request_body.composition_mode == "plain_image":
        return request_body.media_width or 1080, request_body.media_height or 1920

    if not request_body.frame_template:
        raise ValueError("frame_template is required to determine media size")

    from pixelle_video.services.frame_html import HTMLFrameGenerator
    from pixelle_video.utils.template_util import resolve_template_path

    template_path = resolve_template_path(request_body.frame_template)
    generator = HTMLFrameGenerator(template_path)
    media_width, media_height = generator.get_media_size()
    logger.debug(f"Auto-determined media size from template: {media_width}x{media_height}")
    return media_width, media_height


def _build_video_params(request_body: VideoGenerateRequest, progress_callback=None) -> dict:
    """Build PixelleVideoCore.generate_video kwargs from the API request."""
    media_width, media_height = _resolve_media_size(request_body)
    video_params = {
        "text": request_body.text,
        "pipeline": request_body.pipeline,
        "mode": request_body.mode,
        "split_mode": request_body.split_mode,
        "director_mode": request_body.director_mode,
        "density": request_body.storyboard_density,
        "target_scene_count": request_body.target_scene_count,
        "title": request_body.title,
        "n_scenes": request_body.n_scenes,
        "scenes": [
            {
                "narration": scene.narration,
                "visual_prompt": scene.visual_prompt,
                **({"visual_focus": scene.visual_focus} if scene.visual_focus else {}),
                **({"text_anchors": scene.text_anchors} if scene.text_anchors else {}),
            }
            for scene in request_body.scenes
        ] if request_body.scenes else None,
        "reuse_assets_from_task_id": request_body.reuse_assets_from_task_id,
        "min_narration_words": request_body.min_narration_words,
        "max_narration_words": request_body.max_narration_words,
        "min_image_prompt_words": request_body.min_image_prompt_words,
        "max_image_prompt_words": request_body.max_image_prompt_words,
        "media_width": media_width,
        "media_height": media_height,
        "media_workflow": request_body.media_workflow,
        "video_fps": request_body.video_fps,
        "frame_template": request_body.frame_template,
        "template_params": request_body.template_params,
        "prompt_prefix": request_body.prompt_prefix,
        "bgm_path": request_body.bgm_path,
        "bgm_volume": request_body.bgm_volume,
        "tts_inference_mode": request_body.tts_inference_mode,
        "composition_mode": request_body.composition_mode,
        "image_motion_enabled": request_body.image_motion_enabled,
        "subtitle_enabled": request_body.subtitle_enabled,
        "subtitle_style": request_body.subtitle_style.model_dump(by_alias=False)
        if request_body.subtitle_style
        else None,
        "image_motion_mode": request_body.image_motion_mode,
        "image_motion_strength": request_body.image_motion_strength,
        "image_fit_mode": request_body.image_fit_mode,
        "use_api_image": bool(request_body.use_api_image),
    }

    if request_body.tts_voice:
        video_params["tts_voice"] = request_body.tts_voice
    if request_body.tts_speed is not None:
        video_params["tts_speed"] = request_body.tts_speed
    if request_body.tts_workflow:
        video_params["tts_workflow"] = request_body.tts_workflow
    if request_body.ref_audio:
        video_params["ref_audio"] = request_body.ref_audio
    for key in ("qwen_audio_model", "qwen_audio_mode", "qwen_audio_instruction", "qwen_audio_ref_audio"):
        value = getattr(request_body, key, None)
        if value is not None:
            video_params[key] = value
    if request_body.voice_id:
        logger.warning("voice_id parameter is deprecated; mapping it to tts_voice")
        video_params["tts_voice"] = request_body.voice_id
    if request_body.minimax_model:
        video_params["minimax_model"] = request_body.minimax_model
    if request_body.minimax_emotion:
        video_params["minimax_emotion"] = request_body.minimax_emotion
    if request_body.mimo_model:
        video_params["mimo_model"] = request_body.mimo_model
    if request_body.mimo_style:
        video_params["mimo_style"] = request_body.mimo_style
    if progress_callback:
        video_params["progress_callback"] = progress_callback

    return {key: value for key, value in video_params.items() if value is not None}


@router.post("/generate/async", response_model=VideoGenerateAsyncResponse)
async def generate_video_async(
    request_body: VideoGenerateRequest,
    pixelle_video: PixelleVideoDep,
    request: Request
):
    """
    Generate video asynchronously
    
    Creates a background task for video generation.
    Returns immediately with a task_id for tracking progress.
    
    **Workflow:**
    1. Submit video generation request
    2. Receive task_id in response
    3. Poll `/api/tasks/{task_id}` to check status
    4. When status is "completed", retrieve video from result
    
    Request body includes all video generation parameters.
    See VideoGenerateRequest schema for details.
    
    Returns task_id for tracking progress.
    """
    try:
        logger.info(f"Async video generation: {request_body.text[:50]}...")
        
        # Create task
        task = task_manager.create_task(
            task_type=TaskType.VIDEO_GENERATION,
            request_params=request_body.model_dump(),
            request_key=request_body.client_request_key,
        )
        
        # Define async execution function
        async def execute_video_generation():
            """Execute video generation in background"""
            def progress_callback(event):
                current = int(event.progress * 100)
                total = 100
                if event.event_type == "frame_step":
                    message = (
                        f"Frame {event.frame_current}/{event.frame_total} "
                        f"step {event.step}: {event.action}"
                    )
                elif event.event_type == "processing_frame":
                    message = f"Processing frame {event.frame_current}/{event.frame_total}"
                else:
                    message = event.event_type
                if event.extra_info:
                    message = f"{message} - {event.extra_info}"
                task_manager.update_progress(
                    task.task_id,
                    current,
                    total,
                    message,
                    event_type=event.event_type,
                    frame_current=event.frame_current,
                    frame_total=event.frame_total,
                    step=event.step,
                    action=event.action,
                    extra_info=event.extra_info,
                )

            video_params = _build_video_params(
                request_body,
                progress_callback=progress_callback,
            )
            video_params["task_id"] = task.task_id
            result = await pixelle_video.generate_video(**video_params)
            
            # Get file size
            file_size = os.path.getsize(result.video_path) if os.path.exists(result.video_path) else 0
            
            # Convert path to URL
            video_url = path_to_url(request, result.video_path)
            
            return {
                "video_url": video_url,
                "duration": result.duration,
                "file_size": file_size
            }
        
        # Start execution
        await task_manager.execute_task(
            task_id=task.task_id,
            coro_func=execute_video_generation
        )
        
        return VideoGenerateAsyncResponse(
            task_id=task.task_id
        )
        
    except Exception as e:
        logger.error(f"Async video generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
