"""Async API endpoints for specialist generation workflows."""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.dependencies import PixelleVideoDep
from api.routers.uploads import resolve_uploaded_file_keys
from api.routers.video import path_to_url
from api.schemas.specialist import ActionTransferGenerateRequest, CustomMediaGenerateRequest, DigitalHumanGenerateRequest, ImageToVideoGenerateRequest
from api.schemas.uploads import UploadPurpose
from api.schemas.video import VideoGenerateAsyncResponse
from api.tasks import TaskType, task_manager
from pixelle_video.pipelines.asset_based import AssetBasedPipeline
from pixelle_video.services.specialist_video import execute_digital_human_video, execute_video_workflow, persist_specialist_video

router = APIRouter(prefix="/specialist", tags=["Specialist Generation"])


def _update_task_progress(task_id: str, event) -> None:
    current = int(event.progress * 100)
    message = event.event_type
    if event.extra_info:
        message = f"{message} - {event.extra_info}"
    task_manager.update_progress(
        task_id,
        current,
        100,
        message,
        event_type=event.event_type,
        frame_current=event.frame_current,
        frame_total=event.frame_total,
        step=event.step,
        action=event.action,
        extra_info=event.extra_info,
    )


@router.post("/custom-media/generate/async", response_model=VideoGenerateAsyncResponse)
async def generate_custom_media_async(
    body: CustomMediaGenerateRequest,
    pixelle_video: PixelleVideoDep,
    request: Request,
) -> VideoGenerateAsyncResponse:
    """Generate an asset-based video from server-owned uploaded media."""
    asset_paths = resolve_uploaded_file_keys(body.asset_file_keys, UploadPurpose.CUSTOM_MEDIA)
    task = task_manager.create_task(
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"pipeline": "asset_based", **body.model_dump()},
    )

    async def execute_custom_media():
        pipeline = AssetBasedPipeline(pixelle_video)
        context = await pipeline(
            assets=asset_paths,
            video_title=body.title,
            intent=body.intent,
            duration=body.duration,
            source=body.source,
            bgm_path=body.bgm_path,
            bgm_volume=body.bgm_volume,
            bgm_mode=body.bgm_mode,
            voice_id=body.voice_id,
            tts_speed=body.tts_speed,
            task_id=task.task_id,
            progress_callback=lambda event: _update_task_progress(task.task_id, event),
        )
        return {
            "video_url": path_to_url(request, context.final_video_path),
            "duration": context.storyboard.total_duration if context.storyboard else 0,
        }

    await task_manager.execute_task(task.task_id, execute_custom_media)
    return VideoGenerateAsyncResponse(task_id=task.task_id)


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


@router.post("/action-transfer/generate/async", response_model=VideoGenerateAsyncResponse)
async def generate_action_transfer_async(
    body: ActionTransferGenerateRequest,
    pixelle_video: PixelleVideoDep,
    request: Request,
) -> VideoGenerateAsyncResponse:
    """Transfer motion from an uploaded video to an uploaded subject image."""
    video_path = resolve_uploaded_file_keys([body.video_file_key], UploadPurpose.ACTION_TRANSFER_VIDEO)[0]
    image_path = resolve_uploaded_file_keys([body.image_file_key], UploadPurpose.ACTION_TRANSFER_IMAGE)[0]
    task = task_manager.create_task(
        task_type=TaskType.VIDEO_GENERATION,
        request_params={"pipeline": "action_transfer", **body.model_dump()},
    )

    async def execute_action_transfer():
        try:
            task_manager.update_progress(task.task_id, 5, 100, "Preparing action-transfer workflow")
            final_video_path = await execute_video_workflow(
                pixelle_video,
                body.workflow_key,
                {"video": video_path, "image": image_path, "prompt": body.prompt, "second": body.duration},
                task.task_id,
            )
            task_manager.update_progress(task.task_id, 90, 100, "Saving generated video")
            await persist_specialist_video(
                pixelle_video,
                task.task_id,
                "action_transfer",
                body.model_dump(),
                final_video_path,
            )
            task_manager.update_progress(task.task_id, 100, 100, "Completed")
            return {"video_url": path_to_url(request, final_video_path)}
        except Exception as error:
            await persist_specialist_video(
                pixelle_video,
                task.task_id,
                "action_transfer",
                body.model_dump(),
                error=str(error),
            )
            raise

    await task_manager.execute_task(task.task_id, execute_action_transfer)
    return VideoGenerateAsyncResponse(task_id=task.task_id)


@router.post("/digital-human/generate/async", response_model=VideoGenerateAsyncResponse)
async def generate_digital_human_async(
    body: DigitalHumanGenerateRequest,
    pixelle_video: PixelleVideoDep,
    request: Request,
) -> VideoGenerateAsyncResponse:
    """Generate a digital-human video from validated uploaded assets."""
    character_path = resolve_uploaded_file_keys([body.character_file_key], UploadPurpose.DIGITAL_HUMAN_CHARACTER)[0]
    product_path = None
    if body.product_file_key:
        product_path = resolve_uploaded_file_keys([body.product_file_key], UploadPurpose.DIGITAL_HUMAN_PRODUCT)[0]
    task = task_manager.create_task(task_type=TaskType.VIDEO_GENERATION, request_params={"pipeline": "digital_human", **body.model_dump()})

    async def execute_digital_human():
        try:
            task_manager.update_progress(task.task_id, 5, 100, "Preparing digital-human workflow")
            final_video_path = await execute_digital_human_video(
                pixelle_video, task.task_id, body.mode, character_path, body.script, product_path,
                body.product_title, body.tts_inference_mode, body.voice, body.speed,
            )
            await persist_specialist_video(pixelle_video, task.task_id, "digital_human", body.model_dump(), final_video_path)
            task_manager.update_progress(task.task_id, 100, 100, "Completed")
            return {"video_url": path_to_url(request, final_video_path)}
        except Exception as error:
            await persist_specialist_video(pixelle_video, task.task_id, "digital_human", body.model_dump(), error=str(error))
            raise

    await task_manager.execute_task(task.task_id, execute_digital_human)
    return VideoGenerateAsyncResponse(task_id=task.task_id)
