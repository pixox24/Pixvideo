from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.schemas.workbench import (
    AssetVersionResponse,
    BatchImageRequest,
    CreateProjectRequest,
    ExportRequest,
    GenerationJobResponse,
    GenerationRunCreateRequest,
    GenerationRunItemResponse,
    GenerationRunResponse,
    LatestExportResponse,
    ProjectResponse,
    ProjectSceneResponse,
    ProjectUpdateRequest,
    RegenerateImageRequest,
    ReorderScenesRequest,
    TimelineUpdateRequest,
    UpdateNarrationRequest,
    UpdateSceneRequest,
)
from api.tasks import task_manager
from api.tasks.models import TaskType
from pixelle_video.config import config_manager
from pixelle_video.models.workbench import (
    AssetSource,
    GenerationJob,
    GenerationKind,
    GenerationRunStatus,
    GenerationStatus,
    Project,
    Scene,
    effective_scene_duration,
)
from pixelle_video.services.project_generation_service import (
    ActiveGenerationRunError,
    ActiveSceneLockedError,
)
from pixelle_video.services.workbench_generation import (
    build_parameter_snapshot,
    compute_image_fingerprint,
    compute_narration_fingerprint,
)
from pixelle_video.utils.content_generators import generate_image_prompts
from pixelle_video.utils.os_util import get_data_path, get_root_path

router = APIRouter(prefix="/projects", tags=["Workbench Projects"])

_PROJECT_CONFIG_KEYS = {
    "title", "tabType", "workflowId", "workflow", "ttsMode", "tts_inference_mode",
    "ttsDelivery", "tts_delivery",
    "voice", "tts_voice", "speed", "tts_speed", "minimaxModel", "minimax_model",
    "emotion", "minimax_emotion", "mimoModel", "mimo_model", "mimoStyle", "mimo_style",
    "mediaWidth", "mediaHeight", "media_width", "media_height",
    "imageAspectRatio", "bgm", "bgm_path", "bgmVolume", "bgm_volume", "promptPrefix",
    "prompt_prefix", "enableMotion", "enableSubtitles", "subtitleStyle", "subtitle_enabled",
    "splitType", "frame_template", "template_params", "composition_mode", "image_motion_enabled",
    "image_motion_mode", "image_motion_strength", "image_fit_mode", "video_fps", "ttsWorkflow",
    "tts_workflow", "ref_audio", "scenes", "n_scenes", "mode", "split_mode",
}
_BGM_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}


def _validate_project_bgm(config: dict) -> None:
    """Allow only BGM references returned by the local resource APIs."""
    for key in ("bgm", "bgm_path"):
        raw_value = config.get(key)
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if value in {"", "none", "bgm-none"}:
            continue

        candidates: list[tuple[Path, str]] = []
        if value.startswith("custom-bgm/"):
            folder = str(config_manager.get("quick_create", {}).get("custom_bgm_folder") or "").strip()
            if folder:
                candidates.append((Path(folder).expanduser(), value.removeprefix("custom-bgm/")))
        elif value.startswith("data/bgm/"):
            candidates.append((Path(get_data_path("bgm")), value.removeprefix("data/bgm/")))
        elif value.startswith("bgm/"):
            candidates.append((Path(get_root_path("bgm")), value.removeprefix("bgm/")))
        elif Path(value).name == value:
            candidates.extend([
                (Path(get_data_path("bgm")), value),
                (Path(get_root_path("bgm")), value),
            ])

        for base, relative in candidates:
            if Path(relative).name != relative or Path(relative).suffix.lower() not in _BGM_EXTENSIONS:
                continue
            try:
                resolved_base = base.resolve()
                candidate = (resolved_base / relative).resolve()
                candidate.relative_to(resolved_base)
                if candidate.is_file():
                    break
            except (OSError, RuntimeError, ValueError):
                continue
        else:
            raise HTTPException(status_code=422, detail=f"unsupported BGM reference: {value}")


def _scene_or_404(core, project_id: str, scene_id: str):
    if core.workbench_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    scene = core.workbench_repository.get_scene(scene_id)
    if scene is None or scene.project_id != project_id:
        raise HTTPException(status_code=404, detail="scene not found")
    return scene


