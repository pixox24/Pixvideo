from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from api.dependencies import PixelleVideoDep
from api.schemas.workbench import (
    AssetVersionResponse,
    CreateProjectRequest,
    GenerationJobResponse,
    ProjectResponse,
    ProjectSceneResponse,
    RegenerateImageRequest,
    UpdateNarrationRequest,
)
from api.tasks import task_manager
from api.tasks.models import TaskType
from pixelle_video.models.workbench import GenerationJob, GenerationKind, Project, Scene

router = APIRouter(prefix="/projects", tags=["Workbench Projects"])


def _scene_or_404(core, project_id: str, scene_id: str):
    if core.workbench_repository.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    scene = core.workbench_repository.get_scene(scene_id)
    if scene is None or scene.project_id != project_id:
        raise HTTPException(status_code=404, detail="scene not found")
    return scene


async def _enqueue(core, project_id: str, scene_id: str | None, kind: GenerationKind,
                   task_type: TaskType, request_snapshot: dict, runner, *runner_args):
    task = task_manager.create_task(task_type, request_params=request_snapshot)
    job = GenerationJob(project_id, kind, task.task_id, request_snapshot, scene_id=scene_id)
    core.workbench_repository.create_generation_job(job)
    await task_manager.execute_task(task.task_id, runner, project_id, scene_id, task.task_id, *runner_args)
    return job


def _response(project, scenes, repository, media, request: Request) -> ProjectResponse:
    scene_responses = []
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
        scene_responses.append(ProjectSceneResponse(
            sceneId=scene.scene_id, position=scene.position, narration=scene.narration,
            visualPrompt=scene.visual_prompt, currentVersionId=scene.current_version_id,
            audioUrl=audio_url, durationSeconds=scene.duration_seconds,
            manualHoldSeconds=scene.manual_hold_seconds, status=scene.status,
            versions=version_responses,
        ))
    return ProjectResponse(
        projectId=project.project_id, title=project.title, source=project.source,
        sourceHistoryTaskId=project.source_history_task_id, config=project.config,
        scenes=scene_responses, jobs=[], updatedAt=project.updated_at.isoformat(),
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(body: CreateProjectRequest, core: PixelleVideoDep, request: Request):
    project = Project(title=body.title, config=body.config, source=body.source)
    scenes = [Scene(project.project_id, position, item.narration, item.visual_prompt)
              for position, item in enumerate(body.scenes)]
    core.workbench_repository.create_project(project, scenes)
    return _response(project, scenes, core.workbench_repository, core.workbench_media, request)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, core: PixelleVideoDep, request: Request):
    project = core.workbench_repository.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    scenes = core.workbench_repository.list_project_scenes(project_id)
    return _response(project, scenes, core.workbench_repository, core.workbench_media, request)


@router.post("/{project_id}/scenes/{scene_id}/generate", response_model=GenerationJobResponse, status_code=202)
async def generate_scene(project_id: str, scene_id: str, core: PixelleVideoDep):
    scene = _scene_or_404(core, project_id, scene_id)
    job = await _enqueue(core, project_id, scene_id, GenerationKind.SCENE, TaskType.WORKBENCH_SCENE,
                         {"narration": scene.narration, "prompt": scene.visual_prompt},
                         core.workbench_jobs.run_scene_job)
    return GenerationJobResponse(jobId=job.job_id, taskId=job.task_id, sceneId=scene_id,
                                 kind=job.kind.value, status=job.status.value, progress=job.progress)


@router.post("/{project_id}/scenes/{scene_id}/image-generations", response_model=GenerationJobResponse, status_code=202)
async def regenerate_image(project_id: str, scene_id: str, body: RegenerateImageRequest, core: PixelleVideoDep):
    _scene_or_404(core, project_id, scene_id)
    job = await _enqueue(core, project_id, scene_id, GenerationKind.IMAGE, TaskType.WORKBENCH_IMAGE,
                         {"prompt": body.prompt}, core.workbench_jobs.run_image_job, body.prompt)
    return GenerationJobResponse(jobId=job.job_id, taskId=job.task_id, sceneId=scene_id,
                                 kind=job.kind.value, status=job.status.value, progress=job.progress)


@router.post("/{project_id}/scenes/{scene_id}/tts", response_model=GenerationJobResponse, status_code=202)
async def regenerate_tts(project_id: str, scene_id: str, body: UpdateNarrationRequest, core: PixelleVideoDep):
    _scene_or_404(core, project_id, scene_id)
    job = await _enqueue(core, project_id, scene_id, GenerationKind.TTS, TaskType.WORKBENCH_TTS,
                         {"narration": body.narration}, core.workbench_jobs.run_tts_job, body.narration)
    return GenerationJobResponse(jobId=job.job_id, taskId=job.task_id, sceneId=scene_id,
                                 kind=job.kind.value, status=job.status.value, progress=job.progress)
