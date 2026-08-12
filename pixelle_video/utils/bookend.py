"""Project-level intro/outro bookend packaging defaults and normalization."""

from __future__ import annotations

from typing import Any


# Product defaults (see design: 片头 1.2s / 片尾 2.0s, fades nested inside).
DEFAULT_BOOKEND = {
    "enabled": True,
    "intro_seconds": 1.2,
    "outro_seconds": 2.0,
    "intro_fade_seconds": 0.6,
    "outro_fade_seconds": 1.0,
}


def _to_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return number


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def normalize_bookend_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Normalize project/export config into a canonical bookend dict.

    Accepts camelCase (frontend) and snake_case (backend) keys.
    Outro is additive with per-scene manual hold (hold stays on scenes; outro is extra).
    """
    cfg = config or {}

    if "bookendEnabled" in cfg or "bookend_enabled" in cfg:
        enabled_raw = cfg.get("bookendEnabled", cfg.get("bookend_enabled"))
    else:
        # Nested object support: config.bookend = { enabled, ... }
        nested = cfg.get("bookend") if isinstance(cfg.get("bookend"), dict) else {}
        enabled_raw = nested.get("enabled", DEFAULT_BOOKEND["enabled"])
        cfg = {**nested, **cfg}

    if isinstance(enabled_raw, str):
        enabled = enabled_raw.strip().lower() not in {"0", "false", "no", "off", ""}
    else:
        enabled = bool(enabled_raw) if enabled_raw is not None else True

    intro = _clamp(
        _to_float(
            cfg.get("bookendIntroSeconds", cfg.get("intro_seconds", cfg.get("introSeconds"))),
            DEFAULT_BOOKEND["intro_seconds"],
        ),
        0.0,
        5.0,
    )
    outro = _clamp(
        _to_float(
            cfg.get("bookendOutroSeconds", cfg.get("outro_seconds", cfg.get("outroSeconds"))),
            DEFAULT_BOOKEND["outro_seconds"],
        ),
        0.0,
        6.0,
    )
    intro_fade = _clamp(
        _to_float(
            cfg.get(
                "bookendIntroFadeSeconds",
                cfg.get("intro_fade_seconds", cfg.get("introFadeSeconds")),
            ),
            DEFAULT_BOOKEND["intro_fade_seconds"],
        ),
        0.0,
        3.0,
    )
    outro_fade = _clamp(
        _to_float(
            cfg.get(
                "bookendOutroFadeSeconds",
                cfg.get("outro_fade_seconds", cfg.get("outroFadeSeconds")),
            ),
            DEFAULT_BOOKEND["outro_fade_seconds"],
        ),
        0.0,
        4.0,
    )

    # Fades cannot exceed pad durations.
    if intro > 0:
        intro_fade = min(intro_fade, intro)
    else:
        intro_fade = 0.0
    if outro > 0:
        outro_fade = min(outro_fade, outro)
    else:
        outro_fade = 0.0

    if not enabled:
        intro = outro = intro_fade = outro_fade = 0.0

    return {
        "enabled": enabled and (intro > 0 or outro > 0),
        "intro_seconds": round(intro, 3),
        "outro_seconds": round(outro, 3),
        "intro_fade_seconds": round(intro_fade, 3),
        "outro_fade_seconds": round(outro_fade, 3),
    }
