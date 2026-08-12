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


class UpdateSceneRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    narration: str | None = Field(default=None, min_length=1)
    visual_prompt: str | None = Field(default=None, alias="visualPrompt")
    manual_hold_seconds: float | None = Field(default=None, ge=0, alias="manualHoldSeconds")
    duration_seconds: float | None = Field(default=None, gt=0, alias="durationSeconds")

    @field_validator("narration")
    @classmethod
    def optional_narration_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("narration must not be blank")
        return value


class ReorderScenesRequest(BaseModel):
    scene_ids: list[str] = Field(..., min_length=1, alias="sceneIds")
    model_config = ConfigDict(populate_by_name=True)


class TimelineUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    scene_ids: list[str] = Field(..., min_length=1, alias="sceneIds")
    holds: dict[str, float] = Field(default_factory=dict)

    @field_validator("holds")
    @classmethod
    def holds_are_finite_non_negative(cls, value: dict[str, float]) -> dict[str, float]:
        import math
        if any(not math.isfinite(number) or number < 0 for number in value.values()):
            raise ValueError("holds must be finite and non-negative")
        return value


class BatchImageRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    scene_ids: list[str] = Field(..., min_length=1, max_length=100, alias="sceneIds")
    prompt_prefix: str = Field(default="", max_length=1000, alias="promptPrefix")

    @field_validator("scene_ids")
    @classmethod
    def scene_ids_are_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("sceneIds must be unique")
        return value


class ExportRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    allow_incomplete: bool = Field(default=False, alias="allowIncomplete")


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    config: dict[str, Any] | None = None
    expected_updated_at: str | None = Field(default=None, alias="expectedUpdatedAt")

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class GenerationRunCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    scene_ids: list[str] | None = Field(default=None, alias="sceneIds")
    config_override: dict[str, Any] = Field(default_factory=dict, alias="configOverride")


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
    generation_state: dict[str, Any] = Field(default_factory=dict, alias="generationState")


class GenerationRunItemResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    item_id: str = Field(alias="itemId")
    scene_id: str = Field(alias="sceneId")
    position: int
    status: str
    phase: str
    tts_status: str = Field(alias="ttsStatus")
    image_status: str = Field(alias="imageStatus")
    skip_reason: str | None = Field(default=None, alias="skipReason")
    candidate_version_id: str | None = Field(default=None, alias="candidateVersionId")
    error: str | None = None
    updated_at: str = Field(alias="updatedAt")


class GenerationRunResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    run_id: str = Field(alias="runId")
    project_id: str = Field(alias="projectId")
    task_id: str = Field(alias="taskId")
    status: str
    current_scene_id: str | None = Field(default=None, alias="currentSceneId")
    total_count: int = Field(alias="totalCount")
    completed_count: int = Field(alias="completedCount")
    skipped_count: int = Field(alias="skippedCount")
    failed_count: int = Field(alias="failedCount")
    candidate_review_count: int = Field(alias="candidateReviewCount")
    pause_requested: bool = Field(alias="pauseRequested")
    cancel_requested: bool = Field(alias="cancelRequested")
    error: str | None = None
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    allowed_actions: list[str] = Field(default_factory=list, alias="allowedActions")
    items: list[GenerationRunItemResponse]


class GenerationJobResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    job_id: str = Field(alias="jobId")
    task_id: str = Field(alias="taskId")
    scene_id: str | None = Field(default=None, alias="sceneId")
    kind: Literal["scene", "image", "tts", "export"]
    status: str
    progress: float
    error: str | None = None


class LatestExportResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    export_id: str = Field(alias="exportId")
    purpose: Literal["initial", "manual"] | None = None
    status: str
    output_url: str | None = Field(default=None, alias="outputUrl")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    progress: dict[str, Any] | None = None
    task_id: str | None = Field(default=None, alias="taskId")


class PipelineSceneCellResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    scene_id: str = Field(alias="sceneId")
    position: int
    narration: str = ""
    tts: str
    image: str
    segment: str


class PipelineProgressResponse(BaseModel):
    """Workbench progress observatory payload (assets + export)."""
    model_config = ConfigDict(populate_by_name=True)
    phase: str
    summary: str
    updated_at: str | None = Field(default=None, alias="updatedAt")
    assets: dict[str, Any] | None = None
    export: dict[str, Any] | None = None
    scenes: list[PipelineSceneCellResponse] = Field(default_factory=list)
    focus: dict[str, Any] | None = None


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
    latest_export: LatestExportResponse | None = Field(default=None, alias="latestExport")
    dirty: bool = False
    pipeline_progress: PipelineProgressResponse | None = Field(default=None, alias="pipelineProgress")
