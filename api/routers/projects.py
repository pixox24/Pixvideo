from __future__ import annotations

import shutil
import tempfile
from types import SimpleNamespace
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
    PipelineProgressResponse,
    PipelineSceneCellResponse,
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
    AssetVersion,
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
from pixelle_video.utils.content_generators import (
    generate_image_prompts,
    segment_narration_semantically,
)
from pixelle_video.utils.os_util import get_data_path, get_root_path
from pixelle_video.utils.prompt_helper import is_visual_prompt_same_as_narration
from pixelle_video.utils.project_config import normalize_project_config

router = APIRouter(prefix="/projects", tags=["Workbench Projects"])

_PROJECT_CONFIG_KEYS = {
    "title", "tabType", "workflowId", "workflow", "ttsMode", "tts_inference_mode",
    "ttsDelivery", "tts_delivery",
    "voice", "tts_voice", "speed", "tts_speed", "minimaxModel", "minimax_model",
    "emotion", "minimax_emotion", "mimoModel", "mimo_model", "mimoStyle", "mimo_style",
    "qwenAudioModel", "qwen_audio_model", "qwenAudioMode", "qwen_audio_mode",
    "qwenAudioInstruction", "qwen_audio_instruction", "qwenAudioRefAudio", "qwen_audio_ref_audio",
    "mediaWidth", "mediaHeight", "media_width", "media_height",
    "videoFps", "video_fps",
    # imageGenWidth/Height removed: gen size always maps from media canvas whitelist
    "imageAspectRatio", "bgm", "bgm_path", "bgmVolume", "bgm_volume", "promptPrefix",
    "prompt_prefix", "enableMotion", "enableSubtitles", "subtitleStyle", "subtitle_enabled",
    "bookendEnabled", "bookend_enabled", "bookendIntroSeconds", "bookendOutroSeconds",
    "bookendIntroFadeSeconds", "bookendOutroFadeSeconds", "bookend",
    "intro_seconds", "outro_seconds", "intro_fade_seconds", "outro_fade_seconds",
    "splitType", "frame_template", "template_params", "composition_mode", "image_motion_enabled",
    "image_motion_mode", "image_motion_strength", "image_fit_mode", "video_fps", "ttsWorkflow",
    "tts_workflow", "ref_audio", "scenes", "n_scenes", "mode", "split_mode",
    "useApiImage", "use_api_image", "directorMode", "director_mode", "density", "storyboard_density",
    "targetSceneCount", "target_scene_count",
    "styleSlotId", "style_slot_id", "stylePrefixSnapshot", "style_prefix_snapshot", "styleStrength", "style_strength",
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


def _assert_scene_not_locked(core, project_id: str, scene_id: str) -> None:
    """Reject asset/content operations that would overwrite a user-locked scene."""
    scene = _scene_or_404(core, project_id, scene_id)
    if scene.locked:
        raise HTTPException(
            status_code=409,
            detail={"message": "该分镜已锁定，请先解锁后再修改或重新生成", "sceneId": scene_id},
        )


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
    progress = None
    if isinstance(revision.snapshot, dict):
        raw = revision.snapshot.get("progress")
        if isinstance(raw, dict):
            progress = raw
    task_id = None
    if isinstance(revision.snapshot, dict):
        raw_task = revision.snapshot.get("taskId") or revision.snapshot.get("task_id")
        if raw_task:
            task_id = str(raw_task)
    return LatestExportResponse(
        exportId=revision.export_id,
        purpose=revision.snapshot.get("purpose"),
        status=revision.status.value,
        outputUrl=output_url,
        createdAt=revision.created_at.isoformat(),
        updatedAt=revision.updated_at.isoformat(),
        progress=progress,
        taskId=task_id,
    ), completed is None or project.updated_at > completed.updated_at


def _map_tts_cell(item_status: str | None, tts_status: str | None, audio_state: str | None) -> str:
    status = (tts_status or item_status or "").lower()
    if status in {"failed"}:
        return "failed"
    if status in {"running", "running_tts"}:
        return "running"
    if status in {"skipped"}:
        return "skipped"
    if status in {"completed", "ready"} or audio_state == "ready":
        return "ready"
    if status in {"queued", "pending"}:
        return "queued"
    if audio_state == "stale":
        return "stale"
    if audio_state == "missing":
        return "missing"
    return "queued" if status else "idle"


def _map_image_cell(item_status: str | None, image_status: str | None, image_state: str | None, candidate: int) -> str:
    status = (image_status or item_status or "").lower()
    if status in {"failed"}:
        return "failed"
    if status in {"candidate_review"} or candidate > 0 and status not in {"completed", "ready"}:
        if status in {"running", "running_image"}:
            return "running"
        if candidate > 0 and status in {"completed", "candidate_review"}:
            return "candidate"
    if status in {"running", "running_image"}:
        return "running"
    if status in {"skipped"}:
        return "skipped"
    if status in {"completed", "ready"} or image_state == "ready":
        return "ready"
    if status in {"candidate_review"}:
        return "candidate"
    if status in {"queued", "pending"}:
        return "queued"
    if image_state == "stale":
        return "stale"
    if image_state == "missing":
        return "missing"
    return "queued" if status else "idle"


def _build_pipeline_progress(project, scenes, scene_responses, repository) -> PipelineProgressResponse:
    """Assemble observatory payload: assets run + export segment progress."""
    run = repository.get_active_generation_run(project.project_id)
    if run is None:
        # Prefer latest non-terminal-looking recent run if just finished
        runs = repository.list_generation_runs(project.project_id, limit=1)
        run = runs[0] if runs else None

    run_items = repository.list_generation_run_items(run.run_id) if run else []
    items_by_scene = {item.scene_id: item for item in run_items}
    export_revision = repository.get_latest_export_revision(project.project_id)
    export_progress = {}
    if export_revision and isinstance(export_revision.snapshot, dict):
        raw = export_revision.snapshot.get("progress")
        if isinstance(raw, dict):
            export_progress = raw
    segment_by_scene = {}
    for row in export_progress.get("segments") or []:
        if isinstance(row, dict) and row.get("sceneId"):
            segment_by_scene[str(row["sceneId"])] = str(row.get("status") or "queued")

    cells: list[PipelineSceneCellResponse] = []
    for scene, scene_resp in zip(scenes, scene_responses):
        item = items_by_scene.get(scene.scene_id)
        gen = scene_resp.generation_state or {}
        item_status = item.status.value if item and hasattr(item.status, "value") else (str(item.status) if item else None)
        tts_status = item.tts_status.value if item and hasattr(item.tts_status, "value") else (str(item.tts_status) if item else None)
        image_status = item.image_status.value if item and hasattr(item.image_status, "value") else (str(item.image_status) if item else None)
        tts = _map_tts_cell(item_status, tts_status, gen.get("audio"))
        image = _map_image_cell(
            item_status,
            image_status,
            gen.get("image"),
            int(gen.get("candidateCount") or 0),
        )
        # Segment only meaningful during/after export
        if export_revision and export_revision.status in {
            GenerationStatus.PENDING,
            GenerationStatus.RUNNING,
            GenerationStatus.COMPLETED,
            GenerationStatus.FAILED,
        }:
            if export_revision.status == GenerationStatus.COMPLETED:
                segment = "ready"
            else:
                segment = segment_by_scene.get(scene.scene_id, "idle")
                if segment == "queued" and export_progress.get("stage") in {None, "prepare"}:
                    segment = "queued"
        else:
            segment = "idle"
        cells.append(
            PipelineSceneCellResponse(
                sceneId=scene.scene_id,
                position=scene.position,
                narration=(scene.narration or "")[:48],
                tts=tts,
                image=image,
                segment=segment,
            )
        )

    run_terminal = bool(run and run.status in {
        GenerationRunStatus.COMPLETED,
        GenerationRunStatus.COMPLETED_WITH_FAILURES,
        GenerationRunStatus.CANCELLED,
        GenerationRunStatus.FAILED,
    })
    export_active = bool(
        export_revision
        and export_revision.status in {GenerationStatus.PENDING, GenerationStatus.RUNNING}
    )
    export_done = bool(export_revision and export_revision.status == GenerationStatus.COMPLETED)
    export_failed = bool(export_revision and export_revision.status == GenerationStatus.FAILED)

    assets_payload = None
    focus = None
    updated_at = None
    if run:
        assets_payload = {
            "runId": run.run_id,
            "status": run.status.value,
            "completed": run.completed_count,
            "total": run.total_count,
            "failed": run.failed_count,
            "currentSceneId": run.current_scene_id,
        }
        updated_at = run.updated_at.isoformat()
        if not run_terminal:
            current = next((c for c in cells if c.scene_id == run.current_scene_id), None)
            cell = "tts"
            if current:
                if current.tts == "running":
                    cell = "tts"
                elif current.image == "running":
                    cell = "image"
                else:
                    cell = "image" if current.tts == "ready" else "tts"
            focus = {
                "phase": "assets",
                "sceneId": run.current_scene_id,
                "sceneIndex": (current.position + 1) if current else None,
                "sceneTotal": run.total_count,
                "cell": cell,
            }

    export_payload = None
    if export_revision:
        stage = export_progress.get("stage") or (
            "done" if export_done else "failed" if export_failed else "prepare"
        )
        export_payload = {
            "exportId": export_revision.export_id,
            "status": export_revision.status.value,
            "purpose": export_revision.snapshot.get("purpose") if isinstance(export_revision.snapshot, dict) else None,
            "stage": stage,
            "segmentCurrent": export_progress.get("segmentCurrent") or 0,
            "segmentTotal": export_progress.get("segmentTotal") or len(cells),
            "segments": export_progress.get("segments") or [],
            "error": export_revision.error or export_progress.get("error"),
            "updatedAt": export_progress.get("updatedAt") or export_revision.updated_at.isoformat(),
        }
        updated_at = export_payload["updatedAt"] or updated_at
        if export_active:
            seg_cur = int(export_payload["segmentCurrent"] or 0)
            focus = {
                "phase": "export",
                "sceneIndex": seg_cur or None,
                "sceneTotal": export_payload["segmentTotal"],
                "cell": "concat" if stage == "concat" else "segment",
                "stage": stage,
            }

    # Phase + summary
    if export_active:
        stage = (export_payload or {}).get("stage") or "segments"
        if stage == "concat":
            summary = "素材完成 · 正在合并成片"
        elif stage == "finalize":
            summary = "素材完成 · 正在写入成片"
        else:
            cur = (export_payload or {}).get("segmentCurrent") or 0
            total = (export_payload or {}).get("segmentTotal") or len(cells)
            summary = f"素材完成 · 导出编码 {cur}/{total}"
        phase = "export"
    elif run and not run_terminal:
        cur = run.completed_count
        total = run.total_count or len(cells)
        cell_label = {"tts": "配音", "image": "画面"}.get((focus or {}).get("cell") or "", "素材")
        idx = (focus or {}).get("sceneIndex")
        if idx:
            summary = f"素材 {cur}/{total} · 第{idx}镜{cell_label}"
        else:
            summary = f"素材 {cur}/{total}"
        phase = "assets"
    elif export_failed:
        err_scene = next((c for c in cells if c.segment == "failed"), None)
        if err_scene:
            summary = f"导出失败 · 第{err_scene.position + 1}镜编码"
        else:
            summary = "导出失败"
        phase = "failed"
    elif export_done and (not run or run_terminal):
        purpose = (export_payload or {}).get("purpose")
        summary = "初稿已就绪" if purpose == "initial" else "成片已就绪"
        phase = "done"
    elif run and run_terminal and run.status == GenerationRunStatus.COMPLETED_WITH_FAILURES:
        summary = f"素材有失败 · {run.failed_count} 项"
        phase = "assets_failed"
    elif run and run_terminal:
        summary = "素材已完成 · 待导出"
        phase = "assets_done"
    else:
        summary = "尚未开始"
        phase = "idle"

    return PipelineProgressResponse(
        phase=phase,
        summary=summary,
        updatedAt=updated_at,
        assets=assets_payload,
        export=export_payload,
        scenes=cells,
        focus=focus,
    )


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
            visualFocus=scene.visual_focus, textAnchors=scene.text_anchors,
            lockedFields=scene.locked_fields, editedFields=scene.edited_fields,
            locked=scene.locked,
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
    try:
        pipeline_progress = _build_pipeline_progress(project, scenes, scene_responses, repository)
    except Exception as exc:
        logger.warning("pipeline progress build failed: {}", exc)
        pipeline_progress = None
    return ProjectResponse(
        projectId=project.project_id, title=project.title, source=project.source,
        sourceHistoryTaskId=project.source_history_task_id, config=project.config,
        scenes=scene_responses, jobs=jobs, updatedAt=project.updated_at.isoformat(),
        latestExport=latest_export, dirty=dirty,
        pipelineProgress=pipeline_progress,
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


def is_visual_prompt_same_as_narration(
    visual_prompt: str | None,
    narration: str | None,
) -> bool:
    """Identify the legacy fallback that copied narration into visual_prompt."""
    prompt = _normalize_match_text(visual_prompt)
    source = _normalize_match_text(narration)
    return bool(prompt and source and prompt.casefold() == source.casefold())


async def _autofill_image_prompts(
    core,
    scenes: list[Scene],
    style_prefix: str = "",
) -> None:
    """Fill missing visual prompts without ever persisting narration as a prompt."""
    missing = [
        scene
        for scene in scenes
        if not _normalize_match_text(scene.visual_prompt)
        or is_visual_prompt_same_as_narration(scene.visual_prompt, scene.narration)
    ]
    if not missing:
        return

    # Clear known legacy narration fallbacks before attempting generation. This
    # makes a later generation run able to recognize them as missing.
    for scene in missing:
        if is_visual_prompt_same_as_narration(scene.visual_prompt, scene.narration):
            scene.visual_prompt = ""

    llm = getattr(core, "llm", None)
    if llm is None:
        logger.warning(
            "Image prompt autofill skipped: LLM service unavailable; %d prompts remain empty",
            len(missing),
        )
        raise HTTPException(
            status_code=422,
            detail={
                "code": "visual_prompt_generation_failed",
                "message": "分镜画面提示词生成失败：LLM 服务不可用，未保存空提示词项目。",
                "sceneCount": len(missing),
                "scenePositions": [getattr(scene, "position", index) + 1 for index, scene in enumerate(missing)],
            },
        )

    try:
        from pixelle_video.config import config_manager

        llm_config = config_manager.get_llm_config()
        if not all(llm_config.get(key) for key in ("api_key", "base_url", "model")):
            logger.warning(
                "Image prompt autofill skipped: incomplete LLM configuration; %d prompts remain empty",
                len(missing),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "visual_prompt_generation_failed",
                    "message": "分镜画面提示词生成失败：LLM 配置不完整，未保存空提示词项目。",
                    "sceneCount": len(missing),
                    "scenePositions": [getattr(scene, "position", index) + 1 for index, scene in enumerate(missing)],
                },
            )
        prompts = await generate_image_prompts(
            llm,
            [scene.narration for scene in missing],
            min_words=20,
            max_words=80,
            style_prefix=style_prefix,
            visual_focuses=[scene.visual_focus for scene in missing],
            text_anchors=[scene.text_anchors for scene in missing],
        )
        if len(prompts) != len(missing):
            raise ValueError(f"expected {len(missing)} generated prompts, got {len(prompts)}")
        for scene, prompt in zip(missing, prompts):
            clean_prompt = _normalize_match_text(prompt)
            if clean_prompt and not is_visual_prompt_same_as_narration(clean_prompt, scene.narration):
                scene.visual_prompt = clean_prompt
    except Exception as exc:
        logger.warning(
            "Image prompt autofill failed; leaving %d visual prompts empty: %s",
            len(missing),
            exc,
        )

    remaining = [scene for scene in missing if not _normalize_match_text(scene.visual_prompt)]
    if remaining:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "visual_prompt_generation_failed",
                "message": "分镜画面提示词生成失败，未保存空提示词项目。请检查 LLM 配置后重试。",
                "sceneCount": len(remaining),
                "scenePositions": [getattr(scene, "position", index) + 1 for index, scene in enumerate(remaining)],
            },
        )


