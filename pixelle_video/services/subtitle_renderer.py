from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Punctuation used as split points for "one cue per phrase" (not shown on screen).
# Includes terminal marks and Chinese/English pauses so e.g.
# "有人说，AI会取代人类。" → ["有人说", "AI会取代人类"]
_SPLIT_PUNCT_CLASS = r"。！？!?\.…，,、；;：:"
_TRAILING_PUNCT_RE = re.compile(rf"[{_SPLIT_PUNCT_CLASS}\s]+$")
_LEADING_PUNCT_RE = re.compile(rf"^[{_SPLIT_PUNCT_CLASS}\s]+")
# Extract non-punctuation runs (sentence mode).
_SENTENCE_PARTS_RE = re.compile(rf"[^{_SPLIT_PUNCT_CLASS}\s]+")
# Soft break only for phrase mode oversize handling.
_SOFT_BREAK_RE = re.compile(r"(?<=[，,、；;])")

SUBTITLE_STYLE_DEFAULTS: dict[str, Any] = {
    "mode": "ass",
    "preset": "short-video-bold",
    "fontFamily": "",
    "fontPath": "",
    "fontSize": 80,
    "primaryColor": "#FFFFFF",
    "accentColor": "#F97316",
    "outlineColor": "#000000",
    "backColor": "#000000",
    "outlineWidth": 0,
    "shadow": 0,
    "marginV": 200,
    "alignment": 2,
    "maxCharsPerLine": 20,
    "maxLines": 1,
    "animation": "fade",
    "segmentMode": "sentence",
    "highlightWords": [],
    "keywordColors": {},
    "highlightStyle": "accent",
    "highlightScale": 125,
    "backgroundOpacity": 72,
    "fadeInMs": 120,
    "fadeOutMs": 120,
}

# Presets provide defaults only. Values explicitly supplied by the caller are
# merged after these values so manual controls always win.
SUBTITLE_PRESET_DEFAULTS: dict[str, dict[str, Any]] = {
    "short-video-bold": {
        "fontSize": 56,
        "primaryColor": "#FFFFFF",
        "accentColor": "#FFD43B",
        "outlineColor": "#000000",
        "outlineWidth": 4,
        "shadow": 1,
        "marginV": 120,
        "maxLines": 2,
        "animation": "fade",
    },
    "clean-white": {
        "fontSize": 52,
        "primaryColor": "#FFFFFF",
        "accentColor": "#FFFFFF",
        "outlineColor": "#000000",
        "outlineWidth": 1,
        "shadow": 0,
        "marginV": 120,
        "maxLines": 2,
        "animation": "fade",
    },
    "cinema-soft": {
        "fontSize": 52,
        "primaryColor": "#FFF7ED",
        "accentColor": "#FBBF24",
        "outlineColor": "#3F2A1D",
        "outlineWidth": 2,
        "shadow": 2,
        "marginV": 140,
        "maxLines": 2,
        "animation": "fade",
    },
    "caption-box": {
        "fontSize": 80,
        "primaryColor": "#FFFFFF",
        "accentColor": "#F97316",
        "outlineColor": "#000000",
        "backColor": "#000000",
        "outlineWidth": 0,
        "shadow": 0,
        "marginV": 200,
        "maxLines": 1,
        "backgroundOpacity": 72,
        "animation": "fade",
    },
}


@dataclass(frozen=True)
class TimedCaptionSegment:
    """One timed subtitle segment used by ASS and dynamic renderers."""

    text: str
    start: float
    end: float
    weight: int


