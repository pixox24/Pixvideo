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
class ExportRevision:
    project_id: str
    snapshot: dict[str, Any]
    export_id: str = field(default_factory=lambda: uuid4().hex)
    output_relative_path: str | None = None
    status: GenerationStatus = GenerationStatus.PENDING
    error: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
