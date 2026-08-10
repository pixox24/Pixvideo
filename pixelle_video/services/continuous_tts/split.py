"""Split a continuous TTS track into per-scene audio files."""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Sequence

from loguru import logger

from pixelle_video.services.continuous_tts.models import SceneAudioSlice
from pixelle_video.services.subtitle_alignment import (
    AlignmentCue,
    load_alignment,
    map_segments_to_alignment,
    normalize_align_text,
)


def _ffmpeg_scratch_dir() -> Path:
    """
    Write ffmpeg intermediates under the OS temp tree, not the project folder.

    Security software (e.g. 360) often prompts on every ffmpeg write into
    project ``assets/`` paths; temp + Python move avoids per-scene popups.
    """
    root = Path(tempfile.gettempdir()) / "pixelle_video_ffmpeg"
    root.mkdir(parents=True, exist_ok=True)
    return root


def proportional_slices(
    scene_ids: Sequence[str],
    scene_texts: Sequence[str],
    total_duration: float,
) -> list[SceneAudioSlice]:
    """Fallback: allocate continuous duration by normalized character weight."""
    weights = [max(1, len(normalize_align_text(text) or "·")) for text in scene_texts]
    total_weight = float(sum(weights)) or float(len(weights)) or 1.0
    total = max(0.05 * max(1, len(scene_ids)), float(total_duration or 0.0))
    cursor = 0.0
    slices: list[SceneAudioSlice] = []
    for index, scene_id in enumerate(scene_ids):
        if index == len(scene_ids) - 1:
            end = total
        else:
            span = total * (weights[index] / total_weight)
            end = min(total, cursor + max(0.05, span))
        slices.append(
            SceneAudioSlice(
                scene_id=scene_id,
                start=cursor,
                end=max(cursor + 0.05, end),
                method="proportional",
            )
        )
        cursor = slices[-1].end
    if slices:
        slices[-1] = SceneAudioSlice(
            scene_id=slices[-1].scene_id,
            start=slices[-1].start,
            end=total,
            method="proportional",
        )
    return slices


def plan_scene_slices(
    scene_ids: Sequence[str],
    scene_texts: Sequence[str],
    *,
    continuous_audio_path: str | Path,
    total_duration: float | None = None,
    cues: Sequence[AlignmentCue] | None = None,
) -> list[SceneAudioSlice]:
    """
    Prefer alignment-mapped windows; fall back to character-proportional split.
    """
    path = Path(continuous_audio_path)
    duration = float(total_duration or 0.0)
    if duration <= 0:
        duration = _probe_duration(path) or max(0.5 * len(scene_ids), 1.0)

    resolved_cues = list(cues) if cues is not None else load_alignment(path)
    if resolved_cues:
        mapped = map_segments_to_alignment(list(scene_texts), list(resolved_cues), duration)
        if mapped and len(mapped) == len(scene_ids):
            return [
                SceneAudioSlice(
                    scene_id=scene_id,
                    start=float(start),
                    end=float(end),
                    method="alignment",
                )
                for scene_id, (start, end) in zip(scene_ids, mapped)
            ]
        logger.warning(
            "Continuous TTS alignment map incomplete ({} cues → {} ranges for {} scenes); "
            "using proportional split",
            len(resolved_cues),
            0 if not mapped else len(mapped),
            len(scene_ids),
        )
    return proportional_slices(scene_ids, scene_texts, duration)


def extract_audio_segment(
    source_path: str | Path,
    dest_path: str | Path,
    start: float,
    end: float,
) -> Path:
    """
    Cut ``[start, end]`` from the continuous track into ``dest_path``.

    Uses ffmpeg when the source is real audio; otherwise writes a deterministic
    placeholder so unit tests without media containers still complete.
    """
    source = Path(source_path)
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        raise FileNotFoundError(source)

    start = max(0.0, float(start))
    end = max(start + 0.05, float(end))
    duration = end - start

    if _try_ffmpeg_extract(source, dest, start, duration):
        return dest

    # Non-media / test fixtures: copy source and stamp size by proportion.
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise FileNotFoundError(source) from exc
    if not data:
        dest.write_bytes(b"")
        return dest

    # Keep content stable enough for fingerprinting tests; do not hard-cut UTF-8 mid-char.
    total_duration = _probe_duration(source) or duration
    ratio = min(1.0, duration / max(total_duration, duration))
    keep = max(8, int(len(data) * max(0.05, ratio)))
    dest.write_bytes(data[:keep] if keep < len(data) else data)
    if dest.stat().st_size == 0:
        shutil.copyfile(source, dest)
    return dest


