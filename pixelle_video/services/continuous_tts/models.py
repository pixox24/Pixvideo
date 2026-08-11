"""Datatypes for continuous multi-scene TTS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContinuousSceneSegment:
    """One scene participating in a continuous TTS pass."""

    scene_id: str
    item_id: str
    position: int
    narration: str
    narration_fingerprint: str


@dataclass(frozen=True)
class AssembledScript:
    """Joined narration plus the original scene texts used for alignment mapping."""

    full_text: str
    scene_texts: tuple[str, ...]
    segments: tuple[ContinuousSceneSegment, ...]
    join_separator: str

    @property
    def scene_ids(self) -> list[str]:
        return [segment.scene_id for segment in self.segments]


@dataclass(frozen=True)
class SceneAudioSlice:
    """Time window (seconds) for one scene inside the continuous track."""

    scene_id: str
    start: float
    end: float
    method: str  # "alignment" | "proportional" | "silence_snap"

    @property
    def duration(self) -> float:
        return max(0.05, float(self.end) - float(self.start))


@dataclass
class ContinuousSplitResult:
    """Per-scene audio paths after cutting the continuous track."""

    continuous_relative_path: str
    continuous_absolute_path: str
    slices: list[SceneAudioSlice]
    scene_results: dict[str, dict[str, Any]]
