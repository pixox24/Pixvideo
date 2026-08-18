"""Data models for editable local video projects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    """Return an aware UTC timestamp for persisted project records."""
    return datetime.now(timezone.utc)


DEFAULT_EMPTY_SCENE_SECONDS = 3.0


def effective_scene_duration(audio_seconds: float, manual_hold_seconds: float) -> float:
    """Visual duration is audio-driven and may only be extended by a hold."""
    duration = max(float(audio_seconds), float(audio_seconds) + max(float(manual_hold_seconds), 0.0))
    return duration if duration > 0 else DEFAULT_EMPTY_SCENE_SECONDS


class AssetSource(str, Enum):
    AI = "ai"
    UPLOAD = "upload"


class GenerationKind(str, Enum):
    SCENE = "scene"
    IMAGE = "image"
    TTS = "tts"
    EXPORT = "export"


class GenerationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    CANCELLED = "cancelled"
    FAILED = "failed"


class GenerationRunItemStatus(str, Enum):
    QUEUED = "queued"
    RUNNING_TTS = "running_tts"
    RUNNING_IMAGE = "running_image"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CANDIDATE_REVIEW = "candidate_review"


class GenerationPhase(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Project:
    title: str
    config: dict[str, Any]
    project_id: str = field(default_factory=lambda: uuid4().hex)
    source: str = "quick-create"
    source_history_task_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class Scene:
    project_id: str
    position: int
    narration: str
    visual_prompt: str
    scene_id: str = field(default_factory=lambda: uuid4().hex)
    current_version_id: str | None = None
    audio_relative_path: str | None = None
    subtitle_alignment: list[dict[str, Any]] = field(default_factory=list)
    duration_seconds: float = 0.0
    manual_hold_seconds: float = 0.0
    duration_mode: str = "audio"
    status: str = "pending"
    updated_at: datetime = field(default_factory=utc_now)
    image_fingerprint: str | None = None
    audio_fingerprint: str | None = None
    visual_focus: str = ""
    text_anchors: list[str] = field(default_factory=list)
    locked_fields: list[str] = field(default_factory=list)
    edited_fields: list[str] = field(default_factory=list)
    locked: bool = False


@dataclass
class AssetVersion:
    project_id: str
    scene_id: str | None
    source: AssetSource
    relative_path: str
    prompt_snapshot: str | None = None
    version_id: str = field(default_factory=lambda: uuid4().hex)
    thumbnail_relative_path: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class GenerationJob:
    project_id: str
    kind: GenerationKind
    task_id: str
    request_snapshot: dict[str, Any]
    scene_id: str | None = None
    job_id: str = field(default_factory=lambda: uuid4().hex)
    status: GenerationStatus = GenerationStatus.PENDING
    progress: float = 0.0
    error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class GenerationRun:
    project_id: str
    task_id: str
    parameter_snapshot: dict[str, Any]
    run_id: str = field(default_factory=lambda: uuid4().hex)
    status: GenerationRunStatus = GenerationRunStatus.QUEUED
    current_scene_id: str | None = None
    total_count: int = 0
    completed_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    candidate_review_count: int = 0
    pause_requested: bool = False
    cancel_requested: bool = False
    error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            GenerationRunStatus.COMPLETED,
            GenerationRunStatus.COMPLETED_WITH_FAILURES,
            GenerationRunStatus.CANCELLED,
            GenerationRunStatus.FAILED,
        }


@dataclass
class GenerationRunItem:
    run_id: str
    scene_id: str
    position: int
    narration_snapshot: str
    prompt_snapshot: str
    narration_fingerprint: str
    image_fingerprint: str
    item_id: str = field(default_factory=lambda: uuid4().hex)
    tts_status: GenerationPhase = GenerationPhase.PENDING
    image_status: GenerationPhase = GenerationPhase.PENDING
    status: GenerationRunItemStatus = GenerationRunItemStatus.QUEUED
    skip_reason: str | None = None
    candidate_version_id: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            GenerationRunItemStatus.COMPLETED,
            GenerationRunItemStatus.SKIPPED,
            GenerationRunItemStatus.FAILED,
            GenerationRunItemStatus.CANCELLED,
            GenerationRunItemStatus.CANDIDATE_REVIEW,
        }


@dataclass
class ExportRevision:
    project_id: str
    snapshot: dict[str, Any]
    export_id: str = field(default_factory=lambda: uuid4().hex)
    output_relative_path: str | None = None
    status: GenerationStatus = GenerationStatus.PENDING
    error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