def _assert_scene_editable(core, project_id: str, scene_id: str) -> None:
    service = getattr(core, "project_generation", None)
    if service is None:
        return
    try:
        service.assert_scene_editable(project_id, scene_id)
    except ActiveSceneLockedError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "runId": exc.run_id}) from exc


async def _enqueue(core, project_id: str, scene_id: str | None, kind: GenerationKind,
                   task_type: TaskType, request_snapshot: dict, runner, *runner_args):
    task = task_manager.create_task(task_type, request_params=request_snapshot)
    job = GenerationJob(project_id, kind, task.task_id, request_snapshot, scene_id=scene_id)
    core.workbench_repository.create_generation_job(job)
    await task_manager.execute_task(task.task_id, runner, project_id, scene_id, task.task_id, *runner_args)
    return job


def _latest_export_response(project, repository, media, request: Request):
    revision = repository.get_latest_export_revision(project.project_id)
    if revision is None:
        return None, True
    output_url = None
    if revision.output_relative_path:
        try:
            output_path = media.resolve(project.project_id, revision.output_relative_path)
            if output_path.is_file():
                output_url = media.to_api_url(project.project_id, revision.output_relative_path, request)
        except (OSError, ValueError):
            output_url = None
    completed = repository.get_latest_completed_export_revision(project.project_id)
    return LatestExportResponse(
        exportId=revision.export_id,
        purpose=revision.snapshot.get("purpose"),
        status=revision.status.value,
        outputUrl=output_url,
        createdAt=revision.created_at.isoformat(),
        updatedAt=revision.updated_at.isoformat(),
    ), completed is None or project.updated_at > completed.updated_at


def _response(project, scenes, repository, media, request: Request, runtime_config=None) -> ProjectResponse:
    scene_responses = []
    parameter_snapshot = build_parameter_snapshot(
        project,
        runtime_config=runtime_config or {},
    )
    for scene in scenes:
        versions = repository.list_asset_versions(project.project_id, scene.scene_id)
        version_responses = [
            AssetVersionResponse(
                versionId=version.version_id,
                source=version.source.value,
                imageUrl=media.to_api_url(project.project_id, version.relative_path, request),
                thumbnailUrl=(media.to_api_url(project.project_id, version.thumbnail_relative_path, request)
                              if version.thumbnail_relative_path else None),
                promptSnapshot=version.prompt_snapshot,
                createdAt=version.created_at.isoformat(),
            )
            for version in versions
        ]
        audio_url = (media.to_api_url(project.project_id, scene.audio_relative_path, request)
                     if scene.audio_relative_path else None)
        current = repository.get_asset_version(scene.current_version_id) if scene.current_version_id else None
        expected_image_fingerprint = compute_image_fingerprint(
            scene.visual_prompt,
            parameter_snapshot,
        )
        expected_audio_fingerprint = compute_narration_fingerprint(
            scene.narration,
            parameter_snapshot,
        )
        image_state = "missing"
        if current:
            try:
                image_exists = media.resolve(project.project_id, current.relative_path).is_file()
            except (OSError, ValueError):
                image_exists = False
            image_state = "ready" if image_exists else "missing"
            stored_image_fingerprint = (
                current.parameters.get("imageFingerprint")
                or current.parameters.get("image_fingerprint")
                or scene.image_fingerprint
            )
            if image_exists and not (
                stored_image_fingerprint == expected_image_fingerprint
                or (current.source.value == "upload" and stored_image_fingerprint is None)
            ):
                image_state = "stale"
        audio_state = "missing"
        if scene.audio_relative_path:
            try:
                audio_exists = media.resolve(project.project_id, scene.audio_relative_path).is_file()
            except (OSError, ValueError):
                audio_exists = False
            if audio_exists:
                audio_state = (
                    "ready"
                    if scene.audio_fingerprint == expected_audio_fingerprint
                    else "stale"
                )
        candidate_count = max(0, len(versions) - (1 if scene.current_version_id else 0))
        scene_responses.append(ProjectSceneResponse(
            sceneId=scene.scene_id, position=scene.position, narration=scene.narration,
            visualPrompt=scene.visual_prompt, currentVersionId=scene.current_version_id,
            audioUrl=audio_url, durationSeconds=scene.duration_seconds,
            manualHoldSeconds=scene.manual_hold_seconds, status=scene.status,
            versions=version_responses,
            generationState={"image": image_state, "audio": audio_state, "candidateCount": candidate_count},
        ))
    jobs = [GenerationJobResponse(jobId=job.job_id, taskId=job.task_id, sceneId=job.scene_id,
                                  kind=job.kind.value, status=job.status.value, progress=job.progress,
                                  error=job.error)
            for job in repository.list_generation_jobs(project.project_id)]
    latest_export, dirty = _latest_export_response(project, repository, media, request)
    return ProjectResponse(
        projectId=project.project_id, title=project.title, source=project.source,
        sourceHistoryTaskId=project.source_history_task_id, config=project.config,
        scenes=scene_responses, jobs=jobs, updatedAt=project.updated_at.isoformat(),
        latestExport=latest_export, dirty=dirty,
    )


