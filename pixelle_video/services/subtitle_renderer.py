from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any


SUBTITLE_STYLE_DEFAULTS: dict[str, Any] = {
    "mode": "ass",
    "preset": "short-video-bold",
    "fontFamily": "",
    "fontPath": "",
    "fontSize": 52,
    "primaryColor": "#FFFFFF",
    "accentColor": "#FFD43B",
    "outlineColor": "#000000",
    "backColor": "#000000",
    "outlineWidth": 3,
    "shadow": 0,
    "marginV": 120,
    "alignment": 2,
    "maxCharsPerLine": 14,
    "maxLines": 2,
    "animation": "fade",
    "segmentMode": "phrase",
}


class SubtitleRenderer:
    """Create styled ASS subtitle files for FFmpeg burn-in."""

    def normalize_style(self, style: dict[str, Any] | None) -> dict[str, Any]:
        normalized = {**SUBTITLE_STYLE_DEFAULTS, **(style or {})}
        normalized["fontSize"] = self._coerce_int(normalized.get("fontSize"), 52, 12, 120)
        normalized["outlineWidth"] = self._coerce_int(normalized.get("outlineWidth"), 3, 0, 12)
        normalized["shadow"] = self._coerce_int(normalized.get("shadow"), 0, 0, 12)
        normalized["marginV"] = self._coerce_int(normalized.get("marginV"), 120, 0, 600)
        normalized["alignment"] = self._coerce_int(normalized.get("alignment"), 2, 1, 9)
        normalized["maxCharsPerLine"] = self._coerce_int(
            normalized.get("maxCharsPerLine"),
            14,
            4,
            40,
        )
        normalized["maxLines"] = self._coerce_int(normalized.get("maxLines"), 2, 1, 4)
        normalized["animation"] = "fade" if normalized.get("animation") == "fade" else "none"
        if normalized.get("segmentMode") not in {"line", "sentence", "phrase"}:
            normalized["segmentMode"] = "phrase"
        return normalized

    def _coerce_int(self, value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return min(max(number, minimum), maximum)

    def hex_to_ass_color(self, value: str) -> str:
        color = str(value or "#FFFFFF").strip().lstrip("#")
        if len(color) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", color):
            color = "FFFFFF"
        rr, gg, bb = color[0:2], color[2:4], color[4:6]
        return f"&H00{bb.upper()}{gg.upper()}{rr.upper()}"

    def escape_ass_text(self, text: str) -> str:
        return (
            str(text or "")
            .replace("\\", r"\\")
            .replace("{", r"\{")
            .replace("}", r"\}")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\n", r"\N")
        )

    def segment_text(self, text: str, mode: str, max_chars: int, max_lines: int) -> list[str]:
        cleaned = " ".join(str(text or "").split())
        if not cleaned:
            return []

        if mode == "line":
            raw_segments = [line.strip() for line in str(text).splitlines() if line.strip()]
        elif mode == "sentence":
            raw_segments = [
                part.strip()
                for part in re.split(r"(?<=[。！？!?\.])", cleaned)
                if part.strip()
            ]
        else:
            segment_length = max_chars * max_lines
            raw_segments = [
                cleaned[index : index + segment_length]
                for index in range(0, len(cleaned), segment_length)
            ]

        return [
            self.wrap_text(segment, max_chars, max_lines)
            for segment in raw_segments
            if segment
        ]

    def wrap_text(self, text: str, max_chars: int, max_lines: int) -> str:
        lines: list[str] = []
        current = ""
        for char in str(text or ""):
            if len(current) >= max_chars:
                lines.append(current)
                current = char
                if len(lines) >= max_lines:
                    break
            else:
                current += char
        if len(lines) < max_lines and current:
            lines.append(current)
        return "\n".join(lines[:max_lines])

    def format_time(self, seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        whole_seconds = int(seconds % 60)
        centiseconds = int(round((seconds - int(seconds)) * 100))
        if centiseconds >= 100:
            whole_seconds += 1
            centiseconds = 0
        return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"

    def _font_name(self, style: dict[str, Any]) -> str:
        font_family = str(style.get("fontFamily") or "").strip()
        if font_family:
            return font_family
        font_path = str(style.get("fontPath") or "").strip()
        if font_path:
            return Path(font_path).stem
        return "PingFang SC"

    def create_ass_file(
        self,
        text: str,
        duration: float,
        width: int,
        height: int,
        style: dict[str, Any] | None = None,
        output_dir: str | Path | None = None,
    ) -> str:
        normalized = self.normalize_style(style)
        font_name = self._font_name(normalized)
        max_chars = normalized["maxCharsPerLine"]
        max_lines = normalized["maxLines"]
        segments = self.segment_text(
            text,
            normalized["segmentMode"],
            max_chars,
            max_lines,
        )
        if not segments:
            segments = [self.wrap_text(text, max_chars, max_lines)]

        segment_duration = max(0.3, float(duration) / max(len(segments), 1))
        fade_tag = r"{\fad(120,120)}" if normalized["animation"] == "fade" else ""
        events: list[str] = []
        cursor = 0.0
        for segment in segments:
            start = cursor
            end = min(float(duration), cursor + segment_duration)
            cursor = end
            escaped = self.escape_ass_text(segment)
            events.append(
                "Dialogue: "
                f"0,{self.format_time(start)},{self.format_time(end)},"
                f"Default,,0,0,0,,{fade_tag}{escaped}"
            )

        ass = "\n".join(
            [
                "[Script Info]",
                "ScriptType: v4.00+",
                f"PlayResX: {width}",
                f"PlayResY: {height}",
                "ScaledBorderAndShadow: yes",
                "",
                "[V4+ Styles]",
                "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
                "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
                "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
                "Alignment,MarginL,MarginR,MarginV,Encoding",
                "Style: Default,"
                f"{font_name},{normalized['fontSize']},"
                f"{self.hex_to_ass_color(normalized['primaryColor'])},"
                f"{self.hex_to_ass_color(normalized['accentColor'])},"
                f"{self.hex_to_ass_color(normalized['outlineColor'])},"
                f"{self.hex_to_ass_color(normalized['backColor'])},"
                "1,0,0,0,100,100,0,0,1,"
                f"{normalized['outlineWidth']},{normalized['shadow']},"
                f"{normalized['alignment']},60,60,{normalized['marginV']},1",
                "",
                "[Events]",
                "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
                *events,
                "",
            ]
        )

        if output_dir is None:
            file = tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".ass",
                mode="w",
                encoding="utf-8",
            )
            with file:
                file.write(ass)
            return file.name

        output_path = Path(output_dir) / "subtitles.ass"
        output_path.write_text(ass, encoding="utf-8")
        return str(output_path)
