from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateProjectScene(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    narration: str = Field(..., min_length=1)
    visual_prompt: str = Field("", alias="visualPrompt")

    @field_validator("narration")
    @classmethod
    def narration_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("narration must not be blank")
        return value


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    title: str = Field(..., min_length=1, max_length=200)
    scenes: list[CreateProjectScene] = Field(..., min_length=1, max_length=100)
    config: dict[str, Any] = Field(default_factory=dict)
    source: Literal["quick-create", "history"] = "quick-create"

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class RegenerateImageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    prompt: str = Field(..., min_length=1)

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be blank")
        return value


class UpdateNarrationRequest(BaseModel):
    narration: str = Field(..., min_length=1)

    @field_validator("narration")
    @classmethod
    def narration_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("narration must not be blank")
        return value


class AssetVersionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    version_id: str = Field(alias="versionId")
    source: Literal["ai", "upload"]
    image_url: str = Field(alias="imageUrl")
    thumbnail_url: str | None = Field(default=None, alias="thumbnailUrl")
    prompt_snapshot: str | None = Field(default=None, alias="promptSnapshot")
    created_at: str = Field(alias="createdAt")


class ProjectSceneResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    scene_id: str = Field(alias="sceneId")
    position: int
    narration: str
    visual_prompt: str = Field(alias="visualPrompt")
    current_version_id: str | None = Field(alias="currentVersionId")
    audio_url: str | None = Field(default=None, alias="audioUrl")
    duration_seconds: float = Field(alias="durationSeconds")
    manual_hold_seconds: float = Field(alias="manualHoldSeconds")
    status: str
    versions: list[AssetVersionResponse]


class GenerationJobResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    job_id: str = Field(alias="jobId")
    task_id: str = Field(alias="taskId")
    scene_id: str | None = Field(default=None, alias="sceneId")
    kind: Literal["scene", "image", "tts", "export"]
    status: str
    progress: float
    error: str | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    project_id: str = Field(alias="projectId")
    title: str
    source: str
    source_history_task_id: str | None = Field(default=None, alias="sourceHistoryTaskId")
    config: dict[str, Any]
    scenes: list[ProjectSceneResponse]
    jobs: list[GenerationJobResponse]
    updated_at: str = Field(alias="updatedAt")