def _run_response(core, run_id: str) -> GenerationRunResponse:
    run = core.workbench_repository.get_generation_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="generation run not found")
    items = core.workbench_repository.list_generation_run_items(run_id)
    return GenerationRunResponse(
        runId=run.run_id, projectId=run.project_id, taskId=run.task_id, status=run.status.value,
        currentSceneId=run.current_scene_id, totalCount=run.total_count,
        completedCount=run.completed_count, skippedCount=run.skipped_count,
        failedCount=run.failed_count, candidateReviewCount=run.candidate_review_count,
        pauseRequested=run.pause_requested, cancelRequested=run.cancel_requested,
        error=run.error, createdAt=run.created_at.isoformat(), updatedAt=run.updated_at.isoformat(),
        allowedActions=_allowed_generation_actions(run),
        items=[GenerationRunItemResponse(
            itemId=item.item_id, sceneId=item.scene_id, position=item.position,
            status=item.status.value,
            phase=("tts" if item.status.value == "running_tts" else "image" if item.status.value == "running_image" else "idle"),
            ttsStatus=item.tts_status.value, imageStatus=item.image_status.value,
            skipReason=item.skip_reason, candidateVersionId=item.candidate_version_id,
            error=item.error, updatedAt=item.updated_at.isoformat(),
        ) for item in items],
    )


def _allowed_generation_actions(run) -> list[str]:
    if run.cancel_requested:
        return []
    # A run with failed items is terminal for polling, but is still actionable:
    # the UI must be able to offer a focused retry instead of starting over.
    if run.status == GenerationRunStatus.COMPLETED_WITH_FAILURES:
        return ["retry-failed"]
    if run.is_terminal:
        return []
    if run.status in {GenerationRunStatus.QUEUED, GenerationRunStatus.RUNNING}:
        return ["cancel"] if run.pause_requested else ["pause", "cancel"]
    if run.status == GenerationRunStatus.PAUSED:
        return ["resume", "cancel"]
    return []


async def _autofill_image_prompts(core, scenes: list[Scene]) -> None:
    """Fill empty visual prompts with LLM-generated prompts, falling back to narration."""
    missing = [scene for scene in scenes if not scene.visual_prompt.strip()]
    if not missing:
        return
    llm = getattr(core, "llm", None)
    try:
        if llm is not None:
            from pixelle_video.config import config_manager

            llm_config = config_manager.get_llm_config()
            if llm_config.get("api_key") and llm_config.get("base_url") and llm_config.get("model"):
                prompts = await generate_image_prompts(
                    llm,
                    [scene.narration for scene in missing],
                    min_words=20,
                    max_words=80,
                )
                for scene, prompt in zip(missing, prompts):
                    if prompt and prompt.strip():
                        scene.visual_prompt = prompt.strip()
    except Exception as exc:
        logger.warning(f"Image prompt autofill failed, falling back to narration: {exc}")
    for scene in missing:
        if not scene.visual_prompt.strip():
            scene.visual_prompt = scene.narration


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(body: CreateProjectRequest, core: PixelleVideoDep, request: Request):
    _validate_project_bgm(body.config)
    project = Project(title=body.title, config=body.config, source=body.source)
    scenes = [Scene(project.project_id, position, item.narration, item.visual_prompt.strip())
              for position, item in enumerate(body.scenes)]
    await _autofill_image_prompts(core, scenes)
    core.workbench_repository.create_project(project, scenes)
    return _response(project, scenes, core.workbench_repository, core.workbench_media, request, getattr(core, "config", {}))