def _resolve_reuse_source_task_id(config: dict | None) -> str | None:
    cfg = config or {}
    for key in (
        "reuseTaskId",
        "reuse_task_id",
        "reuse_assets_from_task_id",
        "reuseSourceTaskId",
    ):
        value = cfg.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _normalize_match_text(value: str | None) -> str:
    return " ".join(str(value or "").split()).strip()


async def _import_assets_from_history_task(
    core,
    project: Project,
    scenes: list[Scene],
    source_task_id: str,
) -> dict[str, int]:
    """
    Copy audio/images from a completed history task into a new workbench project.

    Used when Quick Create checks 「沿用历史素材」. Without this, reuseTaskId is only
    stored in config and generation still regenerates every scene.
    """
    history = getattr(core, "history", None)
    if history is None or not hasattr(history, "get_task_detail"):
        logger.warning("History service unavailable; cannot reuse assets from {}", source_task_id)
        return {"images": 0, "audio": 0, "frames": 0}

    detail = await history.get_task_detail(source_task_id)
    if not detail or not detail.get("storyboard"):
        logger.warning(
            "reuseTaskId={} has no storyboard detail; generation will re-create assets",
            source_task_id,
        )
        return {"images": 0, "audio": 0, "frames": 0}

    storyboard = detail["storyboard"]
    frames = list(getattr(storyboard, "frames", None) or [])
    if not frames:
        return {"images": 0, "audio": 0, "frames": 0}

    snapshot = build_parameter_snapshot(
        project,
        runtime_config=getattr(core, "config", {}) or {},
    )
    images = 0
    audio = 0
    for scene, frame in zip(scenes, frames):
        image_path = getattr(frame, "image_path", None)
        if image_path and Path(image_path).is_file():
            relative = core.workbench_media.copy_upload(
                project.project_id,
                scene.scene_id,
                Path(image_path),
                Path(image_path).name,
            )
            image_fp = compute_image_fingerprint(scene.visual_prompt, snapshot)
            version = AssetVersion(
                project.project_id,
                scene.scene_id,
                AssetSource.UPLOAD,
                relative,
                prompt_snapshot=scene.visual_prompt or getattr(frame, "image_prompt", None),
                parameters={"imageFingerprint": image_fp, "reusedFromTaskId": source_task_id},
            )
            core.workbench_repository.create_asset_version(version)
            core.workbench_repository.select_asset_version(
                project.project_id,
                scene.scene_id,
                version.version_id,
            )
            core.workbench_repository.update_scene(
                scene.scene_id,
                image_fingerprint=image_fp,
                status="completed",
            )
            images += 1

        # Audio only when narration still matches — avoids wrong lip-sync reuse.
        frame_narration = _normalize_match_text(getattr(frame, "narration", None))
        scene_narration = _normalize_match_text(scene.narration)
        audio_path = getattr(frame, "audio_path", None)
        if (
            audio_path
            and Path(audio_path).is_file()
            and frame_narration
            and frame_narration == scene_narration
        ):
            audio_relative = (
                f"assets/scenes/{scene.scene_id}/audio/reused{Path(audio_path).suffix or '.mp3'}"
            )
            destination = core.workbench_media.resolve(project.project_id, audio_relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(audio_path, destination)
            audio_fp = compute_narration_fingerprint(scene.narration, snapshot)
            core.workbench_repository.update_scene(
                scene.scene_id,
                audio_relative_path=audio_relative,
                audio_fingerprint=audio_fp,
            )
            audio += 1

    logger.info(
        "Reused history assets from task {}: images={} audio={} of {} frames into project {}",
        source_task_id,
        images,
        audio,
        min(len(scenes), len(frames)),
        project.project_id,
    )
    return {"images": images, "audio": audio, "frames": min(len(scenes), len(frames))}


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(body: CreateProjectRequest, core: PixelleVideoDep, request: Request):
    """
    Create a new workbench project from Quick Create.

    Note: ``reuseTaskId`` only means "import audio/images from that history task".
    It must NOT set ``source_history_task_id`` — that column is UNIQUE and reserved for
    「作品库 → 复制为项目」(from-history), which returns the same project on repeat.
    """
    normalized_config = normalize_project_config(body.config)
    _validate_project_bgm(normalized_config)
    reuse_task_id = _resolve_reuse_source_task_id(normalized_config)
    # Keep reuse id in config for import; never bind UNIQUE source_history_task_id here.
    project = Project(
        title=body.title,
        config=normalized_config,
        source=body.source or ("history-reuse" if reuse_task_id else "quick-create"),
        source_history_task_id=None,
    )
    scene_inputs = list(body.scenes)
    split_mode = str(normalized_config.get("splitType") or normalized_config.get("split_type") or "").strip().lower()
    # Quick Create's auto mode can still leave one long, punctuation-poor scene.
    # Ask the LLM for extractive boundaries only in that narrow case; manual
    # prompts and multi-scene projects are never silently repartitioned.
    if split_mode == "auto" and len(scene_inputs) == 1:
        source_item = scene_inputs[0]
        source_narration = source_item.narration.strip()
        has_manual_prompt = bool(source_item.visual_prompt.strip())
        if len(source_narration.replace(" ", "")) > 52 and not has_manual_prompt:
            llm_service = getattr(core, "llm", None)
            if llm_service is not None:
                try:
                    director_mode = str(normalized_config.get("directorMode") or "auto").strip().lower()
                    target_count = int(
                        normalized_config.get("targetSceneCount")
                        or (normalized_config.get("sceneCount") if director_mode == "custom" else 3)
                        or 3
                    )
                    semantic_segments = await segment_narration_semantically(
                        llm_service,
                        source_narration,
                        target_count=max(2, min(target_count, 3)),
                        max_chars=52,
                    )
                    if len(semantic_segments) > 1:
                        scene_inputs = [
                            SimpleNamespace(
                                narration=item["text"],
                                visual_prompt="",
                                visual_focus=item.get("visual_focus", ""),
                                text_anchors=item.get("text_anchors", []),
                            )
                            for item in semantic_segments
                        ]
                        logger.info("Auto mode expanded one long project scene into {} scenes", len(scene_inputs))
                except Exception as exc:
                    logger.warning("Project auto segmentation unavailable; keeping original scene: {}", exc)

    scenes = []
    for position, item in enumerate(scene_inputs):
        narration = item.narration.strip()
        visual_prompt = item.visual_prompt.strip()
        # A narration copied into visualPrompt is legacy contamination, not a
        # hand-authored visual prompt. Preserve real user edits verbatim.
        if is_visual_prompt_same_as_narration(visual_prompt, narration):
            visual_prompt = ""
        scenes.append(Scene(
            project.project_id,
            position,
            narration,
            visual_prompt,
            visual_focus=str(getattr(item, "visual_focus", "") or "").strip(),
            text_anchors=[str(value).strip() for value in (getattr(item, "text_anchors", []) or []) if str(value).strip()],
            locked_fields=[str(value) for value in (getattr(item, "locked_fields", []) or [])],
            edited_fields=[str(value) for value in (getattr(item, "edited_fields", []) or [])],
            locked=bool(getattr(item, "locked", False)),
        ))
    # Quick Create image projects must have usable prompts before persistence.
    # Draft-only/static workbench projects may intentionally leave them empty
    # until their later media-generation step.
    requires_visual_prompts = bool(
        normalized_config.get("useApiImage")
        or normalized_config.get("use_api_image")
        or normalized_config.get("composition_mode") == "plain_image"
        or normalized_config.get("workflowId")
        or normalized_config.get("workflow")
    )
    if requires_visual_prompts:
        await _autofill_image_prompts(
            core,
            scenes,
            style_prefix=str(
                normalized_config.get("promptPrefix")
                or normalized_config.get("prompt_prefix")
                or ""
            ),
        )
    try:
        core.workbench_repository.create_project(project, scenes)
    except Exception as exc:
        # Surface DB uniqueness etc. as readable API errors (not bare 500 / {}).
        msg = str(exc)
        if "UNIQUE constraint failed: projects.source_history_task_id" in msg:
            raise HTTPException(
                status_code=409,
                detail=(
                    "该历史任务已复制过为项目。请直接打开已有工作台项目，"
                    "或取消「沿用历史素材」后新建（仅改风格可在原项目里「开始生成」）。"
                ),
            ) from exc
        logger.exception("create_project failed: {}", exc)
        raise HTTPException(status_code=500, detail=f"创建项目失败：{msg}") from exc
    if reuse_task_id:
        try:
            stats = await _import_assets_from_history_task(core, project, scenes, reuse_task_id)
            if stats.get("images", 0) == 0 and stats.get("audio", 0) == 0:
                logger.warning(
                    "reuseTaskId={} imported 0 assets; generation will re-create media",
                    reuse_task_id,
                )
        except Exception as exc:
            # Soft-fail: project is usable; generation will fall back to full regen.
            logger.warning(
                "Failed to import reusable assets from {}: {}",
                reuse_task_id,
                exc,
            )
    scenes = core.workbench_repository.list_project_scenes(project.project_id)
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
    # Scene updates during generation bump project.updated_at and used to 409 every
    # settings save. Config-only patches skip OCC; title changes still require a fresh stamp.
    config_only = body.config is not None and body.title is None
    if (
        body.expected_updated_at
        and body.expected_updated_at != project.updated_at.isoformat()
        and not config_only
    ):
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
        # Normalize dual camel/snake keys so export prefers the latest editor values.
        merged_config = normalize_project_config({**dict(project.config), **body.config})
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
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc)}) from exc
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
    project = Project(
        title=storyboard.title or metadata.get("title") or task_id,
        config=normalize_project_config(dict(metadata.get("input") or {})),
        source="history",
        source_history_task_id=task_id,
    )
    _validate_project_bgm(project.config)
    frames = list(storyboard.frames or [])
    scenes = [Scene(project.project_id, index, frame.narration or "", frame.image_prompt or "",
                    duration_seconds=float(frame.duration or 0), status=frame.status or "completed")
              for index, frame in enumerate(frames)]
    if not scenes:
        raise HTTPException(status_code=422, detail="history task has no scenes")
    await _autofill_image_prompts(
        core,
        scenes,
        style_prefix=str(
            project.config.get("promptPrefix")
            or project.config.get("prompt_prefix")
            or ""
        ),
    )
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
    _assert_scene_not_locked(core, project_id, scene_id)
    job = await _enqueue(core, project_id, scene_id, GenerationKind.SCENE, TaskType.WORKBENCH_SCENE,
                         {"narration": scene.narration, "prompt": scene.visual_prompt},
                         core.workbench_jobs.run_scene_job)
    return GenerationJobResponse(jobId=job.job_id, taskId=job.task_id, sceneId=scene_id,
                                 kind=job.kind.value, status=job.status.value, progress=job.progress)


