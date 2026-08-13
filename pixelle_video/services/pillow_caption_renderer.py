"""Pillow-based rounded caption overlays (hyperframes fallback, no new deps)."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from pixelle_video.services.subtitle_renderer import (
    DEFAULT_BOX_PADDING,
    DEFAULT_BOX_RADIUS,
    SubtitleRenderer,
    TimedCaptionSegment,
)


def _hex_to_rgba(value: Any, opacity_pct: int = 100) -> tuple[int, int, int, int]:
    text = str(value or "#000000").strip()
    if text.startswith("#"):
        text = text[1:]
    if len(text) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        text = "000000"
    red = int(text[0:2], 16)
    green = int(text[2:4], 16)
    blue = int(text[4:6], 16)
    alpha = int(round(255 * max(0, min(100, int(opacity_pct))) / 100))
    return red, green, blue, alpha


@dataclass(frozen=True)
class PillowCaptionOverlay:
    """One timed full-frame transparent PNG overlay."""

    path: str
    start: float
    end: float


class PillowCaptionRenderer:
    """
    Render per-cue full-canvas transparent PNGs with optional rounded caption boxes.

    Uses existing Pillow dependency only. Intended as a fallback when Hyperframes
    is unavailable, while still supporting rounded boxes that ASS cannot draw.
    """

    def __init__(self, subtitle_renderer: SubtitleRenderer | None = None):
        self.subtitle_renderer = subtitle_renderer or SubtitleRenderer()

    def render_overlays(
        self,
        text: str,
        duration: float,
        width: int,
        height: int,
        style: dict[str, Any] | None = None,
        alignment: list[Any] | None = None,
        output_dir: str | Path | None = None,
        font_path: str | None = None,
        *,
        hold_seconds: float = 0.0,
        audio_path: str | Path | None = None,
    ) -> list[PillowCaptionOverlay]:
        if duration <= 0:
            raise ValueError("Caption duration must be positive")
        if width <= 0 or height <= 0:
            raise ValueError("Caption canvas width and height must be positive")

        normalized = self.subtitle_renderer.normalize_style(style)
        hold = max(0.0, float(hold_seconds or 0.0))
        timed = self.subtitle_renderer.plan_segments(
            text,
            duration,
            normalized,
            alignment=alignment,
            hold_seconds=hold,
            audio_path=audio_path,
        )
        if not timed:
            raise ValueError("Caption text cannot be empty")

        workspace = Path(output_dir) if output_dir else Path(
            tempfile.mkdtemp(prefix="pixelle-pillow-captions-")
        )
        workspace.mkdir(parents=True, exist_ok=True)

        resolved_font = self._resolve_font_path(normalized, font_path)
        total_duration = float(duration) + hold
        overlays: list[PillowCaptionOverlay] = []
        for index, segment in enumerate(timed):
            end = float(segment.end)
            if index == len(timed) - 1:
                end = max(end, total_duration)
            path = workspace / f"caption-{index + 1:03d}.png"
            self._render_frame(
                path=path,
                text=segment.text,
                width=width,
                height=height,
                style=normalized,
                font_path=resolved_font,
            )
            overlays.append(
                PillowCaptionOverlay(
                    path=str(path),
                    start=max(0.0, float(segment.start)),
                    end=max(float(segment.start) + 0.05, end),
                )
            )
        return overlays

    def _resolve_font_path(
        self,
        style: dict[str, Any],
        font_path: str | None,
    ) -> str:
        candidates: list[str] = []
        if font_path:
            candidates.append(str(font_path))
        custom = str(style.get("fontPath") or "").strip()
        if custom:
            candidates.append(custom)
        for candidate in candidates:
            path = Path(candidate).expanduser()
            if path.is_file():
                return str(path)
        # Last resort: common system fonts (same spirit as VideoService._find_subtitle_font).
        for candidate in (
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
        ):
            if Path(candidate).is_file():
                return candidate
        raise RuntimeError("No usable font found for Pillow caption rendering")

    def _load_font(self, font_path: str, font_size: int):
        from PIL import ImageFont

        path = Path(font_path)
        last_error: Exception | None = None
        # TTC collections: try a few face indices.
        for index in range(0, 8):
            try:
                return ImageFont.truetype(str(path), size=font_size, index=index)
            except OSError as exc:
                last_error = exc
                if index == 0 and path.suffix.lower() != ".ttc":
                    break
                continue
        if last_error:
            raise RuntimeError(f"Failed to load font: {font_path}") from last_error
        return ImageFont.load_default()

    def _render_frame(
        self,
        path: Path,
        text: str,
        width: int,
        height: int,
        style: dict[str, Any],
        font_path: str,
    ) -> None:
        from PIL import Image, ImageDraw

        display = str(text or "").replace("\n", " ").strip()
        if not display:
            display = " "

        font_size = max(12, min(120, int(style.get("fontSize") or 52)))
        # Fit long lines roughly to maxCharsPerLine.
        max_chars = max(4, int(style.get("maxCharsPerLine") or 14))
        max_lines = max(1, int(style.get("maxLines") or 1))
        # Soft wrap for display: prefer existing newlines from plan_segments.
        lines = [line for line in str(text or "").split("\n") if line.strip()]
        if not lines:
            lines = [display]
        # If a single long line exceeds capacity, hard-wrap as last resort.
        wrapped: list[str] = []
        for line in lines:
            if len(line) <= max_chars:
                wrapped.append(line)
                continue
            for offset in range(0, len(line), max_chars):
                wrapped.append(line[offset : offset + max_chars])
                if len(wrapped) >= max_lines:
                    break
            if len(wrapped) >= max_lines:
                break
        lines = wrapped[:max_lines] or [display[:max_chars]]

        font = self._load_font(font_path, font_size)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        spacing = max(4, font_size // 6)
        # Measure multiline block.
        block = "\n".join(lines)
        bbox = draw.multiline_textbbox((0, 0), block, font=font, spacing=spacing, align="center")
        text_w = max(1, bbox[2] - bbox[0])
        text_h = max(1, bbox[3] - bbox[1])

        box_enabled = bool(style.get("boxEnabled")) or style.get("preset") == "caption-box"
        pad = max(
            0,
            int(style.get("boxPadding", style.get("outlineWidth", DEFAULT_BOX_PADDING)) or 0),
        )
        if box_enabled and pad <= 0:
            pad = DEFAULT_BOX_PADDING
        pad_x = max(6, int(round(pad * 0.9))) if box_enabled else 0
        pad_y = max(4, int(round(pad * 0.55))) if box_enabled else 0
        radius = max(0, int(style.get("boxRadius", DEFAULT_BOX_RADIUS) or 0))
        if box_enabled:
            radius = min(radius, max(pad_x, pad_y) * 2, max(4, font_size // 2))

        margin_v = max(0, int(style.get("marginV") or 120))
        # Alignment: ASS 1/4/7 left, 3/6/9 right, else center.
        alignment = int(style.get("alignment") or 2)
        box_w = text_w + pad_x * 2
        box_h = text_h + pad_y * 2
        if alignment in {1, 4, 7}:
            box_x = max(12, int(width * 0.067))
        elif alignment in {3, 6, 9}:
            box_x = min(width - box_w - 12, int(width * 0.933) - box_w)
        else:
            box_x = max(0, (width - box_w) // 2)
        box_y = max(0, height - box_h - margin_v)

        if box_enabled:
            fill = _hex_to_rgba(
                style.get("boxColor") or style.get("backColor") or "#000000",
                int(style.get("boxOpacity", style.get("backgroundOpacity", 72)) or 72),
            )
            rect = [box_x, box_y, box_x + box_w, box_y + box_h]
            if radius > 0:
                draw.rounded_rectangle(rect, radius=radius, fill=fill)
            else:
                draw.rectangle(rect, fill=fill)

        text_color = _hex_to_rgba(style.get("primaryColor") or "#FFFFFF", 100)
        stroke_w = 0 if box_enabled else max(0, int(style.get("strokeWidth", style.get("outlineWidth", 0)) or 0))
        stroke_fill = _hex_to_rgba(
            style.get("strokeColor") or style.get("outlineColor") or "#000000",
            100,
        )
        text_x = box_x + pad_x - bbox[0]
        text_y = box_y + pad_y - bbox[1]
        text_kwargs: dict[str, Any] = {
            "font": font,
            "fill": text_color,
            "spacing": spacing,
            "align": "center",
        }
        if stroke_w > 0:
            text_kwargs["stroke_width"] = stroke_w
            text_kwargs["stroke_fill"] = stroke_fill
        draw.multiline_text((text_x, text_y), block, **text_kwargs)
        overlay.save(path, format="PNG")


def should_use_pillow_captions(style: dict[str, Any] | None) -> bool:
    """True when rounded box captions should prefer Pillow over ASS.

    ASS BorderStyle=3 cannot draw rounded corners. When caption-box is enabled
    and boxRadius > 0 (default 12 after intent normalize), Pillow is preferred.
    Explicit boxRadius=0 keeps the fast ASS rectangular path.
    """
    if not style:
        return False
    box_enabled = bool(style.get("boxEnabled")) or style.get("preset") == "caption-box"
    if not box_enabled:
        return False
    try:
        radius = int(style.get("boxRadius") or 0)
    except (TypeError, ValueError):
        radius = 0
    return radius > 0