@router.get("/{project_id}/media/{relative_path:path}")
async def get_project_media(project_id: str, relative_path: str, core: PixelleVideoDep):
    """Serve project-local media (images, audio) with Range support for playback."""
    if not relative_path:
        raise HTTPException(status_code=404, detail="media path not found")
    try:
        path = core.workbench_media.resolve(project_id, relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="media file not found")
    return FileResponse(path)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, core: PixelleVideoDep, request: Request):
    project = core.workbench_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    scenes = core.workbench_repository.list_project_scenes(project_id)
    return _response(project, scenes, core.workbench_repository, core.workbench_media, request, getattr(core, "config", {}))


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, body: ProjectUpdateRequest, core: PixelleVideoDep, request: Request):
    project = core.workbench_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    if body.expected_updated_at and body.expected_updated_at != project.updated_at.isoformat():
        raise HTTPException(status_code=409, detail="project changed since it was loaded")
    changes = {}
    if body.title is not None:
        changes["title"] = body.title
    if body.config is not None:
        unknown = sorted(set(body.config) - _PROJECT_CONFIG_KEYS)
        if unknown:
            raise HTTPException(status_code=422, detail={"message": "unsupported project config", "keys": unknown})
        _validate_project_bgm(body.config)
        # Preserve server-owned config keys while allowing editor-owned fields to change.
        merged_config = dict(project.config)
        merged_config.update(body.config)
        changes["config"] = merged_config
    if changes:
        core.workbench_repository.update_project(project_id, **changes)
    updated = core.workbench_repository.get_project(project_id)
    scenes = core.workbench_repository.list_project_scenes(project_id)
    return _response(updated, scenes, core.workbench_repository, core.workbench_media, request, getattr(core, "config", {}))


@router.post("/{project_id}/generation-runs", response_model=GenerationRunResponse, status_code=202)
async def start_generation_run(project_id: str, body: GenerationRunCreateRequest, core: PixelleVideoDep):
    if core.workbench_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    try:
        run = await core.project_generation.start(project_id, body.config_override, body.scene_ids)
    except ActiveGenerationRunError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "currentRunId": exc.run.run_id}) from exc
    return _run_response(core, run.run_id)


@router.get("/{project_id}/generation-runs/active", response_model=GenerationRunResponse | None)
async def get_active_generation_run(project_id: str, core: PixelleVideoDep):
    if core.workbench_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    run = core.workbench_repository.get_active_generation_run(project_id)
    return _run_response(core, run.run_id) if run else None


@router.get("/{project_id}/generation-runs/{run_id}", response_model=GenerationRunResponse)
async def get_generation_run(project_id: str, run_id: str, core: PixelleVideoDep):
    run = core.workbench_repository.get_generation_run(run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="generation run not found")
    return _run_response(core, run_id)


async def _generation_action(project_id: str, run_id: str, core, action: str):
    run = core.workbench_repository.get_generation_run(run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="generation run not found")
    try:
        result = await getattr(core.project_generation, f"request_{action}")(run_id)
    except ValueError as exc:
        current = core.workbench_repository.get_generation_run(run_id)
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "allowedActions": _allowed_generation_actions(current) if current else [],
            },
        ) from exc
    return _run_response(core, result.run_id)


@router.post("/{project_id}/generation-runs/{run_id}/pause", response_model=GenerationRunResponse)
async def pause_generation_run(project_id: str, run_id: str, core: PixelleVideoDep):
    return await _generation_action(project_id, run_id, core, "pause")