@router.post("/{project_id}/scenes/{scene_id}/image-generations", response_model=GenerationJobResponse, status_code=202)
async def regenerate_image(project_id: str, scene_id: str, body: RegenerateImageRequest, core: PixelleVideoDep):
    _scene_or_404(core, project_id, scene_id)
    _assert_scene_editable(core, project_id, scene_id)
    _assert_scene_not_locked(core, project_id, scene_id)
    job = await _enqueue(core, project_id, scene_id, GenerationKind.IMAGE, TaskType.WORKBENCH_IMAGE,
                         {"prompt": body.prompt}, core.workbench_jobs.run_image_job, body.prompt)
    return GenerationJobResponse(jobId=job.job_id, taskId=job.task_id, sceneId=scene_id,
                                 kind=job.kind.value, status=job.status.value, progress=job.progress)


@router.post("/{project_id}/scenes/{scene_id}/tts", response_model=GenerationJobResponse, status_code=202)
async def regenerate_tts(project_id: str, scene_id: str, body: UpdateNarrationRequest, core: PixelleVideoDep):
    _scene_or_404(core, project_id, scene_id)
    _assert_scene_editable(core, project_id, scene_id)
    _assert_scene_not_locked(core, project_id, scene_id)
    job = await _enqueue(core, project_id, scene_id, GenerationKind.TTS, TaskType.WORKBENCH_TTS,
                         {"narration": body.narration}, core.workbench_jobs.run_tts_job, body.narration)
    return GenerationJobResponse(jobId=job.job_id, taskId=job.task_id, sceneId=scene_id,
                                 kind=job.kind.value, status=job.status.value, progress=job.progress)


