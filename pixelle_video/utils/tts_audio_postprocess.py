"""Lightweight post-processing for per-scene TTS clips.

Goal: reduce "different speaker" artifacts when clips are generated one-by-one:
- normalize loudness across scenes
- short fade in/out to soften hard cuts
"""

from __future__ import annotations

import subprocess
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


def _postprocess_timeout_seconds(duration: float) -> float:
    """Bound ffmpeg so a hung loudnorm cannot freeze generation forever."""
    # loudnorm is roughly linear; keep a generous floor/ceiling for long continuous tracks.
    return max(30.0, min(180.0, float(duration) * 2.5 + 20.0))


def postprocess_tts_clip(
    audio_path: str | Path,
    *,
    target_i: float = -16.0,
    true_peak: float = -1.5,
    lra: float = 11.0,
    fade_ms: int = 40,
    timeout_seconds: float | None = None,
) -> Path:
    """
    Normalize loudness and apply short fades in-place.

    Uses ffmpeg when available; on failure returns the original file unchanged.
    Always bounded by a timeout so a stuck ffmpeg cannot freeze the API event loop.
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
    from pixelle_video.utils.ffmpeg_scratch import ffmpeg_scratch_dir

    temporary = ffmpeg_scratch_dir() / f"post-{uuid.uuid4().hex}{suffix}"
    timeout = (
        float(timeout_seconds)
        if timeout_seconds is not None
        else _postprocess_timeout_seconds(duration)
    )

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

        # Compile + subprocess.run(timeout=...) instead of ffmpeg.run():
        # 1) avoids unbounded hangs that freeze the workbench generation run
        # 2) avoids rare pipe deadlocks when stderr buffers fill under capture
        cmd = (
            ffmpeg.output(audio, str(temporary), **output_kwargs)
            .overwrite_output()
            .compile()
        )
        completed = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or b"").decode("utf-8", errors="replace")[-500:]
            logger.warning(
                "TTS post-process ffmpeg failed for {} (code={}): {}",
                path,
                completed.returncode,
                stderr or "(no stderr)",
            )
            return path

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
    except subprocess.TimeoutExpired:
        logger.warning(
            "TTS post-process timed out after {:.0f}s for {} (duration={:.1f}s); keeping original",
            timeout,
            path,
            duration,
        )
    except Exception as exc:
        logger.warning("TTS post-process failed for {}: {}", path, exc)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)

    return path