@router.post("/{project_id}/generation-runs/{run_id}/resume", response_model=GenerationRunResponse)
async def resume_generation_run(project_id: str, run_id: str, core: PixelleVideoDep):
    return await _generation_action(project_id, run_id, core, "resume")


@router.post("/{project_id}/generation-runs/{run_id}/cancel", response_model=GenerationRunResponse)
async def cancel_generation_run(project_id: str, run_id: str, core: PixelleVideoDep):
    return await _generation_action(project_id, run_id, core, "cancel")


@router.post("/{project_id}/generation-runs/{run_id}/retry-failed", response_model=GenerationRunResponse, status_code=202)
async def retry_failed_generation(project_id: str, run_id: str, core: PixelleVideoDep):
    run = core.workbench_repository.get_generation_run(run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="generation run not found")
    try:
        retry = await core.project_generation.retry_failed(run_id)
    except (ValueError, ActiveGenerationRunError) as exc:
        detail = {"message": str(exc), "allowedActions": _allowed_generation_actions(run)}
        if isinstance(exc, ActiveGenerationRunError):
            detail["currentRunId"] = exc.run.run_id
        raise HTTPException(status_code=409, detail=detail) from exc
    return _run_response(core, retry.run_id)


@router.post("/from-history/{task_id}", response_model=ProjectResponse, status_code=201)
async def create_project_from_history(task_id: str, core: PixelleVideoDep, request: Request):
    existing = core.workbench_repository.get_project_by_source_history_task_id(task_id)
    if existing:
        scenes = core.workbench_repository.list_project_scenes(existing.project_id)
        return _response(existing, scenes, core.workbench_repository, core.workbench_media, request, getattr(core, "config", {}))
    detail = await core.history.get_task_detail(task_id)
    if not detail or not detail.get("storyboard"):
        raise HTTPException(status_code=404, detail="history task not found")
    storyboard = detail["storyboard"]
    metadata = detail.get("metadata") or {}
    project = Project(title=storyboard.title or metadata.get("title") or task_id,
                      config=dict(metadata.get("input") or {}), source="history",
                      source_history_task_id=task_id)
    _validate_project_bgm(project.config)
    frames = list(storyboard.frames or [])
    scenes = [Scene(project.project_id, index, frame.narration or "", frame.image_prompt or "",
                    duration_seconds=float(frame.duration or 0), status=frame.status or "completed")
              for index, frame in enumerate(frames)]
    if not scenes:
        raise HTTPException(status_code=422, detail="history task has no scenes")
    await _autofill_image_prompts(core, scenes)
    core.workbench_repository.create_project(project, scenes)
    from pixelle_video.models.workbench import AssetSource, AssetVersion
    for scene, frame in zip(scenes, frames):
        if frame.image_path and Path(frame.image_path).is_file():
            relative = core.workbench_media.copy_upload(project.project_id, scene.scene_id, Path(frame.image_path), Path(frame.image_path).name)
            version = AssetVersion(project.project_id, scene.scene_id, AssetSource.UPLOAD, relative, prompt_snapshot=frame.image_prompt)
            core.workbench_repository.create_asset_version(version)
            core.workbench_repository.select_asset_version(project.project_id, scene.scene_id, version.version_id)
        if frame.audio_path and Path(frame.audio_path).is_file():
            audio_relative = f"assets/scenes/{scene.scene_id}/audio/legacy{Path(frame.audio_path).suffix or '.mp3'}"
            audio_destination = core.workbench_media.resolve(project.project_id, audio_relative)
            audio_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(frame.audio_path, audio_destination)
            core.workbench_repository.update_scene(scene.scene_id, audio_relative_path=audio_relative)
    return _response(project, core.workbench_repository.list_project_scenes(project.project_id), core.workbench_repository, core.workbench_media, request, getattr(core, "config", {}))