@router.patch("/{project_id}/scenes/{scene_id}")
async def update_scene(project_id: str, scene_id: str, body: UpdateSceneRequest, core: PixelleVideoDep):
    scene = _scene_or_404(core, project_id, scene_id)
    _assert_scene_editable(core, project_id, scene_id)
    changes = body.model_dump(exclude_none=True, by_alias=False)
    if scene.locked and any(key != "locked" for key in changes):
        raise HTTPException(
            status_code=409,
            detail={"message": "该分镜已锁定，请先解锁后再修改", "sceneId": scene_id},
        )
    if "narration" in changes:
        changes["edited_fields"] = sorted(set(scene.edited_fields or []) | {"narration"})
    if "visual_prompt" in changes:
        changes["edited_fields"] = sorted(set(changes.get("edited_fields") or scene.edited_fields or []) | {"visualPrompt"})
    for key in ("locked_fields", "edited_fields"):
        if key in changes:
            changes[key] = [str(value) for value in changes[key] if str(value).strip()]
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
    return {
        "sceneId": scene_id,
        "narration": updated.narration,
        "visualPrompt": updated.visual_prompt,
        "visualFocus": updated.visual_focus,
        "textAnchors": updated.text_anchors,
        "lockedFields": updated.locked_fields,
        "editedFields": updated.edited_fields,
        "locked": updated.locked,
        "durationSeconds": updated.duration_seconds,
        "manualHoldSeconds": updated.manual_hold_seconds,
    }


