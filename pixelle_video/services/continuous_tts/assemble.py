"""Join multi-scene narrations into one continuous TTS script."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pixelle_video.services.continuous_tts.models import (
    AssembledScript,
    ContinuousSceneSegment,
)

# Default join keeps Chinese narration flow without inserting long pauses.
_DEFAULT_JOIN = "\n"
_TERMINAL_PUNCT = set("。！？!?；;…")


def normalize_tts_delivery(value: Any) -> str:
    """Map UI / config labels to continuous | per_scene."""
    text = str(value or "continuous").strip().lower().replace("-", "_")
    if text in {"per_scene", "perscene", "segment", "scene", "legacy", "sequential"}:
        return "per_scene"
    return "continuous"


def should_use_continuous_tts(
    *,
    delivery: Any,
    scene_count: int,
    pending_tts_count: int,
    provider: Any = None,
) -> bool:
    """
    Recommended Phase-1 policy:

    - delivery defaults to continuous
    - only multi-scene runs with 2+ TTS targets
    - all current providers can synthesize one long string
    """
    if normalize_tts_delivery(delivery) != "continuous":
        return False
    if scene_count < 2 or pending_tts_count < 2:
        return False
    # ComfyUI still benefits from one workflow call; no hard block.
    del provider
    return True


def _ensure_terminal_punct(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    if cleaned[-1] in _TERMINAL_PUNCT:
        return cleaned
    # Prefer Chinese full stop for mixed CN narration.
    return cleaned + "。"


def assemble_continuous_script(
    segments: Sequence[ContinuousSceneSegment],
    *,
    join_separator: str = _DEFAULT_JOIN,
) -> AssembledScript:
    """
    Build one continuous narration from ordered scene segments.

    Scene texts kept separately feed alignment-based split mapping.
    """
    ordered = sorted(segments, key=lambda item: item.position)
    if not ordered:
        raise ValueError("continuous TTS requires at least one scene segment")

    scene_texts: list[str] = []
    joined_parts: list[str] = []
    for segment in ordered:
        text = str(segment.narration or "").strip()
        if not text:
            text = "。"
        scene_texts.append(text)
        joined_parts.append(_ensure_terminal_punct(text))

    full_text = join_separator.join(joined_parts).strip()
    if not full_text:
        raise ValueError("continuous TTS script is empty")

    return AssembledScript(
        full_text=full_text,
        scene_texts=tuple(scene_texts),
        segments=tuple(ordered),
        join_separator=join_separator,
    )


def delivery_from_snapshot(parameter_snapshot: Mapping[str, Any] | None) -> str:
    snapshot = parameter_snapshot or {}
    tts = snapshot.get("tts") if isinstance(snapshot.get("tts"), Mapping) else {}
    config = snapshot.get("config") if isinstance(snapshot.get("config"), Mapping) else {}
    return normalize_tts_delivery(
        (tts or {}).get("delivery")
        or (config or {}).get("ttsDelivery")
        or (config or {}).get("tts_delivery")
        or "continuous"
    )