@router.post("/{project_id}/scenes/{scene_id}/generate", response_model=GenerationJobResponse, status_code=202)
async def generate_scene(project_id: str, scene_id: str, core: PixelleVideoDep):
    scene = _scene_or_404(core, project_id, scene_id)
    _assert_scene_editable(core, project_id, scene_id)
    job = await _enqueue(core, project_id, scene_id, GenerationKind.SCENE, TaskType.WORKBENCH_SCENE,
                         {"narration": scene.narration, "prompt": scene.visual_prompt},
                         core.workbench_jobs.run_scene_job)
    return GenerationJobResponse(jobId=job.job_id, taskId=job.task_id, sceneId=scene_id,
                                 kind=job.kind.value, status=job.status.value, progress=job.progress)


@router.post("/{project_id}/scenes/{scene_id}/image-generations", response_model=GenerationJobResponse, status_code=202)
async def regenerate_image(project_id: str, scene_id: str, body: RegenerateImageRequest, core: PixelleVideoDep):
    _scene_or_404(core, project_id, scene_id)
    _assert_scene_editable(core, project_id, scene_id)
    job = await _enqueue(core, project_id, scene_id, GenerationKind.IMAGE, TaskType.WORKBENCH_IMAGE,
                         {"prompt": body.prompt}, core.workbench_jobs.run_image_job, body.prompt)
    return GenerationJobResponse(jobId=job.job_id, taskId=job.task_id, sceneId=scene_id,
                                 kind=job.kind.value, status=job.status.value, progress=job.progress)


@router.post("/{project_id}/scenes/{scene_id}/tts", response_model=GenerationJobResponse, status_code=202)
async def regenerate_tts(project_id: str, scene_id: str, body: UpdateNarrationRequest, core: PixelleVideoDep):
    _scene_or_404(core, project_id, scene_id)
    _assert_scene_editable(core, project_id, scene_id)
    job = await _enqueue(core, project_id, scene_id, GenerationKind.TTS, TaskType.WORKBENCH_TTS,
                         {"narration": body.narration}, core.workbench_jobs.run_tts_job, body.narration)
    return GenerationJobResponse(jobId=job.job_id, taskId=job.task_id, sceneId=scene_id,
                                 kind=job.kind.value, status=job.status.value, progress=job.progress)


@router.patch("/{project_id}/scenes/{scene_id}")
async def update_scene(project_id: str, scene_id: str, body: UpdateSceneRequest, core: PixelleVideoDep):
    scene = _scene_or_404(core, project_id, scene_id)
    _assert_scene_editable(core, project_id, scene_id)
    changes = body.model_dump(exclude_none=True, by_alias=False)
    if "duration_seconds" in changes and changes["duration_seconds"] < scene.duration_seconds:
        raise HTTPException(status_code=422, detail="duration cannot be shorter than audio duration")
    if "manual_hold_seconds" in changes:
        audio_duration = max(0.0, scene.duration_seconds - scene.manual_hold_seconds)
        changes["duration_seconds"] = effective_scene_duration(
            audio_duration, changes["manual_hold_seconds"]
        )
    if not changes:
        return {"sceneId": scene_id}
    core.workbench_repository.update_scene(scene_id, **changes)
    updated = core.workbench_repository.get_scene(scene_id)
    return {"sceneId": scene_id, "narration": updated.narration, "visualPrompt": updated.visual_prompt,
            "durationSeconds": updated.duration_seconds, "manualHoldSeconds": updated.manual_hold_seconds}


@router.post("/{project_id}/scenes/{scene_id}/versions/{version_id}/select")
async def select_asset_version(project_id: str, scene_id: str, version_id: str, core: PixelleVideoDep):
    _scene_or_404(core, project_id, scene_id)
    _assert_scene_editable(core, project_id, scene_id)
    if core.workbench_repository.get_asset_version(version_id) is None:
        raise HTTPException(status_code=404, detail="version not found")
    try:
        core.workbench_repository.select_asset_version(project_id, scene_id, version_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="version not found") from exc
    return {"sceneId": scene_id, "currentVersionId": version_id}


