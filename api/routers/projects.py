from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from api.dependencies import PixelleVideoDep
from api.schemas.workbench import (
    AssetVersionResponse,
    CreateProjectRequest,
    GenerationJobResponse,
    ProjectResponse,
    ProjectSceneResponse,
)
from pixelle_video.models.workbench import Project, Scene

router = APIRouter(prefix="/projects", tags=["Workbench Projects"])


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

