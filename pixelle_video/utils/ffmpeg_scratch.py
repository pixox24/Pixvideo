"""Shared ffmpeg / TTS temp directory helpers and GC."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from loguru import logger

SCRATCH_DIR_NAME = "pixelle_video_ffmpeg"


def ffmpeg_scratch_dir() -> Path:
    root = Path(tempfile.gettempdir()) / SCRATCH_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def cleanup_ffmpeg_scratch(*, max_age_hours: float = 24.0) -> int:
    """
    Delete files under the shared ffmpeg scratch older than max_age_hours.

    Called on API startup (Day3). Returns number of paths removed.
    """
    root = Path(tempfile.gettempdir()) / SCRATCH_DIR_NAME
    if not root.is_dir():
        return 0
    cutoff = time.time() - max(1.0, float(max_age_hours)) * 3600.0
    removed = 0
    try:
        for path in root.rglob("*"):
            try:
                if not path.is_file():
                    continue
                if path.stat().st_mtime >= cutoff:
                    continue
                path.unlink(missing_ok=True)
                removed += 1
            except OSError:
                continue
        # Remove empty subdirs (best-effort)
        for path in sorted(root.rglob("*"), reverse=True):
            try:
                if path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
            except OSError:
                continue
    except OSError as exc:
        logger.debug("ffmpeg scratch cleanup failed: {}", exc)
        return removed
    if removed:
        logger.info(
            "Cleaned {} stale file(s) from ffmpeg scratch (>{:.0f}h): {}",
            removed,
            max_age_hours,
            root,
        )
    return removed