@router.post("/{project_id}/scenes/{scene_id}/versions/{version_id}/select")
async def select_asset_version(project_id: str, scene_id: str, version_id: str, core: PixelleVideoDep):
    _scene_or_404(core, project_id, scene_id)
    _assert_scene_editable(core, project_id, scene_id)
    _assert_scene_not_locked(core, project_id, scene_id)
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
    unlocked_scene_ids = [scene_id for scene_id in body.scene_ids if not scenes[scene_id].locked]
    if not unlocked_scene_ids:
        raise HTTPException(status_code=409, detail={"message": "所选分镜均已锁定，未启动重新生成"})
    for scene_id in unlocked_scene_ids:
        _assert_scene_editable(core, project_id, scene_id)
    jobs = []
    for scene_id in unlocked_scene_ids:
        scene = scenes[scene_id]
        prompt = " ".join(part for part in (body.prompt_prefix.strip(), scene.visual_prompt.strip()) if part)
        job = await _enqueue(core, project_id, scene_id, GenerationKind.IMAGE, TaskType.WORKBENCH_IMAGE,
                             {"prompt": prompt, "promptPrefix": body.prompt_prefix},
                             core.workbench_jobs.run_image_job_limited, prompt)
        jobs.append({"jobId": job.job_id, "taskId": job.task_id, "sceneId": scene_id,
                     "kind": job.kind.value, "status": job.status.value, "progress": job.progress})
    return {"jobs": jobs}


