"""
Video canvas (成片规格) vs image-generation size mapping.

Product decisions:
1. Default video canvas: 1080×1920 @ 30fps
2. 1440×2560 retained as advanced/slow
3. Image gen always maps to an API whitelist size (not strict follow)
"""

from __future__ import annotations

from typing import Any


# --- Video canvas presets (成片) -------------------------------------------------

DEFAULT_VIDEO_WIDTH = 1080
DEFAULT_VIDEO_HEIGHT = 1920
DEFAULT_VIDEO_FPS = 30

VIDEO_CANVAS_PRESETS: list[dict[str, Any]] = [
    {
        "id": "1080x1920",
        "label": "竖屏 1080p（推荐）",
        "aspect": "9:16",
        "width": 1080,
        "height": 1920,
        "tier": "recommended",
        "hint": "默认成片规格，导出更稳",
    },
    {
        "id": "720x1280",
        "label": "竖屏 720p（更快）",
        "aspect": "9:16",
        "width": 720,
        "height": 1280,
        "tier": "fast",
        "hint": "初稿/试片更快",
    },
    {
        "id": "1440x2560",
        "label": "竖屏 1440p（高级/慢）",
        "aspect": "9:16",
        "width": 1440,
        "height": 2560,
        "tier": "advanced",
        "hint": "更清晰，导出明显更慢且更易失败",
    },
    {
        "id": "1920x1080",
        "label": "横屏 1080p",
        "aspect": "16:9",
        "width": 1920,
        "height": 1080,
        "tier": "recommended",
        "hint": "横版成片",
    },
    {
        "id": "1280x720",
        "label": "横屏 720p（更快）",
        "aspect": "16:9",
        "width": 1280,
        "height": 720,
        "tier": "fast",
        "hint": "横版试片",
    },
    {
        "id": "2560x1440",
        "label": "横屏 1440p（高级/慢）",
        "aspect": "16:9",
        "width": 2560,
        "height": 1440,
        "tier": "advanced",
        "hint": "横版高清，导出更慢",
    },
    {
        "id": "1080x1080",
        "label": "方形 1080",
        "aspect": "1:1",
        "width": 1080,
        "height": 1080,
        "tier": "recommended",
        "hint": "1:1 成片",
    },
    {
        "id": "1024x1024",
        "label": "方形 1024",
        "aspect": "1:1",
        "width": 1024,
        "height": 1024,
        "tier": "fast",
        "hint": "接近生图常用方图",
    },
]


# --- Image API whitelist (生图) -------------------------------------------------

# Common OpenAI-compatible / multi-provider friendly sizes.
IMAGE_GEN_WHITELIST: list[tuple[int, int]] = [
    (1024, 1024),
    (1024, 1536),  # portrait ~2:3
    (1536, 1024),  # landscape ~3:2
    (1080, 1920),  # portrait 9:16 (if provider accepts)
    (1920, 1080),  # landscape 16:9
    (720, 1280),
    (1280, 720),
]


def _to_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def normalize_video_canvas(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Resolve video canvas (export/storyboard media size + fps) from project config.
    Defaults to 1080×1920@30.
    """
    cfg = config or {}
    width = _to_int(cfg.get("mediaWidth", cfg.get("media_width")), DEFAULT_VIDEO_WIDTH)
    height = _to_int(cfg.get("mediaHeight", cfg.get("media_height")), DEFAULT_VIDEO_HEIGHT)
    fps = _to_int(cfg.get("videoFps", cfg.get("video_fps")), DEFAULT_VIDEO_FPS)
    fps = max(12, min(60, fps))

    # Snap to known preset id when exact match
    preset_id = f"{width}x{height}"
    known = {p["id"] for p in VIDEO_CANVAS_PRESETS}
    if preset_id not in known:
        # Keep custom sizes but clamp extremes
        width = max(480, min(3840, width))
        height = max(480, min(3840, height))
        # Prefer even dimensions for yuv420
        width -= width % 2
        height -= height % 2

    tier = "custom"
    for preset in VIDEO_CANVAS_PRESETS:
        if preset["width"] == width and preset["height"] == height:
            tier = str(preset.get("tier") or "custom")
            break

    return {
        "width": width,
        "height": height,
        "fps": fps,
        "preset_id": f"{width}x{height}",
        "tier": tier,
        "is_advanced": tier == "advanced",
    }


def map_image_gen_size(video_width: int, video_height: int) -> tuple[int, int]:
    """
    Map a video canvas size to the closest API whitelist size.

    Prefer same orientation, then closest aspect ratio, then closer pixel count.
    """
    vw = max(1, int(video_width or DEFAULT_VIDEO_WIDTH))
    vh = max(1, int(video_height or DEFAULT_VIDEO_HEIGHT))
    target_aspect = vw / vh
    target_pixels = vw * vh
    portrait = vh >= vw

    # Exact whitelist hit
    for w, h in IMAGE_GEN_WHITELIST:
        if w == vw and h == vh:
            return w, h

    candidates = list(IMAGE_GEN_WHITELIST)
    # Prefer same orientation
    oriented = [(w, h) for w, h in candidates if (h >= w) == portrait]
    pool = oriented or candidates

    def score(size: tuple[int, int]) -> tuple[float, float, float]:
        w, h = size
        aspect = w / h
        aspect_delta = abs(aspect - target_aspect)
        pixel_delta = abs(w * h - target_pixels) / max(target_pixels, 1)
        # Prefer not hugely smaller than target when possible
        undersize_penalty = 0.0 if w * h >= target_pixels * 0.45 else 1.0
        return (aspect_delta, undersize_penalty, pixel_delta)

    best = min(pool, key=score)
    return int(best[0]), int(best[1])


def image_gen_size_from_config(config: dict[str, Any] | None = None) -> tuple[int, int]:
    canvas = normalize_video_canvas(config)
    return map_image_gen_size(canvas["width"], canvas["height"])


def resolve_video_fps(config: dict[str, Any] | None = None) -> int:
    return int(normalize_video_canvas(config)["fps"])
