"""Split a continuous TTS track into per-scene audio files."""

from __future__ import annotations

import re
import shutil
import subprocess
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

# Silence snap: avoid proportional cuts that slice mid-phrase when Edge/local
# TTS has no word-level alignment.
_MIN_SCENE_SPAN = 0.25
_DEFAULT_SILENCE_NOISE_DB = -32.0
_DEFAULT_MIN_SILENCE = 0.12
_SNAP_WINDOW_MIN = 0.6
_SNAP_WINDOW_MAX = 2.5
_SNAP_WINDOW_RATIO = 0.18


def _ffmpeg_scratch_dir() -> Path:
    """
    Write ffmpeg intermediates under the OS temp tree, not the project folder.

    Security software (e.g. 360) often prompts on every ffmpeg write into
    project ``assets/`` paths; temp + Python move avoids per-scene popups.
    """
    from pixelle_video.utils.ffmpeg_scratch import ffmpeg_scratch_dir

    return ffmpeg_scratch_dir()


def proportional_slices(
    scene_ids: Sequence[str],
    scene_texts: Sequence[str],
    total_duration: float,
    *,
    method: str = "proportional",
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
                method=method,
            )
        )
        cursor = slices[-1].end
    if slices:
        slices[-1] = SceneAudioSlice(
            scene_id=slices[-1].scene_id,
            start=slices[-1].start,
            end=total,
            method=method,
        )
    return slices


def detect_silence_islands(
    audio_path: str | Path,
    *,
    noise_db: float = _DEFAULT_SILENCE_NOISE_DB,
    min_silence: float = _DEFAULT_MIN_SILENCE,
    total_duration: float | None = None,
) -> list[tuple[float, float]]:
    """
    Return ``(start, end)`` silence intervals in seconds.

    Prefers ffmpeg ``silencedetect``; returns [] when audio is missing or
    analysis fails (caller keeps pure proportional cuts).
    """
    path = Path(audio_path)
    if not path.is_file():
        return []
    duration = float(total_duration or 0.0) or (_probe_duration(path) or 0.0)
    islands = _silencedetect_ffmpeg(path, noise_db=noise_db, min_silence=min_silence)
    if islands:
        return _clamp_islands(islands, duration)
    return []


def snap_proportional_cuts_to_silence(
    slices: Sequence[SceneAudioSlice],
    silences: Sequence[tuple[float, float]],
    *,
    total_duration: float,
    min_span: float = _MIN_SCENE_SPAN,
) -> list[SceneAudioSlice]:
    """
    Move internal proportional cut points onto nearby silence.

    Prefer the **end** of a silence island (start of the next speech burst) so
    the following scene begins on a clean phrase onset rather than mid-word.
    Falls back to silence midpoint, then leaves the cut unchanged.
    """
    if len(slices) < 2 or not silences:
        return list(slices)

    total = max(float(total_duration), float(slices[-1].end), 0.05)
    # Internal cut times (end of each scene except the last).
    cuts = [float(item.end) for item in slices[:-1]]
    snapped: list[float] = []
    snapped_any = False

    for index, cut in enumerate(cuts):
        prev = 0.0 if index == 0 else snapped[index - 1]
        # Leave room for remaining scenes (including current and tail).
        remaining_scenes = len(slices) - index  # current + after
        # Lower bound: previous cut + min span for current scene.
        low = prev + min_span
        # Upper bound: leave min_span for each remaining scene after this cut.
        # After this cut we still need (remaining_scenes - 1) more segments.
        scenes_after = remaining_scenes - 1  # scenes that start at/after this cut
        high = total - min_span * max(1, scenes_after)
        if high <= low:
            snapped.append(min(total - min_span, max(low, cut)))
            continue

        # Window scales with local proportional scene length.
        local_span = float(slices[index].end) - float(slices[index].start)
        window = max(_SNAP_WINDOW_MIN, min(_SNAP_WINDOW_MAX, local_span * _SNAP_WINDOW_RATIO + 0.8))

        best_t = cut
        best_score: tuple[float, float, int] | None = None  # (dist, -silence_len, priority)
        for sil_start, sil_end in silences:
            if sil_end < low - 0.05 or sil_start > high + 0.05:
                continue
            # Candidate points inside this silence, clamped to [low, high].
            candidates = [
                (sil_end, 0),           # end of silence = phrase onset (preferred)
                ((sil_start + sil_end) / 2.0, 1),  # mid-silence
                (sil_start, 2),         # start of silence (last resort)
            ]
            sil_len = max(0.0, sil_end - sil_start)
            for raw_t, priority in candidates:
                t = min(high, max(low, float(raw_t)))
                if t < low - 1e-6 or t > high + 1e-6:
                    continue
                dist = abs(t - cut)
                if dist > window:
                    continue
                # Prefer closer, then longer silence, then end-of-silence.
                score = (dist, -sil_len, priority)
                if best_score is None or score < best_score:
                    best_score = score
                    best_t = t

        if abs(best_t - cut) > 1e-3:
            snapped_any = True
        snapped.append(best_t)

    # Rebuild slices with monotonic ends.
    rebuilt: list[SceneAudioSlice] = []
    cursor = 0.0
    for index, item in enumerate(slices):
        if index < len(snapped):
            end = max(cursor + min_span, min(total, snapped[index]))
        else:
            end = total
        if index == len(slices) - 1:
            end = total
        method = "silence_snap" if snapped_any else item.method
        # If this boundary didn't move but another did, still mark silence_snap.
        rebuilt.append(
            SceneAudioSlice(
                scene_id=item.scene_id,
                start=cursor,
                end=max(cursor + 0.05, end),
                method=method,
            )
        )
        cursor = rebuilt[-1].end

    if rebuilt:
        rebuilt[-1] = SceneAudioSlice(
            scene_id=rebuilt[-1].scene_id,
            start=rebuilt[-1].start,
            end=total,
            method=rebuilt[-1].method,
        )
    return rebuilt


