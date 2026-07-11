from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from pixelle_video.services.subtitle_renderer import SubtitleRenderer

HYPERFRAMES_VERSION = "0.7.48"


@dataclass(frozen=True)
class CaptionSegment:
    id: str
    text: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class CaptionPlan:
    canvas: dict[str, int]
    duration_ms: int
    style: dict[str, Any]
    captions: list[CaptionSegment]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "canvas": self.canvas,
            "durationMs": self.duration_ms,
            "style": self.style,
            "captions": [asdict(caption) for caption in self.captions],
        }


class HyperframesCaptionRenderer:
    """Render an advanced caption plan to a transparent WebM overlay."""

    def __init__(self, npx_command: str = "npx", timeout_seconds: int = 300):
        self.npx_command = npx_command
        self.timeout_seconds = timeout_seconds
        self.subtitle_renderer = SubtitleRenderer()

    def build_caption_plan(
        self,
        text: str,
        duration: float,
        width: int,
        height: int,
        fps: int,
        style: dict[str, Any] | None = None,
    ) -> CaptionPlan:
        if duration <= 0:
            raise ValueError("Caption duration must be positive")
        if width <= 0 or height <= 0 or fps <= 0:
            raise ValueError("Caption canvas width, height, and fps must be positive")

        normalized_style = self.subtitle_renderer.normalize_style(style)
        if normalized_style["highlightWords"]:
            segments = self._dynamic_segments(
                text,
                normalized_style["segmentMode"],
                normalized_style["maxCharsPerLine"],
                normalized_style["maxLines"],
                normalized_style["highlightWords"],
            )
            segments = [
                self._wrap_highlighted_text(
                    segment,
                    normalized_style["maxCharsPerLine"],
                    normalized_style["maxLines"],
                    normalized_style["highlightWords"],
                )
                for segment in segments
            ]
        else:
            segments = self.subtitle_renderer.segment_text(
                text,
                normalized_style["segmentMode"],
                normalized_style["maxCharsPerLine"],
                normalized_style["maxLines"],
            )
            if not segments:
                segments = [self.subtitle_renderer.wrap_text(
                    text,
                    normalized_style["maxCharsPerLine"],
                    normalized_style["maxLines"],
                )]
        segments = [segment for segment in segments if segment]
        if not segments:
            raise ValueError("Caption text cannot be empty")

        duration_ms = max(1, int(round(duration * 1000)))
        captions: list[CaptionSegment] = []
        for index, segment in enumerate(segments):
            start_ms = round(duration_ms * index / len(segments))
            end_ms = round(duration_ms * (index + 1) / len(segments))
            captions.append(
                CaptionSegment(
                    id=f"caption-{index + 1}",
                    text=segment,
                    start_ms=start_ms,
                    end_ms=max(start_ms + 1, end_ms),
                )
            )
        captions[-1] = CaptionSegment(
            id=captions[-1].id,
            text=captions[-1].text,
            start_ms=captions[-1].start_ms,
            end_ms=duration_ms,
        )

        return CaptionPlan(
            canvas={"width": width, "height": height, "fps": fps},
            duration_ms=duration_ms,
            style=normalized_style,
            captions=captions,
        )

    def prepare_project(self, plan: CaptionPlan, project_dir: str | Path) -> Path:
        project = Path(project_dir)
        project.mkdir(parents=True, exist_ok=True)
        (project / "assets").mkdir(exist_ok=True)
        (project / "compositions").mkdir(exist_ok=True)
        (project / "caption-plan.json").write_text(
            json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (project / "hyperframes.json").write_text(
            json.dumps(
                {
                    "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
                    "paths": {"assets": "assets"},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        font_source = Path(str(plan.style.get("fontPath") or "")).expanduser()
        font_url = ""
        if font_source.is_file():
            font_target = project / "assets" / font_source.name
            shutil.copy2(font_source, font_target)
            font_url = f"assets/{font_target.name}"

        composition = self._composition_html(plan, font_url)
        (project / "compositions" / "caption-overlay.html").write_text(
            composition,
            encoding="utf-8",
        )
        # The CLI discovers projects from this root entrypoint before resolving --composition.
        (project / "index.html").write_text(composition, encoding="utf-8")
        return project

    def render_overlay(self, plan: CaptionPlan, output_dir: str | Path) -> str:
        project = self.prepare_project(plan, output_dir)
        output_path = project / "caption-overlay.webm"
        command = [
            self.npx_command,
            "--yes",
            f"hyperframes@{HYPERFRAMES_VERSION}",
            "render",
            ".",
            "--composition",
            "compositions/caption-overlay.html",
            "--format",
            "webm",
            "--output",
            output_path.name,
            "--fps",
            str(plan.canvas["fps"]),
            "--quality",
            "draft",
            "--workers",
            "1",
            "--strict",
        ]
        try:
            subprocess.run(
                command,
                cwd=project,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("Dynamic subtitles require Node.js and npx.") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("Dynamic subtitle rendering timed out.") from exc
        except subprocess.CalledProcessError as exc:
            details = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(f"Dynamic subtitle rendering failed: {details}") from exc

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise RuntimeError("Dynamic subtitle renderer did not produce a WebM overlay.")
        return str(output_path)

    def _composition_html(self, plan: CaptionPlan, font_url: str) -> str:
        width = plan.canvas["width"]
        height = plan.canvas["height"]
        fps = plan.canvas["fps"]
        style = plan.style
        outline = max(0, min(12, int(style["outlineWidth"])))
        requested_font_size = max(12, min(120, int(style["fontSize"])))
        max_chars_per_line = max(4, int(style["maxCharsPerLine"]))
        available_width = width * 0.8
        max_font_size = int((available_width - 2 * outline) / (max_chars_per_line + 0.7))
        font_size = max(12, min(requested_font_size, max_font_size))
        bottom = max(0, min(height // 2, int(style["marginV"])))
        shadow = max(0, min(12, int(style["shadow"])))
        text_color = self._hex_color(style.get("primaryColor"), "#FFFFFF")
        accent_color = self._hex_color(style.get("accentColor"), "#FFD43B")
        outline_color = self._hex_color(style.get("outlineColor"), "#000000")
        background_color = self._rgba_color(
            style.get("backColor"),
            max(0, min(100, int(style.get("backgroundOpacity", 72)))) / 100,
        )
        alignment = int(style.get("alignment", 2))
        text_alignment, caption_position = self._caption_alignment(alignment)
        highlight_words = self._highlight_words(style.get("highlightWords"))
        highlight_style = str(style.get("highlightStyle") or "accent")
        highlight_scale = max(100, min(180, int(style.get("highlightScale", 125)))) / 100
        font_family = "DynamicCaptionFont" if font_url else str(style.get("fontFamily") or "")
        if not font_family:
            font_family = "PingFang SC"

        font_face = ""
        if font_url:
            font_face = (
                "@font-face {"
                "font-family: DynamicCaptionFont;"
                f"src: url({json.dumps('./' + font_url, ensure_ascii=False)});"
                "}"
            )
        background_rule = background_color if style.get("preset") == "caption-box" else "transparent"
        caption_class = "caption pop" if style.get("animation") == "pop" else "caption"
        captions = "\n".join(
            (
                f'<div id="{caption.id}" class="{caption_class} clip" '
                f'data-start="{caption.start_ms / 1000:.3f}" '
                f'data-duration="{(caption.end_ms - caption.start_ms) / 1000:.3f}" '
                'data-track-index="1" data-layout-allow-occlusion>'
                f"{self._caption_markup(caption.text, highlight_words, highlight_style)}"
                "</div>"
            )
            for caption in plan.captions
        )
        timelines = "\n".join(
            self._timeline_statement(
                caption,
                style.get("animation", "fade"),
                highlight_scale,
            )
            for caption in plan.captions
        )

        return f"""<!doctype html>
<html lang=\"zh-CN\" data-resolution=\"custom\">
  <head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width={width}, height={height}\" />
    <script src=\"https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js\"></script>
    <style>
      {font_face}
      @font-face {{ font-family: \"PingFang SC\"; src: local(\"PingFang SC\"); }}
      @font-face {{ font-family: \"Hiragino Sans GB\"; src: local(\"Hiragino Sans GB\"); }}
      * {{ box-sizing: border-box; }}
      html, body {{ width: {width}px; height: {height}px; margin: 0; overflow: hidden; background: transparent; }}
      body {{ font-family: {json.dumps(font_family, ensure_ascii=False)}, \"PingFang SC\", \"Hiragino Sans GB\", sans-serif; }}
      #caption-root {{ position: relative; width: {width}px; height: {height}px; overflow: hidden; }}
      .caption {{
        position: absolute; {caption_position} bottom: {bottom}px;
        width: fit-content; max-width: 86.6%; padding: 0.2em 0.35em;
        color: {text_color}; background: {background_rule}; border-radius: 12px;
        font-size: {font_size}px; font-weight: 800; line-height: 1.28; text-align: {text_alignment};
        white-space: nowrap; word-break: keep-all;
        -webkit-text-stroke: {outline}px {outline_color};
        text-shadow: {shadow}px {shadow}px {max(1, shadow * 2)}px {outline_color};
      }}
      .caption.pop {{ color: {accent_color}; }}
      .highlight {{ display: inline-block; color: {accent_color}; }}
      .highlight-pop {{ font-weight: 900; }}
      .highlight-badge {{
        padding: 0.02em 0.16em; border-radius: 0.16em; background: {accent_color}; color: #17110a;
        -webkit-text-stroke: 0; text-shadow: none;
      }}
    </style>
  </head>
  <body>
    <main id=\"caption-root\" data-composition-id=\"dynamic-caption-overlay\" data-start=\"0\" data-duration=\"{plan.duration_ms / 1000:.3f}\" data-width=\"{width}\" data-height=\"{height}\" data-fps=\"{fps}\">
      {captions}
    </main>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      {timelines}
      window.__timelines[\"dynamic-caption-overlay\"] = tl;
    </script>
  </body>
</html>
"""

    def _timeline_statement(
        self,
        caption: CaptionSegment,
        animation: str,
        highlight_scale: float,
    ) -> str:
        start = caption.start_ms / 1000
        if animation == "none":
            return ""
        if animation == "word-pop":
            return (
                f'tl.fromTo("#{caption.id}", {{ autoAlpha: 0, y: 22 }}, '
                f'{{ autoAlpha: 1, y: 0, duration: 0.18, ease: "power2.out" }}, {start:.3f});\n'
                f'tl.fromTo("#{caption.id} .highlight", {{ autoAlpha: 0, scale: 0.72 }}, '
                f'{{ autoAlpha: 1, scale: {highlight_scale:.2f}, duration: 0.18, '
                f'ease: "back.out(2.4)", stagger: 0.08 }}, {start + 0.08:.3f});\n'
                f'tl.to("#{caption.id} .highlight", {{ scale: 1, duration: 0.14, '
                f'ease: "power2.out", stagger: 0.08 }}, {start + 0.26:.3f});'
            )
        if animation == "pop":
            return (
                f'tl.fromTo("#{caption.id}", {{ autoAlpha: 0, scale: 0.72, y: 26 }}, '
                f'{{ autoAlpha: 1, scale: 1.08, y: 0, duration: 0.18, ease: "back.out(2.4)" }}, {start:.3f});\n'
                f'tl.to("#{caption.id}", {{ scale: 1, duration: 0.16, ease: "power2.out" }}, {start + 0.18:.3f});'
            )
        return (
            f'tl.fromTo("#{caption.id}", {{ autoAlpha: 0, y: 22 }}, '
            f'{{ autoAlpha: 1, y: 0, duration: 0.18, ease: "power2.out" }}, {start:.3f});'
        )

    @staticmethod
    def _highlight_words(raw_words: Any) -> list[str]:
        if not isinstance(raw_words, list):
            return []
        words = [str(word).strip() for word in raw_words if str(word).strip()]
        return sorted(dict.fromkeys(words), key=len, reverse=True)

    @staticmethod
    def _caption_alignment(alignment: int) -> tuple[str, str]:
        if alignment in {1, 4, 7}:
            return "left", "left: 6.7%; right: auto; margin: 0;"
        if alignment in {3, 6, 9}:
            return "right", "left: auto; right: 6.7%; margin: 0;"
        return "center", "left: 6.7%; right: 6.7%;"

    @staticmethod
    def _caption_markup(text: str, highlight_words: list[str], highlight_style: str) -> str:
        def escape_fragment(fragment: str) -> str:
            return html.escape(fragment).replace("\n", "<br>")

        if not highlight_words:
            return escape_fragment(text)

        matcher = re.compile(
            "(" + "|".join(re.escape(word) for word in highlight_words) + ")",
            flags=re.IGNORECASE,
        )
        highlight_keys = {word.casefold() for word in highlight_words}
        fragments: list[str] = []
        for fragment in matcher.split(text):
            if not fragment:
                continue
            escaped = escape_fragment(fragment)
            if fragment.casefold() in highlight_keys:
                fragments.append(
                    f'<span class="highlight highlight-{highlight_style}">{escaped}</span>'
                )
            else:
                fragments.append(escaped)
        return "".join(fragments)

    @staticmethod
    def _wrap_highlighted_text(
        text: str,
        max_chars_per_line: int,
        max_lines: int,
        highlight_words: list[str],
    ) -> str:
        words = HyperframesCaptionRenderer._highlight_words(highlight_words)
        if not words:
            return text
        tokens = HyperframesCaptionRenderer._highlight_tokens(text, words)

        lines: list[str] = []
        current = ""
        for token in tokens:
            if current and len(current) + len(token) > max_chars_per_line:
                lines.append(current)
                current = token
                if len(lines) >= max_lines:
                    break
            else:
                current += token
        if len(lines) < max_lines and current:
            lines.append(current)
        return "\n".join(lines[:max_lines])

    @staticmethod
    def _dynamic_segments(
        text: str,
        segment_mode: str,
        max_chars_per_line: int,
        max_lines: int,
        highlight_words: list[str],
    ) -> list[str]:
        cleaned = " ".join(str(text or "").split())
        if segment_mode == "line":
            raw_segments = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        elif segment_mode == "sentence":
            raw_segments = [
                part.strip()
                for part in re.split(r"(?<=[。！？!?\.])", cleaned)
                if part.strip()
            ]
        else:
            raw_segments = [cleaned]

        capacity = max(1, max_chars_per_line * max_lines)
        segments: list[str] = []
        for segment in raw_segments:
            segments.extend(
                HyperframesCaptionRenderer._split_highlighted_segment(
                    segment,
                    capacity,
                    highlight_words,
                )
            )
        return segments

    @staticmethod
    def _split_highlighted_segment(
        text: str,
        capacity: int,
        highlight_words: list[str],
    ) -> list[str]:
        segments: list[str] = []
        current = ""
        for token in HyperframesCaptionRenderer._highlight_tokens(text, highlight_words):
            if current and len(current) + len(token) > capacity:
                segments.append(current)
                current = token
            elif not current and len(token) > capacity:
                segments.append(token)
            else:
                current += token
        if current:
            segments.append(current)
        return segments

    @staticmethod
    def _highlight_tokens(text: str, highlight_words: list[str]) -> list[str]:
        words = HyperframesCaptionRenderer._highlight_words(highlight_words)
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

    @staticmethod
    def _hex_color(value: Any, default: str) -> str:
        candidate = str(value or "").strip()
        if len(candidate) == 7 and candidate.startswith("#"):
            try:
                int(candidate[1:], 16)
            except ValueError:
                return default
            return candidate.upper()
        return default

    @classmethod
    def _rgba_color(cls, value: Any, alpha: float) -> str:
        color = cls._hex_color(value, "#000000")
        red, green, blue = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
        return f"rgba({red}, {green}, {blue}, {alpha})"
