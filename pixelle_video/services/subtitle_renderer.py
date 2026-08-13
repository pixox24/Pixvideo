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

# Default caption-box padding (ASS BorderStyle=3 uses Outline as box thickness).
# Never default to 0 — that produces an invisible box under libass.
DEFAULT_BOX_PADDING = 10
DEFAULT_BOX_RADIUS = 12
DEFAULT_BOX_OPACITY = 72

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
    "backgroundOpacity": DEFAULT_BOX_OPACITY,
    "fadeInMs": 120,
    "fadeOutMs": 120,
    # Intent fields (normalized always writes these; callers may also send them).
    "boxEnabled": False,
    "boxColor": "#000000",
    "boxOpacity": DEFAULT_BOX_OPACITY,
    "boxPadding": DEFAULT_BOX_PADDING,
    "boxRadius": DEFAULT_BOX_RADIUS,
    "strokeWidth": 0,
    "strokeColor": "#000000",
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
        # Keep glow light; higher values previously became heavy ASS \\blur.
        "shadow": 1,
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
        # Dual-write: outlineWidth mirrors boxPadding for legacy UI controls.
        "outlineWidth": DEFAULT_BOX_PADDING,
        "shadow": 0,
        "marginV": 200,
        "maxLines": 1,
        "backgroundOpacity": DEFAULT_BOX_OPACITY,
        "boxPadding": DEFAULT_BOX_PADDING,
        "boxOpacity": DEFAULT_BOX_OPACITY,
        "boxColor": "#000000",
        "boxRadius": DEFAULT_BOX_RADIUS,
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
        # Allow up to 24 so caption-box padding can dual-write via outlineWidth.
        normalized["outlineWidth"] = self._coerce_int(normalized.get("outlineWidth"), 3, 0, 24)
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
            DEFAULT_BOX_OPACITY,
            0,
            100,
        )
        normalized["fadeInMs"] = self._coerce_int(normalized.get("fadeInMs"), 120, 0, 1000)
        normalized["fadeOutMs"] = self._coerce_int(normalized.get("fadeOutMs"), 120, 0, 1000)
        return self._apply_subtitle_intent(normalized, raw_style)

    def _apply_subtitle_intent(
        self,
        normalized: dict[str, Any],
        raw_style: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Derive box/stroke intent and dual-write legacy fields.

        caption-box (libass BorderStyle=3):
          - box fill colour is OutlineColour (not BackColour)
          - box thickness is Outline width (= boxPadding)
          - stroke is not available in the same ASS style layer
        """
        box_enabled = (
            normalized.get("preset") == "caption-box"
            or bool(normalized.get("boxEnabled"))
            or str(raw_style.get("boxEnabled") or "").lower() in {"1", "true", "yes"}
        )
        raw_keys = set(raw_style.keys()) if isinstance(raw_style, dict) else set()

        # Prefer explicitly provided fields over preset dual-write defaults.
        if "boxColor" in raw_keys:
            box_color = self._normalize_hex_color(raw_style.get("boxColor"), "#000000")
        elif "backColor" in raw_keys:
            box_color = self._normalize_hex_color(raw_style.get("backColor"), "#000000")
        else:
            box_color = self._normalize_hex_color(
                normalized.get("boxColor") or normalized.get("backColor"),
                "#000000",
            )

        if "boxOpacity" in raw_keys:
            box_opacity = self._coerce_int(raw_style.get("boxOpacity"), DEFAULT_BOX_OPACITY, 0, 100)
        elif "backgroundOpacity" in raw_keys:
            box_opacity = self._coerce_int(
                raw_style.get("backgroundOpacity"),
                DEFAULT_BOX_OPACITY,
                0,
                100,
            )
        else:
            box_opacity = self._coerce_int(
                normalized.get("boxOpacity", normalized.get("backgroundOpacity")),
                DEFAULT_BOX_OPACITY,
                0,
                100,
            )

        # boxPadding resolution for caption-box:
        # 1) explicit boxPadding
        # 2) outlineWidth if caller set it (>0) — legacy "use stroke slider as padding"
        # 3) DEFAULT_BOX_PADDING when outlineWidth is 0 (old broken default)
        if "boxPadding" in raw_keys and raw_style.get("boxPadding") is not None:
            box_padding = self._coerce_int(raw_style.get("boxPadding"), DEFAULT_BOX_PADDING, 0, 24)
        elif box_enabled:
            raw_outline = raw_style.get("outlineWidth", None)
            if raw_outline is not None:
                try:
                    outline_as_padding = int(raw_outline)
                except (TypeError, ValueError):
                    outline_as_padding = 0
                if outline_as_padding > 0:
                    box_padding = self._coerce_int(outline_as_padding, DEFAULT_BOX_PADDING, 1, 24)
                else:
                    # Explicit 0 or legacy preset 0 → use safe default so the box is visible.
                    box_padding = DEFAULT_BOX_PADDING
            else:
                box_padding = self._coerce_int(
                    normalized.get("boxPadding", normalized.get("outlineWidth")),
                    DEFAULT_BOX_PADDING,
                    1,
                    24,
                )
                if box_padding <= 0:
                    box_padding = DEFAULT_BOX_PADDING
        else:
            box_padding = self._coerce_int(
                normalized.get("boxPadding"),
                DEFAULT_BOX_PADDING,
                0,
                24,
            )

        box_radius = self._coerce_int(
            normalized.get("boxRadius"),
            DEFAULT_BOX_RADIUS,
            0,
            48,
        )

        if box_enabled:
            stroke_width = 0
            stroke_color = self._normalize_hex_color(
                normalized.get("strokeColor") or normalized.get("outlineColor"),
                "#000000",
            )
            normalized["boxEnabled"] = True
            normalized["boxColor"] = box_color
            normalized["boxOpacity"] = box_opacity
            normalized["boxPadding"] = box_padding
            normalized["boxRadius"] = box_radius
            # Dual-write legacy fields used by UI / drawtext / hyperframes.
            normalized["backColor"] = box_color
            normalized["backgroundOpacity"] = box_opacity
            normalized["outlineWidth"] = box_padding
            # Keep outlineColor as stroke intent for non-ASS; box fill is boxColor.
            normalized["strokeWidth"] = stroke_width
            normalized["strokeColor"] = stroke_color
        else:
            stroke_width = self._coerce_int(normalized.get("outlineWidth"), 0, 0, 12)
            if "strokeWidth" in raw_keys and raw_style.get("strokeWidth") is not None:
                stroke_width = self._coerce_int(raw_style.get("strokeWidth"), stroke_width, 0, 12)
            stroke_color = self._normalize_hex_color(
                normalized.get("strokeColor") or normalized.get("outlineColor"),
                "#000000",
            )
            normalized["boxEnabled"] = False
            normalized["boxColor"] = box_color
            normalized["boxOpacity"] = box_opacity
            normalized["boxPadding"] = box_padding
            normalized["boxRadius"] = box_radius
            normalized["strokeWidth"] = stroke_width
            normalized["strokeColor"] = stroke_color
            normalized["outlineWidth"] = stroke_width
            normalized["outlineColor"] = stroke_color

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

    @staticmethod
    def _alignment_is_coarse(cues: list[Any], segments: list[str]) -> bool:
        """True when TTS cues lack phrase-level timing (e.g. one cue for whole scene)."""
        if not cues:
            return True
        if len(segments) <= 1:
            return False
        # MiniMax continuous often stores one sentence-level cue per scene.
        if len(cues) == 1 and len(segments) > 1:
            return True
        if len(cues) * 2 < len(segments):
            return True
        return False

    def _proportional_timed(
        self,
        segments: list[str],
        weights: list[int],
        speech_duration: float,
    ) -> list[TimedCaptionSegment]:
        total_weight = sum(weights) or len(segments)
        timed: list[TimedCaptionSegment] = []
        cursor = 0.0
        min_segment = min(0.3, speech_duration / max(len(segments), 1))
        for index, (segment, weight) in enumerate(zip(segments, weights)):
            if index == len(segments) - 1:
                end = speech_duration
            else:
                share = speech_duration * (weight / total_weight)
                end = min(speech_duration, cursor + max(min_segment, share))
            start = cursor
            if end <= start:
                end = min(speech_duration, start + min_segment)
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
                end=speech_duration,
                weight=last.weight,
            )
        return timed

    def _snap_timed_to_silence(
        self,
        timed: list[TimedCaptionSegment],
        audio_path: str | Path,
        speech_duration: float,
    ) -> list[TimedCaptionSegment]:
        """
        Move internal cue boundaries onto nearby silence onsets.

        Used when word-level alignment is missing/coarse so captions track real
        breath pauses (e.g. after「…的人。」 before「原来权力的滋味」).
        """
        if len(timed) < 2:
            return timed
        try:
            from pixelle_video.services.continuous_tts.split import detect_silence_islands
        except Exception:
            return timed

        silences = detect_silence_islands(
            audio_path,
            total_duration=speech_duration,
            min_silence=0.12,
            noise_db=-28.0,
        )
        if not silences:
            return timed

        total = max(0.05, float(speech_duration))
        min_span = min(0.25, total / max(len(timed) * 2, 1))

        # Leading silence → first cue starts at speech onset.
        leading_end = 0.0
        for sil_start, sil_end in silences:
            if sil_start <= 0.08:
                leading_end = max(leading_end, float(sil_end))

        # Trailing silence → last cue ends at last speech (optional trim).
        trailing_start = total
        for sil_start, sil_end in silences:
            if sil_end >= total - 0.08:
                trailing_start = min(trailing_start, float(sil_start))
        if trailing_start < leading_end + min_span:
            trailing_start = total

        # Snap internal cuts (end of timed[0..-2]).
        cuts = [float(item.end) for item in timed[:-1]]
        snapped_cuts: list[float] = []
        for index, cut in enumerate(cuts):
            prev = leading_end if index == 0 else snapped_cuts[index - 1]
            low = prev + min_span
            scenes_after = len(timed) - index - 1
            high = trailing_start - min_span * max(1, scenes_after)
            if high <= low:
                snapped_cuts.append(min(trailing_start - min_span, max(low, cut)))
                continue

            local_span = float(timed[index].end) - float(timed[index].start)
            window = max(0.6, min(2.5, local_span * 0.35 + 0.5))

            best_t = cut
            best_score: tuple[float, float, int] | None = None
            for sil_start, sil_end in silences:
                if sil_end < low - 0.05 or sil_start > high + 0.05:
                    continue
                sil_len = max(0.0, sil_end - sil_start)
                for raw_t, priority in (
                    (sil_end, 0),  # end of silence = next phrase onset
                    ((sil_start + sil_end) / 2.0, 1),
                    (sil_start, 2),
                ):
                    t = min(high, max(low, float(raw_t)))
                    dist = abs(t - cut)
                    if dist > window:
                        continue
                    score = (dist, -sil_len, priority)
                    if best_score is None or score < best_score:
                        best_score = score
                        best_t = t
            snapped_cuts.append(best_t)

        rebuilt: list[TimedCaptionSegment] = []
        cursor = leading_end if leading_end < total * 0.25 else 0.0
        for index, item in enumerate(timed):
            if index < len(snapped_cuts):
                end = max(cursor + min_span, min(trailing_start, snapped_cuts[index]))
            else:
                end = trailing_start if trailing_start < total else total
            if end <= cursor:
                end = min(total, cursor + min_span)
            rebuilt.append(
                TimedCaptionSegment(
                    text=item.text,
                    start=cursor,
                    end=end if index < len(timed) - 1 else total,
                    weight=item.weight,
                )
            )
            cursor = rebuilt[-1].end
        if rebuilt:
            last = rebuilt[-1]
            rebuilt[-1] = TimedCaptionSegment(
                text=last.text,
                start=last.start,
                end=total,
                weight=last.weight,
            )
        return rebuilt

    def plan_segments(
        self,
        text: str,
        duration: float,
        style: dict[str, Any] | None = None,
        alignment: list[Any] | None = None,
        *,
        hold_seconds: float = 0.0,
        audio_path: str | Path | None = None,
    ) -> list[TimedCaptionSegment]:
        """Build timed segments.

        ``duration`` is the **speech/narration** window used to schedule cues
        (same contract as workbench preview: audio only, no manual hold).

        Prefer fine TTS alignment (word/phrase cues) when available; otherwise
        proportional character-weight timing, then optional **silence snap** when
        ``audio_path`` is provided (MiniMax whole-scene cues count as coarse).

        ``hold_seconds`` keeps the last cue visible after speech ends (preview
        1B) without stretching earlier cues across the hold.
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

        speech_duration = max(0.05, float(duration))
        hold = max(0.0, float(hold_seconds or 0.0))
        weights = [self.effective_weight(segment) for segment in segments]

        cues: list[AlignmentCue] = []
        if alignment:
            if all(isinstance(item, AlignmentCue) for item in alignment):
                cues = list(alignment)  # type: ignore[arg-type]
            else:
                cues = parse_alignment_payload(alignment)

        coarse = self._alignment_is_coarse(cues, segments)
        timed: list[TimedCaptionSegment]
        if cues and not coarse:
            aligned_times = map_segments_to_alignment(segments, cues, speech_duration)
            if aligned_times and len(aligned_times) == len(segments):
                timed = [
                    TimedCaptionSegment(
                        text=segment,
                        start=start,
                        end=end,
                        weight=weight,
                    )
                    for segment, (start, end), weight in zip(segments, aligned_times, weights)
                ]
            else:
                timed = self._proportional_timed(segments, weights, speech_duration)
        else:
            timed = self._proportional_timed(segments, weights, speech_duration)

        # Silence snap when no fine alignment (or alignment was coarse).
        if audio_path and (coarse or not cues) and len(timed) > 1:
            timed = self._snap_timed_to_silence(timed, audio_path, speech_duration)

        # Hold: freeze last line only — do not re-proportion earlier cues.
        if timed and hold > 1e-9:
            last = timed[-1]
            timed[-1] = TimedCaptionSegment(
                text=last.text,
                start=last.start,
                end=speech_duration + hold,
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
        *,
        hold_seconds: float = 0.0,
        audio_path: str | Path | None = None,
    ) -> str:
        normalized = self.normalize_style(style)
        font_name = self._font_name(normalized)
        timed_segments = self.plan_segments(
            text,
            duration,
            normalized,
            alignment=alignment,
            hold_seconds=hold_seconds,
            audio_path=audio_path,
        )
        if not timed_segments:
            total = max(0.05, float(duration) + max(0.0, float(hold_seconds or 0.0)))
            timed_segments = [
                TimedCaptionSegment(
                    text=self.wrap_text(text, normalized["maxCharsPerLine"], normalized["maxLines"]),
                    start=0.0,
                    end=total,
                    weight=1,
                )
            ]

        # Soft glow via ASS blur; keep hard Shadow at 0 to avoid double-ghost offset.
        # Cap blur tightly — high UI shadow used to map to blur≈3–6 and looked "out of focus".
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
        is_caption_box = bool(normalized.get("boxEnabled")) or normalized.get("preset") == "caption-box"
        bold = 1 if normalized["preset"] == "short-video-bold" else 0

        if is_caption_box:
            # libass BorderStyle=3: opaque box fill uses OutlineColour; Outline is padding.
            # BackColour is ignored for the fill — we still write the same colour for clarity.
            box_color = str(normalized.get("boxColor") or normalized.get("backColor") or "#000000")
            box_opacity = int(normalized.get("boxOpacity", normalized.get("backgroundOpacity", DEFAULT_BOX_OPACITY)))
            box_padding = max(
                1,
                int(normalized.get("boxPadding", normalized.get("outlineWidth", DEFAULT_BOX_PADDING)) or DEFAULT_BOX_PADDING),
            )
            background_alpha = round(255 * (1 - (max(0, min(100, box_opacity)) / 100)))
            outline_colour = self.hex_to_ass_color(box_color, background_alpha)
            back_colour = self.hex_to_ass_color(box_color, background_alpha)
            border_style = 3
            outline_width = box_padding
        else:
            outline_colour = self.hex_to_ass_color(
                str(normalized.get("strokeColor") or normalized.get("outlineColor") or "#000000")
            )
            back_colour = self.hex_to_ass_color(normalized.get("backColor") or "#000000", 0)
            border_style = 1
            outline_width = int(normalized.get("strokeWidth", normalized.get("outlineWidth", 0)) or 0)
            # Zero outline + soft blur = mushy glyphs. Ensure a hard edge for readability.
            shadow_val = int(normalized.get("shadow", 0) or 0)
            if outline_width <= 0 and (shadow_val > 0 or blur_amount > 0):
                outline_width = max(1, min(3, (shadow_val + 1) // 2 or 1))

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
                f"{outline_colour},"
                f"{back_colour},"
                f"{bold},0,0,0,100,100,0,0,{border_style},"
                f"{outline_width},{style_shadow},"
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
        """Map UI shadow (0-12) to a *light* ASS \\blur (soft edge, not defocus).

        Historical mapping (value*0.55, max 6) made shadow=6 look like out-of-focus
        captions on 1080p/2K exports. Keep glow subtle; hard edge comes from Outline.
        """
        try:
            value = int(shadow)
        except (TypeError, ValueError):
            value = 0
        if value <= 0:
            return 0.0
        # Curve: 1→0.4, 4→0.9, 6→1.2, 12→1.5 (hard cap)
        return round(min(1.5, max(0.35, value * 0.2)), 2)

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
        # Short cues: never let fade dominate (e.g. 1.4s cue with fad(400,400)).
        # Cap each side to 15% of cue length and total fade to 30%.
        duration_ms = max(0, int(float(segment_duration) * 1000))
        max_each = max(0, int(duration_ms * 0.15))
        max_total = max(0, int(duration_ms * 0.30))
        # Also leave a readable solid middle (~40ms margin for very short clips).
        max_total = min(max_total, max(0, duration_ms - 40))
        fade_in = min(fade_in, max_each)
        fade_out = min(fade_out, max_each)
        if fade_in + fade_out > max_total and max_total > 0:
            scale = max_total / max(fade_in + fade_out, 1)
            fade_in = int(fade_in * scale)
            fade_out = int(fade_out * scale)
        if fade_in <= 0 and fade_out <= 0:
            return ""
        return r"{\fad(" + f"{max(0, fade_in)},{max(0, fade_out)}" + r")}"