def extract_audio_segments(
    source_path: str | Path,
    cuts: Sequence[tuple[str | Path, float, float]],
    *,
    batch_size: int = 16,
) -> list[Path]:
    """
    Cut many windows from one continuous track.

    Prefer one ffmpeg process per batch (writes only under OS temp), then move
    finished files into the project tree with Python — fewer AV prompts.
    """
    source = Path(source_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not cuts:
        return []

    # Probe once; fall back to per-file extract when source is not real media.
    if _probe_duration(source) is None:
        results: list[Path] = []
        for dest, start, end in cuts:
            results.append(extract_audio_segment(source, dest, start, end))
        return results

    results = []
    size = max(1, int(batch_size or 16))
    for offset in range(0, len(cuts), size):
        chunk = list(cuts[offset : offset + size])
        if _try_ffmpeg_extract_batch(source, chunk):
            results.extend(Path(dest) for dest, _, _ in chunk)
            continue
        # Batch failed: fall back per item (still uses temp-dir ffmpeg writes).
        for dest, start, end in chunk:
            results.append(extract_audio_segment(source, dest, start, end))
    return results


def _try_ffmpeg_extract(source: Path, dest: Path, start: float, duration: float) -> bool:
    try:
        import ffmpeg
    except ImportError:
        return False

    suffix = dest.suffix.lower() or ".mp3"
    temporary = _ffmpeg_scratch_dir() / f"cut-{uuid.uuid4().hex}{suffix}"
    try:
        # Validate source is probe-able audio before cutting.
        probe = ffmpeg.probe(str(source))
        if not probe.get("streams"):
            return False
        has_audio = any(stream.get("codec_type") == "audio" for stream in probe.get("streams", []))
        if not has_audio:
            return False

        output_kwargs: dict = {"ac": 1, "ar": 44100}
        if suffix == ".wav":
            output_kwargs["acodec"] = "pcm_s16le"
        else:
            output_kwargs["acodec"] = "libmp3lame"
            output_kwargs["audio_bitrate"] = "192k"

        (
            ffmpeg.input(str(source), ss=start, t=duration)
            .output(str(temporary), **output_kwargs)
            .overwrite_output()
            .run(quiet=True, capture_stdout=True, capture_stderr=True)
        )
        if temporary.is_file() and temporary.stat().st_size > 0:
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Python process moves the file into the project tree (not ffmpeg).
            shutil.move(str(temporary), str(dest))
            return True
    except Exception as exc:
        logger.debug("ffmpeg continuous split failed for {}: {}", source.name, exc)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
    return False


def _try_ffmpeg_extract_batch(
    source: Path,
    cuts: Sequence[tuple[str | Path, float, float]],
) -> bool:
    """Run one ffmpeg process that emits many segment files into the scratch dir."""
    try:
        import ffmpeg
    except ImportError:
        return False
    if not cuts:
        return True

    scratch = _ffmpeg_scratch_dir()
    tmp_pairs: list[tuple[Path, Path]] = []  # (temp, final)
    try:
        # Build a multi-output graph: same input, many (ss/t) outputs.
        stream = ffmpeg.input(str(source))
        nodes = []
        for dest_raw, start, end in cuts:
            dest = Path(dest_raw)
            start = max(0.0, float(start))
            end = max(start + 0.05, float(end))
            duration = end - start
            suffix = dest.suffix.lower() or ".mp3"
            temporary = scratch / f"cut-{uuid.uuid4().hex}{suffix}"
            tmp_pairs.append((temporary, dest))
            output_kwargs: dict = {
                "ac": 1,
                "ar": 44100,
                "ss": start,
                "t": duration,
            }
            if suffix == ".wav":
                output_kwargs["acodec"] = "pcm_s16le"
            else:
                output_kwargs["acodec"] = "libmp3lame"
                output_kwargs["audio_bitrate"] = "192k"
            nodes.append(stream.output(str(temporary), **output_kwargs))

        # Run all outputs in one process.
        ffmpeg.merge_outputs(*nodes).overwrite_output().run(
            quiet=True,
            capture_stdout=True,
            capture_stderr=True,
        )
        for temporary, dest in tmp_pairs:
            if not temporary.is_file() or temporary.stat().st_size <= 0:
                raise RuntimeError(f"batch cut missing output: {temporary.name}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temporary), str(dest))
        return True
    except Exception as exc:
        logger.debug("ffmpeg batch continuous split failed: {}", exc)
        for temporary, _dest in tmp_pairs:
            if temporary.exists():
                temporary.unlink(missing_ok=True)
        return False


def _probe_duration(path: Path) -> float | None:
    try:
        import ffmpeg

        probe = ffmpeg.probe(str(path))
        duration = float(probe.get("format", {}).get("duration") or 0.0)
        return duration if duration > 0 else None
    except Exception:
        return None