def _active_exports_for_project(repository, project_id: str):
    return [
        rev
        for rev in repository.list_active_export_revisions()
        if rev.project_id == project_id
    ]


async def _cancel_export_work(core, revision, *, reason: str = "export cancelled") -> None:
    """Cancel task + kill tracked ffmpeg for this process; terminalize revision."""
    from api.tasks import task_manager
    from pixelle_video.services.video import kill_tracked_ffmpeg_processes

    snap = dict(revision.snapshot or {})
    task_id = snap.get("taskId") or snap.get("task_id")
    if task_id:
        try:
            await task_manager.cancel_task(str(task_id))
        except Exception as exc:
            logger.debug("cancel export task {} ignored: {}", task_id, exc)
    try:
        kill_tracked_ffmpeg_processes()
    except Exception as exc:
        logger.debug("kill tracked ffmpeg ignored: {}", exc)
    current = core.workbench_repository.get_export_revision(revision.export_id)
    if current is None:
        return
    if current.status in {GenerationStatus.PENDING, GenerationStatus.RUNNING}:
        core.workbench_repository.update_export_revision(
            revision.export_id,
            status=GenerationStatus.CANCELLED,
            error=reason,
        )


@router.post("/{project_id}/exports", status_code=202)
async def create_export(project_id: str, core: PixelleVideoDep, body: ExportRequest = ExportRequest()):
    project = core.workbench_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    active = _active_exports_for_project(core.workbench_repository, project_id)
    if active:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "export already in progress",
                "exportId": active[0].export_id,
                "status": active[0].status.value,
            },
        )
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
        # Keep the snapshot byte-for-byte aligned with the saved project config.
        # New projects are normalized on creation; legacy projects should not
        # gain synthetic director keys merely by exporting.
        "config": dict(project.config),
        "allowIncomplete": body.allow_incomplete,
        "createdFromRunId": None,
        "taskId": task.task_id,
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