@router.post("/{project_id}/scenes/reorder")
async def reorder_scenes(project_id: str, body: ReorderScenesRequest, core: PixelleVideoDep):
    if core.workbench_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    scenes = core.workbench_repository.list_project_scenes(project_id)
    expected = {scene.scene_id for scene in scenes}
    if len(body.scene_ids) != len(set(body.scene_ids)) or set(body.scene_ids) != expected:
        raise HTTPException(status_code=422, detail="sceneIds must contain every project scene exactly once")
    core.workbench_repository.reorder_scenes(project_id, body.scene_ids)
    return {"sceneIds": body.scene_ids}


@router.patch("/{project_id}/timeline")
async def update_timeline(project_id: str, body: TimelineUpdateRequest, core: PixelleVideoDep):
    if core.workbench_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    scenes = core.workbench_repository.list_project_scenes(project_id)
    expected = {scene.scene_id for scene in scenes}
    if len(body.scene_ids) != len(set(body.scene_ids)) or set(body.scene_ids) != expected:
        raise HTTPException(status_code=422, detail="sceneIds must contain every project scene exactly once")
    if not set(body.holds).issubset(expected):
        raise HTTPException(status_code=422, detail="holds contains an unknown scene")
    core.workbench_repository.reorder_scenes(project_id, body.scene_ids)
    for scene_id, hold in body.holds.items():
        scene = core.workbench_repository.get_scene(scene_id)
        audio_duration = max(0.0, scene.duration_seconds - scene.manual_hold_seconds) if scene else 0.0
        core.workbench_repository.update_scene(
            scene_id,
            manual_hold_seconds=hold,
            duration_seconds=effective_scene_duration(audio_duration, hold),
        )
    return {"sceneIds": body.scene_ids, "scenes": [scene.__dict__ for scene in core.workbench_repository.list_project_scenes(project_id)]}


@router.post("/{project_id}/batch/image-generations", status_code=202)
async def batch_image_generations(project_id: str, body: BatchImageRequest, core: PixelleVideoDep):
    if core.workbench_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    scenes = {scene.scene_id: scene for scene in core.workbench_repository.list_project_scenes(project_id)}
    if any(scene_id not in scenes for scene_id in body.scene_ids):
        raise HTTPException(status_code=404, detail="scene not found")
    for scene_id in body.scene_ids:
        _assert_scene_editable(core, project_id, scene_id)
    jobs = []
    for scene_id in body.scene_ids:
        scene = scenes[scene_id]
        prompt = " ".join(part for part in (body.prompt_prefix.strip(), scene.visual_prompt.strip()) if part)
        job = await _enqueue(core, project_id, scene_id, GenerationKind.IMAGE, TaskType.WORKBENCH_IMAGE,
                             {"prompt": prompt, "promptPrefix": body.prompt_prefix},
                             core.workbench_jobs.run_image_job_limited, prompt)
        jobs.append({"jobId": job.job_id, "taskId": job.task_id, "sceneId": scene_id,
                     "kind": job.kind.value, "status": job.status.value, "progress": job.progress})
    return {"jobs": jobs}


