"""Async API endpoint for image-to-video generation."""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.dependencies import PixelleVideoDep
from api.routers.uploads import resolve_uploaded_file_keys
from api.routers.video import path_to_url
from api.schemas.specialist import ImageToVideoGenerateRequest
from api.schemas.uploads import UploadPurpose
from api.schemas.video import VideoGenerateAsyncResponse
from api.tasks import TaskType, task_manager
from pixelle_video.services.specialist_video import (
    execute_video_workflow,
    persist_specialist_video,
)

router = APIRouter(prefix="/specialist", tags=["Specialist Generation"])


@router.post("/image-to-video/generate/async", response_model=VideoGenerateAsyncResponse)
async def generate_image_to_video_async(
    body: ImageToVideoGenerateRequest,
    pixelle_video: PixelleVideoDep,
    request: Request,
) -> VideoGenerateAsyncResponse:
    """Generate a video from one uploaded reference image and an I2V workflow."""
    image_path = resolve_uploaded_file_keys([body.image_file_key], UploadPurpose.IMAGE_TO_VIDEO)[0]
    task = task_manager.create_task(
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"pipeline": "image_to_video", **body.model_dump()},
    )

    async def execute_image_to_video():
        try:
            task_manager.update_progress(task.task_id, 5, 100, "Preparing image-to-video workflow")
            final_video_path = await execute_video_workflow(
                pixelle_video,
                body.workflow_key,
                {"image": image_path, "prompt": body.prompt},
                task.task_id,
            )
            task_manager.update_progress(task.task_id, 90, 100, "Saving generated video")
            await persist_specialist_video(
                pixelle_video,
                task.task_id,
                "image_to_video",
                body.model_dump(),
                final_video_path,
            )
            task_manager.update_progress(task.task_id, 100, 100, "Completed")
            return {"video_url": path_to_url(request, final_video_path)}
        except Exception as error:
            await persist_specialist_video(
                pixelle_video,
                task.task_id,
                "image_to_video",
                body.model_dump(),
                error=str(error),
            )
            raise

    await task_manager.execute_task(task.task_id, execute_image_to_video)
    return VideoGenerateAsyncResponse(task_id=task.task_id)