@router.post("/{project_id}/exports/{export_id}/cancel", status_code=200)
async def cancel_export(project_id: str, export_id: str, core: PixelleVideoDep):
    if core.workbench_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    revision = core.workbench_repository.get_export_revision(export_id)
    if revision is None or revision.project_id != project_id:
        raise HTTPException(status_code=404, detail="export revision not found")
    if revision.status not in {GenerationStatus.PENDING, GenerationStatus.RUNNING}:
        raise HTTPException(
            status_code=409,
            detail=f"export status {revision.status.value} cannot be cancelled",
        )
    await _cancel_export_work(core, revision, reason="export cancelled by user")
    updated = core.workbench_repository.get_export_revision(export_id)
    return {
        "exportId": export_id,
        "status": (updated.status.value if updated else GenerationStatus.CANCELLED.value),
    }


@router.post("/{project_id}/exports/{export_id}/retry", status_code=202)
async def retry_export(project_id: str, export_id: str, core: PixelleVideoDep):
    if core.workbench_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    revision = core.workbench_repository.get_export_revision(export_id)
    if revision is None or revision.project_id != project_id:
        raise HTTPException(status_code=404, detail="export revision not found")
    # Allow retry when failed/cancelled, OR when stuck in pending/running
    # (ffmpeg hang leaves status=running forever; users need a force-retry path).
    if revision.status == GenerationStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="completed exports cannot be retried; start a new export")
    if revision.status not in {
        GenerationStatus.FAILED,
        GenerationStatus.CANCELLED,
        GenerationStatus.PENDING,
        GenerationStatus.RUNNING,
    }:
        raise HTTPException(status_code=409, detail=f"export status {revision.status.value} cannot be retried")
    if not core.workbench_jobs or not hasattr(core.workbench_jobs, "run_export_job"):
        raise HTTPException(status_code=503, detail="video pipeline is unavailable")
    # Stop previous attempt cleanly (task + tracked ffmpeg PIDs only — not global taskkill).
    if revision.status in {GenerationStatus.PENDING, GenerationStatus.RUNNING}:
        await _cancel_export_work(core, revision, reason="export superseded by retry")
    # Reset progress snapshot so the observatory does not keep the old stuck frame.
    from api.tasks import task_manager
    from api.tasks.models import TaskType

    task = task_manager.create_task(
        TaskType.WORKBENCH_EXPORT,
        request_params={"project_id": project_id, "export_id": export_id, "retry": True},
    )
    try:
        snap = dict(revision.snapshot or {})
        scenes = list(snap.get("scenes") or [])
        snap["progress"] = {
            "stage": "prepare",
            "segmentCurrent": 0,
            "segmentTotal": len(scenes),
            "segments": [
                {
                    "sceneId": str(item.get("sceneId") or ""),
                    "position": int(item.get("position") if item.get("position") is not None else index),
                    "status": "queued",
                }
                for index, item in enumerate(scenes)
            ],
            "updatedAt": None,
        }
        snap["taskId"] = task.task_id
        core.workbench_repository.update_export_revision(
            export_id,
            status=GenerationStatus.PENDING,
            error=None,
            snapshot=snap,
        )
    except Exception:
        core.workbench_repository.update_export_revision(
            export_id,
            status=GenerationStatus.PENDING,
            error=None,
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
    _assert_scene_not_locked(core, project_id, scene_id)
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