@router.post("/{project_id}/exports", status_code=202)
async def create_export(project_id: str, core: PixelleVideoDep, body: ExportRequest = ExportRequest()):
    project = core.workbench_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    _validate_project_bgm(project.config)
    scenes = core.workbench_repository.list_project_scenes(project_id)
    snapshot_scenes = []
    blocking = []
    candidate_warnings = []
    for scene in scenes:
        versions = core.workbench_repository.list_asset_versions(project_id, scene.scene_id)
        version = (core.workbench_repository.get_asset_version(scene.current_version_id)
                   if scene.current_version_id else None)
        if any(item.source == AssetSource.AI and item.version_id != scene.current_version_id for item in versions):
            candidate_warnings.append(scene.scene_id)
        audio_path = scene.audio_relative_path
        if version is None or not audio_path:
            blocking.append(scene.scene_id)
            continue
        snapshot_scenes.append({
            "sceneId": scene.scene_id, "position": scene.position,
            "narration": scene.narration, "visualPrompt": scene.visual_prompt,
            "durationSeconds": scene.duration_seconds, "manualHoldSeconds": scene.manual_hold_seconds,
            "versionId": version.version_id if version else None,
            "imagePath": version.relative_path if version else None,
            "audioPath": audio_path,
        })
    if blocking and not body.allow_incomplete:
        raise HTTPException(status_code=409, detail={"blockingScenes": blocking, "message": "project is incomplete"})
    if not snapshot_scenes:
        raise HTTPException(status_code=409, detail={"blockingScenes": blocking, "message": "project has no complete scenes"})
    from api.tasks import task_manager
    from api.tasks.models import TaskType
    from pixelle_video.models.workbench import ExportRevision
    task = task_manager.create_task(TaskType.WORKBENCH_EXPORT, request_params={"project_id": project_id, "allowIncomplete": body.allow_incomplete})
    revision = ExportRevision(project_id, {
        "projectId": project_id,
        "purpose": "manual",
        "sceneOrder": [scene["sceneId"] for scene in snapshot_scenes],
        "scenes": snapshot_scenes,
        "config": project.config,
        "allowIncomplete": body.allow_incomplete,
        "createdFromRunId": None,
    })
    core.workbench_repository.create_export_revision(revision)
    if core.workbench_jobs and hasattr(core.workbench_jobs, "run_export_job"):
        await task_manager.execute_task(task.task_id, core.workbench_jobs.run_export_job, project_id, revision.export_id, task.task_id)
    return {
        "exportId": revision.export_id,
        "jobId": task.task_id,
        "taskId": task.task_id,
        "status": revision.status.value,
        "blockingScenes": blocking,
        "candidateWarnings": candidate_warnings,
    }


@router.post("/{project_id}/exports/{export_id}/retry", status_code=202)
async def retry_export(project_id: str, export_id: str, core: PixelleVideoDep):
    if core.workbench_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    revision = core.workbench_repository.get_export_revision(export_id)
    if revision is None or revision.project_id != project_id:
        raise HTTPException(status_code=404, detail="export revision not found")
    if revision.status not in {GenerationStatus.FAILED, GenerationStatus.CANCELLED}:
        raise HTTPException(status_code=409, detail="only failed exports can be retried")
    if not core.workbench_jobs or not hasattr(core.workbench_jobs, "run_export_job"):
        raise HTTPException(status_code=503, detail="video pipeline is unavailable")
    core.workbench_repository.update_export_revision(
        export_id,
        status=GenerationStatus.PENDING,
        error=None,
    )
    from api.tasks import task_manager
    from api.tasks.models import TaskType
    task = task_manager.create_task(
        TaskType.WORKBENCH_EXPORT,
        request_params={"project_id": project_id, "export_id": export_id, "retry": True},
    )
    await task_manager.execute_task(
        task.task_id,
        core.workbench_jobs.run_export_job,
        project_id,
        export_id,
        task.task_id,
    )
    return {
        "exportId": export_id,
        "jobId": task.task_id,
        "taskId": task.task_id,
        "status": GenerationStatus.PENDING.value,
    }


@router.post("/{project_id}/scenes/{scene_id}/uploads", status_code=201)
async def upload_scene_asset(project_id: str, scene_id: str, core: PixelleVideoDep, file: UploadFile = File(...)):
    _scene_or_404(core, project_id, scene_id)
    _assert_scene_editable(core, project_id, scene_id)
    extension = Path(file.filename or "").suffix.lower()
    if file.content_type not in {"image/png", "image/jpeg", "image/webp", "image/gif"} or extension not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        raise HTTPException(status_code=415, detail="only image uploads are supported")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as handle:
            temporary = Path(handle.name)
            while chunk := await file.read(1024 * 1024):
                handle.write(chunk)
        relative = core.workbench_media.copy_upload(project_id, scene_id, temporary, file.filename or "upload.png")
        from pixelle_video.models.workbench import AssetSource, AssetVersion
        version = AssetVersion(project_id, scene_id, AssetSource.UPLOAD, relative)
        core.workbench_repository.create_asset_version(version)
        return {"versionId": version.version_id, "imageUrl": core.workbench_media.to_api_url(project_id, relative, None)}
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
        await file.close()
