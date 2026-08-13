from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[。！？!?\.…,，、；;：:\s]+")


@dataclass(frozen=True)
class AlignmentCue:
    """One timed speech unit from TTS (sentence or word)."""

    text: str
    start_ms: int
    end_ms: int

    @property
    def start(self) -> float:
        return self.start_ms / 1000.0

    @property
    def end(self) -> float:
        return self.end_ms / 1000.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def alignment_sidecar_path(audio_path: str | Path) -> Path:
    path = Path(audio_path)
    return path.with_suffix(path.suffix + ".alignment.json")


def save_alignment(audio_path: str | Path, cues: Iterable[AlignmentCue]) -> str:
    target = alignment_sidecar_path(audio_path)
    payload = {
        "version": 1,
        "cues": [cue.to_dict() for cue in cues],
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(target)


def load_alignment(audio_path: str | Path) -> list[AlignmentCue]:
    target = alignment_sidecar_path(audio_path)
    if not target.is_file():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_cues = data.get("cues") if isinstance(data, dict) else data
    return parse_alignment_payload(raw_cues)


def normalize_align_text(text: str) -> str:
    return _PUNCT_RE.sub("", _WS_RE.sub("", str(text or "")))


def parse_alignment_payload(raw: Any) -> list[AlignmentCue]:
    """Parse MiniMax subtitle JSON or our sidecar format into AlignmentCue list."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        if "cues" in raw:
            raw = raw["cues"]
        elif "subtitles" in raw:
            raw = raw["subtitles"]
        elif "utterances" in raw:
            raw = raw["utterances"]
        else:
            raw = [raw]
    if not isinstance(raw, list):
        return []

    cues: list[AlignmentCue] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(
            item.get("text")
            or item.get("content")
            or item.get("word")
            or item.get("sentence")
            or ""
        ).strip()
        start_ms = _coerce_ms(
            item.get("start_ms"),
            item.get("time_begin"),
            item.get("begin_time"),
            item.get("start_time"),
            item.get("start"),
            item.get("offset"),
            default=None,
        )
        end_ms = _coerce_ms(
            item.get("end_ms"),
            item.get("time_end"),
            item.get("end_time"),
            item.get("end"),
            default=None,
        )
        if end_ms is None and start_ms is not None:
            duration_ms = _coerce_ms(item.get("duration"), item.get("duration_ms"), default=None)
            if duration_ms is not None:
                end_ms = start_ms + duration_ms
        if not text or start_ms is None or end_ms is None:
            continue
        if end_ms <= start_ms:
            end_ms = start_ms + 1
        cues.append(AlignmentCue(text=text, start_ms=int(start_ms), end_ms=int(end_ms)))

    cues.sort(key=lambda cue: (cue.start_ms, cue.end_ms))
    return cues


def _coerce_ms(*values: Any, default: int | None = 0) -> int | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        # Heuristic: values under 1000 with a fractional part are seconds.
        if 0 < number < 1000 and not float(number).is_integer():
            return int(round(number * 1000))
        # Edge TTS offsets arrive in 100-nanosecond units (very large ints).
        if number > 10_000_000:
            return int(round(number / 10_000))
        return int(round(number))
    return default


def build_char_timeline(
    cues: list[AlignmentCue],
    total_duration: float | None = None,
) -> list[tuple[str, float, float]]:
    """
    Expand alignment cues into a per-character timeline.

    Each character inherits a linear slice of its parent cue duration.
    """
    timeline: list[tuple[str, float, float]] = []
    for cue in cues:
        compact = normalize_align_text(cue.text)
        if not compact:
            continue
        start = cue.start
        end = cue.end
        if end <= start:
            end = start + 0.05
        span = end - start
        length = len(compact)
        for index, char in enumerate(compact):
            char_start = start + span * index / length
            char_end = start + span * (index + 1) / length
            timeline.append((char, char_start, char_end))

    if total_duration is not None and timeline:
        last_end = timeline[-1][2]
        if last_end < total_duration:
            # Stretch trailing silence onto the last character window slightly.
            char, start, _ = timeline[-1]
            timeline[-1] = (char, start, float(total_duration))
    return timeline


def map_segments_to_alignment(
    segments: list[str],
    cues: list[AlignmentCue],
    duration: float,
) -> list[tuple[float, float]] | None:
    """
    Map display segments onto TTS alignment using character-index coverage.

    Returns list of (start, end) seconds aligned to ``segments``, or None if
    alignment cannot be applied confidently.
    """
    if not segments or not cues:
        return None

    timeline = build_char_timeline(cues, total_duration=duration)
    if not timeline:
        return None

    # Flatten segments into normalized characters with segment ownership.
    segment_ranges: list[tuple[int, int]] = []
    flat_chars: list[str] = []
    for segment in segments:
        compact = normalize_align_text(segment)
        start_index = len(flat_chars)
        flat_chars.extend(list(compact) if compact else ["·"])
        segment_ranges.append((start_index, len(flat_chars)))

    # If timeline and segment char counts diverge a lot, still map by proportion
    # of timeline length rather than exact string equality (TTS may rewrite text).
    n_timeline = len(timeline)
    n_segments_chars = len(flat_chars)
    if n_timeline <= 0 or n_segments_chars <= 0:
        return None

    times: list[tuple[float, float]] = []
    total = max(0.05, float(duration))
    for start_index, end_index in segment_ranges:
        # Map character indices into timeline indices proportionally.
        t0 = int(round(start_index * n_timeline / n_segments_chars))
        t1 = int(round(end_index * n_timeline / n_segments_chars))
        t0 = max(0, min(n_timeline - 1, t0))
        t1 = max(t0 + 1, min(n_timeline, t1))
        start = timeline[t0][1]
        end = timeline[t1 - 1][2]
        if end <= start:
            end = min(total, start + 0.05)
        times.append((max(0.0, start), min(total, end)))

    if times:
        # Ensure monotonic non-overlapping coverage of the audio window.
        cursor = 0.0
        fixed: list[tuple[float, float]] = []
        for index, (start, end) in enumerate(times):
            start = max(cursor, start)
            if index == len(times) - 1:
                end = total
            else:
                end = max(start + 0.05, end)
            fixed.append((start, min(total, end)))
            cursor = fixed[-1][1]
        fixed[-1] = (fixed[-1][0], total)
        return fixed
    return None


def edge_word_boundaries_to_cues(boundaries: list[dict[str, Any]]) -> list[AlignmentCue]:
    """Convert Edge TTS WordBoundary stream events into AlignmentCue list."""
    cues: list[AlignmentCue] = []
    for item in boundaries:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        # Edge reports offset/duration in 100-nanosecond units.
        offset = float(item.get("offset") or 0)
        duration = float(item.get("duration") or 0)
        start_ms = int(round(offset / 10_000))
        end_ms = int(round((offset + max(duration, 1)) / 10_000))
        if end_ms <= start_ms:
            end_ms = start_ms + 1
        cues.append(AlignmentCue(text=text, start_ms=start_ms, end_ms=end_ms))
    return cues


def slice_alignment_cues(
    cues: Iterable[AlignmentCue],
    start: float,
    end: float,
) -> list[AlignmentCue]:
    """
    Take cues that overlap absolute window ``[start, end)`` seconds and re-zero
    them to a local timeline starting at 0 (for continuous → per-scene sidecars).
    """
    start_s = max(0.0, float(start))
    end_s = max(start_s + 0.01, float(end))
    start_ms = int(round(start_s * 1000))
    end_ms = int(round(end_s * 1000))
    window = max(1, end_ms - start_ms)

    sliced: list[AlignmentCue] = []
    for cue in cues:
        if cue.end_ms <= start_ms or cue.start_ms >= end_ms:
            continue
        local_start = max(0, cue.start_ms - start_ms)
        local_end = min(window, cue.end_ms - start_ms)
        if local_end <= local_start:
            local_end = min(window, local_start + 1)
        sliced.append(
            AlignmentCue(
                text=cue.text,
                start_ms=local_start,
                end_ms=local_end,
            )
        )
    return sliced


def write_sliced_alignment_sidecar(
    continuous_audio_path: str | Path,
    scene_audio_path: str | Path,
    start: float,
    end: float,
    *,
    cues: list[AlignmentCue] | None = None,
) -> str | None:
    """
    Slice full-track alignment (if any) onto a scene audio file.

    Returns sidecar path when written, else None when no cues overlap the window.
    """
    source_cues = list(cues) if cues is not None else load_alignment(continuous_audio_path)
    if not source_cues:
        return None
    local = slice_alignment_cues(source_cues, start, end)
    if not local:
        return None
    return save_alignment(scene_audio_path, local)