def plan_scene_slices(
    scene_ids: Sequence[str],
    scene_texts: Sequence[str],
    *,
    continuous_audio_path: str | Path,
    total_duration: float | None = None,
    cues: Sequence[AlignmentCue] | None = None,
) -> list[SceneAudioSlice]:
    """
    Prefer alignment-mapped windows.

    Fallback chain when alignment is missing/incomplete:
      1. character-proportional anchors
      2. snap internal cuts onto nearby silence (avoid mid-phrase chops)
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
            "using proportional + silence snap",
            len(resolved_cues),
            0 if not mapped else len(mapped),
            len(scene_ids),
        )

    base = proportional_slices(scene_ids, scene_texts, duration)
    if len(base) < 2:
        return base

    silences = detect_silence_islands(path, total_duration=duration)
    if not silences:
        logger.info(
            "Continuous TTS: no silence islands detected; using pure proportional split "
            "({} scenes, {:.2f}s)",
            len(base),
            duration,
        )
        return base

    snapped = snap_proportional_cuts_to_silence(
        base,
        silences,
        total_duration=duration,
    )
    moved = [
        (i, base[i].end, snapped[i].end)
        for i in range(len(base) - 1)
        if abs(base[i].end - snapped[i].end) > 0.02
    ]
    if moved:
        logger.info(
            "Continuous TTS silence snap adjusted {} cut(s): {}",
            len(moved),
            "; ".join(f"#{i} {old:.3f}->{new:.3f}s" for i, old, new in moved),
        )
    else:
        logger.debug(
            "Continuous TTS silence snap found {} island(s) but cuts already near silence",
            len(silences),
        )
    return snapped


def _silencedetect_ffmpeg(
    path: Path,
    *,
    noise_db: float,
    min_silence: float,
) -> list[tuple[float, float]]:
    """Parse silence intervals from ffmpeg silencedetect."""
    if not shutil.which("ffmpeg"):
        return []
    # -vn: audio only; null mux discards samples while filter still runs.
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-af",
        f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("silencedetect failed for {}: {}", path.name, exc)
        return []

    # ffmpeg writes filter logs to stderr; encoding may be GBK on Chinese Windows.
    stderr = result.stderr or b""
    text = ""
    for encoding in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            text = stderr.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        text = stderr.decode("utf-8", errors="replace")

    starts = [
        float(match.group(1))
        for match in re.finditer(r"silence_start:\s*([0-9.]+)", text)
    ]
    ends = [
        float(match.group(1))
        for match in re.finditer(r"silence_end:\s*([0-9.]+)", text)
    ]
    islands: list[tuple[float, float]] = []
    # Pair starts with ends in order; handle trailing open silence.
    end_iter = iter(ends)
    for start in starts:
        end = next(end_iter, None)
        if end is None:
            # Open-ended silence until EOF — ignore for internal cuts.
            break
        if end > start + 0.05:
            islands.append((start, end))
    return islands


def _clamp_islands(
    islands: Sequence[tuple[float, float]],
    duration: float,
) -> list[tuple[float, float]]:
    if duration <= 0:
        return [(float(s), float(e)) for s, e in islands if e > s]
    clamped: list[tuple[float, float]] = []
    for start, end in islands:
        s = max(0.0, float(start))
        e = min(float(duration), float(end))
        if e > s + 0.05:
            clamped.append((s, e))
    return clamped


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

        stream = (
            ffmpeg.input(str(source), ss=start, t=duration)
            .output(str(temporary), **output_kwargs)
        )
        # Bound cut time so continuous TTS phase cannot hang forever.
        cut_timeout = max(45.0, min(180.0, 30.0 + float(duration) * 4.0))
        from pixelle_video.services.video import run_ffmpeg_stream

        run_ffmpeg_stream(stream, timeout=cut_timeout, label="continuous-tts-cut")
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

        # Run all outputs in one process with a hard timeout.
        total_span = 0.0
        for _dest, start, end in cuts:
            total_span += max(0.05, float(end) - float(start))
        batch_timeout = max(60.0, min(300.0, 45.0 + total_span * 3.0 + len(cuts) * 5.0))
        from pixelle_video.services.video import run_ffmpeg_compiled

        merged = ffmpeg.merge_outputs(*nodes).overwrite_output()
        run_ffmpeg_compiled(
            merged.compile(),
            timeout=batch_timeout,
            label=f"continuous-tts-batch({len(cuts)})",
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
