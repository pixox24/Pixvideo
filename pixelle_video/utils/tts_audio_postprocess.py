"""Lightweight post-processing for per-scene TTS clips.

Goal: reduce "different speaker" artifacts when clips are generated one-by-one:
- normalize loudness across scenes
- short fade in/out to soften hard cuts
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

from loguru import logger

# Shared speaker-lock phrase for multi-scene style prompts (MiMo / design).
SPEAKER_LOCK_PHRASE = (
    "同一讲述者全程口播：音色、音高、气息与语速保持高度一致，"
    "像同一条录音切分，不要切换角色或情绪基调"
)


def with_speaker_lock(style: str | None, *, multi_scene: bool, force: bool = False) -> str | None:
    """Append a stable speaker-identity constraint for multi-scene narration."""
    base = str(style or "").strip()
    if not multi_scene and not force:
        return base or None
    if SPEAKER_LOCK_PHRASE in base:
        return base or SPEAKER_LOCK_PHRASE
    if not base:
        return SPEAKER_LOCK_PHRASE if (multi_scene or force) else None
    return f"{base.rstrip('。.;；,，')}。{SPEAKER_LOCK_PHRASE}"


def postprocess_tts_clip(
    audio_path: str | Path,
    *,
    target_i: float = -16.0,
    true_peak: float = -1.5,
    lra: float = 11.0,
    fade_ms: int = 40,
) -> Path:
    """
    Normalize loudness and apply short fades in-place.

    Uses ffmpeg when available; on failure returns the original file unchanged.
    """
    path = Path(audio_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    try:
        import ffmpeg
    except ImportError:
        logger.warning("ffmpeg-python not available; skip TTS post-process for {}", path)
        return path

    try:
        probe = ffmpeg.probe(str(path))
        duration = float(probe.get("format", {}).get("duration") or 0.0)
    except Exception as exc:
        logger.warning("Failed to probe TTS audio {}: {}", path, exc)
        return path

    if duration <= 0.05:
        return path

    fade_s = max(0.02, min(fade_ms / 1000.0, duration / 4.0))
    fade_out_start = max(0.0, duration - fade_s)
    suffix = path.suffix.lower() or ".mp3"
    # Keep ffmpeg outputs in OS temp so AV does not flag project-folder writes.
    scratch = Path(tempfile.gettempdir()) / "pixelle_video_ffmpeg"
    scratch.mkdir(parents=True, exist_ok=True)
    temporary = scratch / f"post-{uuid.uuid4().hex}{suffix}"

    try:
        stream = ffmpeg.input(str(path))
        audio = stream.audio
        # Single-pass loudnorm is good enough for cross-scene matching without 2-pass cost.
        audio = audio.filter("loudnorm", I=target_i, TP=true_peak, LRA=lra)
        audio = audio.filter("afade", t="in", st=0, d=fade_s)
        audio = audio.filter("afade", t="out", st=fade_out_start, d=fade_s)

        output_kwargs: dict = {"ac": 1, "ar": 44100}
        if suffix == ".wav":
            output_kwargs["acodec"] = "pcm_s16le"
        else:
            output_kwargs["acodec"] = "libmp3lame"
            output_kwargs["audio_bitrate"] = "192k"

        (
            ffmpeg.output(audio, str(temporary), **output_kwargs)
            .overwrite_output()
            .run(quiet=True, capture_stdout=True, capture_stderr=True)
        )
        if temporary.is_file() and temporary.stat().st_size > 0:
            shutil.move(str(temporary), str(path))
            logger.debug(
                "TTS post-process applied: path={} duration={:.2f}s fade={:.0f}ms",
                path.name,
                duration,
                fade_s * 1000,
            )
        else:
            logger.warning("TTS post-process produced empty file for {}", path)
    except Exception as exc:
        logger.warning("TTS post-process failed for {}: {}", path, exc)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)

    return path