class SubtitleRenderer:
    """Plan and burn-in styled ASS subtitles for FFmpeg."""

    def normalize_style(self, style: dict[str, Any] | None) -> dict[str, Any]:
        raw_style = style or {}
        preset = str(raw_style.get("preset") or SUBTITLE_STYLE_DEFAULTS["preset"])
        if preset not in SUBTITLE_PRESET_DEFAULTS:
            preset = SUBTITLE_STYLE_DEFAULTS["preset"]
        normalized = {
            **SUBTITLE_STYLE_DEFAULTS,
            **SUBTITLE_PRESET_DEFAULTS[preset],
            **raw_style,
            "preset": preset,
        }
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
        if normalized.get("mode") not in {"drawtext", "ass", "hyperframes"}:
            normalized["mode"] = "ass"
        raw_animation = normalized.get("animation")
        if normalized["mode"] == "hyperframes":
            normalized["animation"] = (
                raw_animation if raw_animation in {"fade", "pop", "word-pop", "none"} else "fade"
            )
        else:
            # ASS burn-in only supports fade/none; map pop variants to fade.
            if raw_animation == "none":
                normalized["animation"] = "none"
            elif raw_animation in {"fade", "pop", "word-pop", None, ""}:
                normalized["animation"] = "fade"
            else:
                normalized["animation"] = "none"

        if normalized.get("segmentMode") not in {"line", "sentence", "phrase"}:
            normalized["segmentMode"] = "sentence"
        raw_words = normalized.get("highlightWords")
        if isinstance(raw_words, str):
            raw_words = [raw_words]
        if not isinstance(raw_words, (list, tuple, set)):
            raw_words = []
        highlight_words: list[str] = []
        seen_words: set[str] = set()
        for raw_word in raw_words:
            word = " ".join(str(raw_word or "").split())[:40]
            key = word.casefold()
            if word and key not in seen_words:
                highlight_words.append(word)
                seen_words.add(key)
            if len(highlight_words) == 24:
                break
        normalized["highlightWords"] = highlight_words

        keyword_colors: dict[str, str] = {}
        raw_colors = normalized.get("keywordColors")
        if isinstance(raw_colors, dict):
            for raw_key, raw_color in raw_colors.items():
                key = " ".join(str(raw_key or "").split())[:40]
                if not key:
                    continue
                color = self._normalize_hex_color(raw_color, "")
                if color:
                    keyword_colors[key] = color
                if len(keyword_colors) == 24:
                    break
        normalized["keywordColors"] = keyword_colors

        if normalized.get("highlightStyle") not in {"accent", "pop", "badge"}:
            normalized["highlightStyle"] = "accent"
        normalized["highlightScale"] = self._coerce_int(
            normalized.get("highlightScale"),
            125,
            100,
            180,
        )
        normalized["backgroundOpacity"] = self._coerce_int(
            normalized.get("backgroundOpacity"),
            72,
            0,
            100,
        )
        normalized["fadeInMs"] = self._coerce_int(normalized.get("fadeInMs"), 120, 0, 1000)
        normalized["fadeOutMs"] = self._coerce_int(normalized.get("fadeOutMs"), 120, 0, 1000)
        return normalized

    def _coerce_int(self, value: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return min(max(number, minimum), maximum)

    @staticmethod
    def _normalize_hex_color(value: Any, default: str = "#FFFFFF") -> str:
        candidate = str(value or "").strip()
        if candidate.startswith("#"):
            body = candidate[1:]
        else:
            body = candidate
        if len(body) == 6 and re.fullmatch(r"[0-9a-fA-F]{6}", body):
            return f"#{body.upper()}"
        return default

    def hex_to_ass_color(self, value: str, alpha: int = 0) -> str:
        color = self._normalize_hex_color(value, "#FFFFFF").lstrip("#")
        rr, gg, bb = color[0:2], color[2:4], color[4:6]
        ass_alpha = min(255, max(0, int(alpha)))
        return f"&H{ass_alpha:02X}{bb}{gg}{rr}"

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

    @staticmethod
    def strip_display_punctuation(text: str) -> str:
        """Remove leading/trailing punctuation used as split points (not shown on screen)."""
        cleaned = str(text or "").strip()
        cleaned = _LEADING_PUNCT_RE.sub("", cleaned)
        cleaned = _TRAILING_PUNCT_RE.sub("", cleaned)
        return cleaned.strip()

    @staticmethod
    def effective_weight(text: str) -> int:
        """Character weight for proportional timing (ignore whitespace and common punctuation)."""
        compact = re.sub(r"[\s。！？!?\.…,，、；;：:]+", "", str(text or ""))
        return max(1, len(compact)) if compact else max(1, len(str(text or "").strip()) or 1)

    def split_raw_segments(self, text: str, mode: str) -> list[str]:
        """Split source text into display segments (punctuation is never kept)."""
        if mode == "line":
            raw_segments = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        elif mode == "sentence":
            cleaned = " ".join(str(text or "").split())
            if not cleaned:
                return []
            # One cue per punctuation-bounded phrase; never hard-cut mid-phrase.
            raw_segments = [part.strip() for part in _SENTENCE_PARTS_RE.findall(cleaned) if part.strip()]
        else:
            cleaned = " ".join(str(text or "").split())
            raw_segments = [cleaned] if cleaned else []

        display_segments: list[str] = []
        for segment in raw_segments:
            display = self.strip_display_punctuation(segment)
            if display:
                display_segments.append(display)
        return display_segments

    def _split_overlong_segment(self, text: str, capacity: int) -> list[str]:
        """Break long text at soft punctuation when possible; last resort keeps the whole piece."""
        cleaned = self.strip_display_punctuation(text)
        if not cleaned:
            return []
        if len(cleaned) <= capacity:
            return [cleaned]

        soft_parts = [part for part in _SOFT_BREAK_RE.split(cleaned) if part]
        if len(soft_parts) <= 1:
            # No soft punctuation left — keep intact rather than inventing a mid-phrase cut here.
            # Callers may still apply hard capacity cuts as a final fallback.
            return [cleaned]

        chunks: list[str] = []
        current = ""
        for part in soft_parts:
            candidate = current + part
            if current and len(self.strip_display_punctuation(candidate)) > capacity:
                piece = self.strip_display_punctuation(current)
                if piece:
                    chunks.append(piece)
                current = part
            else:
                current = candidate
        piece = self.strip_display_punctuation(current)
        if piece:
            chunks.append(piece)
        return chunks or [cleaned]

    def _expand_phrase_segments(
        self,
        text: str,
        capacity: int,
        highlight_words: list[str] | None = None,
    ) -> list[str]:
        """
        Phrase mode: prefer punctuation-bounded phrases, then soft commas, then capacity.

        Fixed character packing alone produces mid-sentence cuts such as
        「后半生该|找回真正的自己」. Natural Chinese short-video captions should
        break at ，。！？ first.
        """
        words = list(highlight_words or [])
        # 1) Atomic phrases by the same punctuation class as sentence mode.
        atomic = self.split_raw_segments(text, "sentence")
        if not atomic:
            cleaned = " ".join(str(text or "").split())
            cleaned = self.strip_display_punctuation(cleaned)
            atomic = [cleaned] if cleaned else []

        expanded: list[str] = []
        for phrase in atomic:
            if len(phrase) <= capacity:
                expanded.append(phrase)
                continue
            # 2) Soft punctuation packing inside an overlong phrase.
            soft_chunks = self._split_overlong_segment(phrase, capacity)
            for chunk in soft_chunks:
                if len(chunk) <= capacity:
                    expanded.append(chunk)
                else:
                    # 3) Last resort: hard capacity (keeps highlight tokens intact when possible).
                    expanded.extend(self._split_by_capacity(chunk, capacity, words))
        return [segment for segment in expanded if segment]

    def _highlight_tokens(self, text: str, highlight_words: list[str]) -> list[str]:
        words = sorted(
            {str(word).strip() for word in highlight_words if str(word).strip()},
            key=len,
            reverse=True,
        )
        if not words:
            return list(text)
        matcher = re.compile(
            "(" + "|".join(re.escape(word) for word in words) + ")",
            flags=re.IGNORECASE,
        )
        highlight_keys = {word.casefold() for word in words}
        tokens: list[str] = []
        for fragment in matcher.split(text):
            if not fragment:
                continue
            if fragment.casefold() in highlight_keys:
                tokens.append(fragment)
            else:
                tokens.extend(fragment)
        return tokens

    def _split_by_capacity(
        self,
        text: str,
        capacity: int,
        highlight_words: list[str] | None = None,
    ) -> list[str]:
        """Split text into capacity-sized chunks, keeping highlight words intact when possible."""
        cleaned = self.strip_display_punctuation(text) if text else ""
        if not cleaned:
            return []
        if len(cleaned) <= capacity:
            return [cleaned]

        tokens = (
            self._highlight_tokens(cleaned, highlight_words or [])
            if highlight_words
            else list(cleaned)
        )
        segments: list[str] = []
        current = ""
        for token in tokens:
            if current and len(current) + len(token) > capacity:
                segments.append(current)
                current = token if len(token) <= capacity else ""
                if len(token) > capacity:
                    # Hard-cut an oversized token as a last resort.
                    for index in range(0, len(token), capacity):
                        piece = token[index : index + capacity]
                        if index == 0 and not segments:
                            current = piece
                        else:
                            if current:
                                segments.append(current)
                            current = piece
            else:
                current += token
        if current:
            segments.append(current)
        return segments

    def segment_text(
        self,
        text: str,
        mode: str,
        max_chars: int,
        max_lines: int,
        highlight_words: list[str] | None = None,
    ) -> list[str]:
        capacity = max(1, max_chars * max_lines)
        words = list(highlight_words or [])

        if mode == "phrase":
            expanded = self._expand_phrase_segments(text, capacity, words)
            # Multi-line wrap is display-only; each cue already prefers punctuation.
            if words:
                return [
                    self._wrap_with_highlights(segment, max_chars, max_lines, words)
                    for segment in expanded
                    if segment
                ]
            return [
                self.wrap_text(segment, max_chars, max_lines)
                for segment in expanded
                if segment
            ]

        # sentence / line: one cue = one line, never force-cut mid-phrase by capacity.
        expanded = self.split_raw_segments(text, mode)
        if mode == "line" and capacity:
            # Line mode still respects explicit newlines only; no mid-line capacity cut.
            pass
        # Return single-line cues (no wrap_text truncation).
        return [segment.replace("\n", "").strip() for segment in expanded if segment.strip()]

    def _wrap_with_highlights(
        self,
        text: str,
        max_chars: int,
        max_lines: int,
        highlight_words: list[str],
    ) -> str:
        tokens = self._highlight_tokens(text, highlight_words)
        lines: list[str] = []
        current = ""
        for token in tokens:
            if current and len(current) + len(token) > max_chars:
                lines.append(current)
                current = token
                if len(lines) >= max_lines:
                    break
            else:
                current += token
        if len(lines) < max_lines and current:
            lines.append(current)
        return "\n".join(lines[:max_lines])

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

    def plan_segments(
        self,
        text: str,
        duration: float,
        style: dict[str, Any] | None = None,
        alignment: list[Any] | None = None,
    ) -> list[TimedCaptionSegment]:
        """Build timed segments.

        Prefer TTS alignment cues when available; otherwise fall back to
        proportional character-weight timing.
        """
        from pixelle_video.services.subtitle_alignment import (
            AlignmentCue,
            map_segments_to_alignment,
            parse_alignment_payload,
        )

        normalized = self.normalize_style(style)
        max_chars = normalized["maxCharsPerLine"]
        max_lines = normalized["maxLines"]
        segments = self.segment_text(
            text,
            normalized["segmentMode"],
            max_chars,
            max_lines,
            highlight_words=normalized.get("highlightWords") or [],
        )
        if not segments:
            fallback = self.wrap_text(
                self.strip_display_punctuation(text) or str(text or "").strip(),
                max_chars,
                max_lines,
            )
            segments = [fallback] if fallback else []
        if not segments:
            return []

        total_duration = max(0.05, float(duration))
        weights = [self.effective_weight(segment) for segment in segments]

        cues: list[AlignmentCue] = []
        if alignment:
            if all(isinstance(item, AlignmentCue) for item in alignment):
                cues = list(alignment)  # type: ignore[arg-type]
            else:
                cues = parse_alignment_payload(alignment)

        aligned_times = map_segments_to_alignment(segments, cues, total_duration) if cues else None
        if aligned_times and len(aligned_times) == len(segments):
            return [
                TimedCaptionSegment(
                    text=segment,
                    start=start,
                    end=end,
                    weight=weight,
                )
                for segment, (start, end), weight in zip(segments, aligned_times, weights)
            ]

        total_weight = sum(weights) or len(segments)
        timed: list[TimedCaptionSegment] = []
        cursor = 0.0
        min_segment = min(0.3, total_duration / max(len(segments), 1))
        for index, (segment, weight) in enumerate(zip(segments, weights)):
            if index == len(segments) - 1:
                end = total_duration
            else:
                share = total_duration * (weight / total_weight)
                end = min(total_duration, cursor + max(min_segment, share))
            start = cursor
            if end <= start:
                end = min(total_duration, start + min_segment)
            timed.append(
                TimedCaptionSegment(
                    text=segment,
                    start=start,
                    end=end,
                    weight=weight,
                )
            )
            cursor = end
        if timed:
            last = timed[-1]
            timed[-1] = TimedCaptionSegment(
                text=last.text,
                start=last.start,
                end=total_duration,
                weight=last.weight,
            )
        return timed

    def create_ass_file(
        self,
        text: str,
        duration: float,
        width: int,
        height: int,
        style: dict[str, Any] | None = None,
        output_dir: str | Path | None = None,
        alignment: list[Any] | None = None,
    ) -> str:
        normalized = self.normalize_style(style)
        font_name = self._font_name(normalized)
        timed_segments = self.plan_segments(text, duration, normalized, alignment=alignment)
        if not timed_segments:
            timed_segments = [
                TimedCaptionSegment(
                    text=self.wrap_text(text, normalized["maxCharsPerLine"], normalized["maxLines"]),
                    start=0.0,
                    end=max(0.05, float(duration)),
                    weight=1,
                )
            ]

        # Soft glow via ASS blur; keep hard Shadow at 0 to avoid double-ghost offset.
        blur_amount = self._blur_amount(normalized.get("shadow", 0))
        style_shadow = 0
        events: list[str] = []
        for segment in timed_segments:
            tags = self._dialogue_prefix_tags(normalized, segment.end - segment.start, blur_amount)
            body = self.apply_ass_highlights(segment.text, normalized)
            events.append(
                "Dialogue: "
                f"0,{self.format_time(segment.start)},{self.format_time(segment.end)},"
                f"Default,,0,0,0,,{tags}{body}"
            )

        # Escape commas in font name for ASS style line safety.
        safe_font = str(font_name).replace(",", " ")
        is_caption_box = normalized["preset"] == "caption-box"
        background_opacity = normalized.get("backgroundOpacity", 72)
        background_alpha = round(255 * (1 - (int(background_opacity) / 100)))
        border_style = 3 if is_caption_box else 1
        bold = 1 if normalized["preset"] == "short-video-bold" else 0
        ass = "\n".join(
            [
                "[Script Info]",
                "ScriptType: v4.00+",
                f"PlayResX: {width}",
                f"PlayResY: {height}",
                "ScaledBorderAndShadow: yes",
                "WrapStyle: 2",
                "",
                "[V4+ Styles]",
                "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
                "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
                "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
                "Alignment,MarginL,MarginR,MarginV,Encoding",
                "Style: Default,"
                f"{safe_font},{normalized['fontSize']},"
                f"{self.hex_to_ass_color(normalized['primaryColor'])},"
                f"{self.hex_to_ass_color(normalized['accentColor'])},"
                f"{self.hex_to_ass_color(normalized['outlineColor'])},"
                f"{self.hex_to_ass_color(normalized['backColor'], background_alpha if is_caption_box else 0)},"
                f"{bold},0,0,0,100,100,0,0,{border_style},"
                f"{normalized['outlineWidth']},{style_shadow},"
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

    def format_time(self, seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        whole_seconds = int(seconds % 60)
        centiseconds = int(round((seconds - int(seconds)) * 100))
        if centiseconds >= 100:
            whole_seconds += 1
            centiseconds = 0
            if whole_seconds >= 60:
                whole_seconds = 0
                minutes += 1
                if minutes >= 60:
                    minutes = 0
                    hours += 1
        return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"

    def _font_name(self, style: dict[str, Any]) -> str:
        """Resolve the real font family name used by libass / FFmpeg."""
        font_path = str(style.get("fontPath") or "").strip()
        if font_path:
            resolved = self.resolve_font_family(font_path)
            if resolved:
                return resolved
        font_family = str(style.get("fontFamily") or "").strip()
        if font_family and not self._looks_like_filename_stem(font_family, font_path):
            return font_family
        if font_path:
            return Path(font_path).stem
        return "Microsoft YaHei"

    @staticmethod
    def _looks_like_filename_stem(family: str, font_path: str) -> bool:
        if not font_path:
            return False
        stem = Path(font_path).stem
        return family.casefold() in {stem.casefold(), stem.replace("_", " ").casefold()}

    @staticmethod
    def resolve_font_family(font_path: str) -> str | None:
        """Read the real family name from a font file (TTF/OTF/TTC)."""
        path = Path(font_path).expanduser()
        if not path.is_file():
            return None
        try:
            from PIL import ImageFont

            # TTC collections: try first faces until one loads.
            last_error: Exception | None = None
            for index in range(0, 8):
                try:
                    font = ImageFont.truetype(str(path), size=24, index=index)
                    family, _style = font.getname()
                    family = (family or "").strip()
                    if family:
                        return family
                except OSError as exc:
                    last_error = exc
                    if index == 0:
                        # Non-collection font that failed once.
                        break
                    continue
            if last_error:
                return None
        except Exception:
            return None
        return None

    @staticmethod
    def _blur_amount(shadow: int) -> float:
        """Map UI shadow (0-12) to ASS \\blur for soft glow, not hard double-ghost."""
        try:
            value = int(shadow)
        except (TypeError, ValueError):
            value = 0
        if value <= 0:
            return 0.0
        # Gentle curve: 1→0.8, 4→2.4, 12→6.0
        return round(min(6.0, max(0.6, value * 0.55)), 2)

    def _dialogue_prefix_tags(
        self,
        style: dict[str, Any],
        segment_duration: float,
        blur_amount: float,
    ) -> str:
        """Build ASS override tags for fade + soft blur (no hard offset shadow)."""
        tags: list[str] = []
        fade = self._fade_tag(style, segment_duration)
        if fade.startswith("{") and fade.endswith("}"):
            tags.append(fade[1:-1])  # e.g. \\fad(120,120)
        if blur_amount > 0:
            tags.append(f"\\blur{blur_amount:g}")
        if not tags:
            return ""
        return "{" + "".join(tags) + "}"

    def _highlight_color_map(self, style: dict[str, Any]) -> dict[str, str]:
        """Map casefolded highlight word -> hex color."""
        accent = self._normalize_hex_color(style.get("accentColor"), "#FFD43B")
        colors = style.get("keywordColors") or {}
        words = style.get("highlightWords") or []
        result: dict[str, str] = {}
        for word in words:
            key = str(word).casefold()
            override = colors.get(word) or colors.get(str(word))
            # Also try case-insensitive lookup in keywordColors.
            if not override and isinstance(colors, dict):
                for raw_key, raw_color in colors.items():
                    if str(raw_key).casefold() == key:
                        override = raw_color
                        break
            result[key] = self._normalize_hex_color(override, accent) if override else accent
        # Allow keywordColors-only entries without listing in highlightWords.
        if isinstance(colors, dict):
            for raw_key, raw_color in colors.items():
                key = str(raw_key).casefold()
                if key and key not in result:
                    result[key] = self._normalize_hex_color(raw_color, accent)
        return result

    def apply_ass_highlights(self, text: str, style: dict[str, Any]) -> str:
        """Wrap highlight words with ASS primary-color overrides."""
        color_map = self._highlight_color_map(style)
        if not color_map:
            return self.escape_ass_text(text)

        # Build matcher from original highlightWords for display casing.
        display_words = list(style.get("highlightWords") or [])
        for key in color_map:
            if not any(str(w).casefold() == key for w in display_words):
                display_words.append(key)
        display_words = sorted(
            {w for w in display_words if str(w).casefold() in color_map},
            key=lambda w: len(str(w)),
            reverse=True,
        )
        if not display_words:
            return self.escape_ass_text(text)

        pattern = re.compile(
            "(" + "|".join(re.escape(str(word)) for word in display_words) + ")",
            flags=re.IGNORECASE,
        )
        primary = self.hex_to_ass_color(style.get("primaryColor", "#FFFFFF"))
        parts: list[str] = []
        for fragment in pattern.split(text):
            if not fragment:
                continue
            if fragment.casefold() in color_map:
                ass_color = self.hex_to_ass_color(color_map[fragment.casefold()])
                parts.append(
                    r"{\c" + ass_color + "&}"
                    + self.escape_ass_text(fragment)
                    + r"{\c" + primary + "&}"
                )
            else:
                parts.append(self.escape_ass_text(fragment))
        return "".join(parts)

    def _fade_tag(self, style: dict[str, Any], segment_duration: float) -> str:
        if style.get("animation") == "none":
            return ""
        # ASS uses fade for fade and degraded pop/word-pop.
        if style.get("animation") not in {"fade", "pop", "word-pop"}:
            return ""
        fade_in = int(style.get("fadeInMs", 120))
        fade_out = int(style.get("fadeOutMs", 120))
        # Keep fades within segment length so short cues still appear fully.
        max_total_ms = max(0, int(segment_duration * 1000) - 40)
        if fade_in + fade_out > max_total_ms and max_total_ms > 0:
            scale = max_total_ms / max(fade_in + fade_out, 1)
            fade_in = int(fade_in * scale)
            fade_out = int(fade_out * scale)
        if fade_in <= 0 and fade_out <= 0:
            return ""
        return r"{\fad(" + f"{max(0, fade_in)},{max(0, fade_out)}" + r")}"
