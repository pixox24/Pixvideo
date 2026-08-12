"""
Project config dual-key normalization (camelCase UI vs snake_case pipeline).

Product rule (P0):
- Editor writes camelCase (enableSubtitles, bgmVolume, mediaWidth, …).
- Readers must prefer camel when both casings exist (history imports leave snake keys).
- On write, dual-write both casings so all consumers stay consistent.
"""

from __future__ import annotations

from typing import Any

# (camel, snake) — camel is editor-owned / preferred when both present.
_CONFIG_KEY_PAIRS: tuple[tuple[str, str], ...] = (
    ("enableSubtitles", "subtitle_enabled"),
    ("enableMotion", "image_motion_enabled"),
    ("bgmVolume", "bgm_volume"),
    ("bgm", "bgm_path"),
    ("mediaWidth", "media_width"),
    ("mediaHeight", "media_height"),
    ("videoFps", "video_fps"),
    ("promptPrefix", "prompt_prefix"),
    ("ttsMode", "tts_inference_mode"),
    ("ttsDelivery", "tts_delivery"),
    ("voice", "tts_voice"),
    ("speed", "tts_speed"),
    ("minimaxModel", "minimax_model"),
    ("emotion", "minimax_emotion"),
    ("mimoModel", "mimo_model"),
    ("mimoStyle", "mimo_style"),
    ("subtitleStyle", "subtitle_style"),
    ("workflowId", "media_workflow"),
    ("bookendEnabled", "bookend_enabled"),
)


def pick_config(
    config: dict[str, Any] | None,
    *keys: str,
    default: Any = None,
) -> Any:
    """Return the first present non-None value among keys (order = priority)."""
    cfg = config or {}
    for key in keys:
        if key in cfg and cfg[key] is not None:
            return cfg[key]
    return default


def normalize_project_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """
    Dual-write known key pairs so camel and snake stay in sync.

    When both exist, camel wins (UI is source of truth after editor saves).
    """
    out = dict(config or {})
    for camel, snake in _CONFIG_KEY_PAIRS:
        if camel in out and out[camel] is not None:
            out[snake] = out[camel]
        elif snake in out and out[snake] is not None:
            out[camel] = out[snake]
    # Alias workflow → media_workflow / workflowId when only one form is present
    if "workflowId" not in out or out.get("workflowId") in (None, ""):
        workflow = out.get("workflow") or out.get("media_workflow")
        if workflow not in (None, ""):
            out["workflowId"] = workflow
            out.setdefault("media_workflow", workflow)
    elif out.get("workflowId") not in (None, ""):
        out.setdefault("media_workflow", out["workflowId"])
        out.setdefault("workflow", out["workflowId"])
    return out
