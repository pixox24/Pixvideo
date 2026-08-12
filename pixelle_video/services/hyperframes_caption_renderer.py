from __future__ import annotations

import html
import json
import os
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
        # Keep the default portable, while allowing Windows services whose PATH
        # differs from the interactive shell to point at an absolute npx.cmd.
        self.npx_command = os.getenv("PIXELLE_NPX_COMMAND", npx_command).strip() or npx_command
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
        alignment: list[Any] | None = None,
    ) -> CaptionPlan:
        if duration <= 0:
            raise ValueError("Caption duration must be positive")
        if width <= 0 or height <= 0 or fps <= 0:
            raise ValueError("Caption canvas width, height, and fps must be positive")

        normalized_style = self.subtitle_renderer.normalize_style(style)
        timed_segments = self.subtitle_renderer.plan_segments(
            text,
            duration,
            normalized_style,
            alignment=alignment,
        )
        if not timed_segments:
            raise ValueError("Caption text cannot be empty")

        duration_ms = max(1, int(round(duration * 1000)))
        captions: list[CaptionSegment] = []
        for index, timed in enumerate(timed_segments):
            start_ms = max(0, int(round(timed.start * 1000)))
            end_ms = max(start_ms + 1, int(round(timed.end * 1000)))
            if index == len(timed_segments) - 1:
                end_ms = duration_ms
            captions.append(
                CaptionSegment(
                    id=f"caption-{index + 1}",
                    text=timed.text,
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
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
                encoding="utf-8",
                errors="replace",
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
        box_enabled = bool(style.get("boxEnabled")) or style.get("preset") == "caption-box"
        # Stroke applies only outside caption-box; box mode uses padding instead.
        stroke_width = 0 if box_enabled else max(0, min(12, int(style.get("strokeWidth", style.get("outlineWidth", 0)))))
        box_padding = max(0, min(24, int(style.get("boxPadding", style.get("outlineWidth", 10)))))
        box_radius = max(0, min(48, int(style.get("boxRadius", 12))))
        requested_font_size = max(12, min(120, int(style["fontSize"])))
        max_chars_per_line = max(4, int(style["maxCharsPerLine"]))
        available_width = width * 0.8
        max_font_size = int((available_width - 2 * stroke_width) / (max_chars_per_line + 0.7))
        font_size = max(12, min(requested_font_size, max_font_size))
        bottom = max(0, min(height // 2, int(style["marginV"])))
        shadow = max(0, min(12, int(style["shadow"])))
        text_color = self._hex_color(style.get("primaryColor"), "#FFFFFF")
        accent_color = self._hex_color(style.get("accentColor"), "#FFD43B")
        outline_color = self._hex_color(
            style.get("strokeColor") or style.get("outlineColor"),
            "#000000",
        )
        box_color = style.get("boxColor") or style.get("backColor")
        box_opacity = max(
            0,
            min(100, int(style.get("boxOpacity", style.get("backgroundOpacity", 72)))),
        )
        background_color = self._rgba_color(box_color, box_opacity / 100)
        # CSS padding roughly matches ASS box padding (px at render font size).
        pad_y = max(4, int(round(box_padding * 0.55))) if box_enabled else max(2, int(font_size * 0.08))
        pad_x = max(6, int(round(box_padding * 0.9))) if box_enabled else max(4, int(font_size * 0.12))
        alignment = int(style.get("alignment", 2))
        text_alignment, caption_position = self._caption_alignment(alignment)
        highlight_words = self._highlight_words(style.get("highlightWords"))
        highlight_style = str(style.get("highlightStyle") or "accent")
        highlight_scale = max(100, min(180, int(style.get("highlightScale", 125)))) / 100
        # Font stack must only include families with matching @font-face (hyperframes --strict).
        system_faces = [
            ("PingFang SC", 'local("PingFang SC")'),
            ("Hiragino Sans GB", 'local("Hiragino Sans GB")'),
            ("Microsoft YaHei", 'local("Microsoft YaHei"), local("微软雅黑")'),
            ("Noto Sans CJK SC", 'local("Noto Sans CJK SC"), local("Noto Sans SC")'),
        ]
        font_face_rules: list[str] = []
        stack: list[str] = []
        if font_url:
            font_face_rules.append(
                "@font-face {"
                "font-family: DynamicCaptionFont;"
                f"src: url({json.dumps('./' + font_url, ensure_ascii=False)});"
                "}"
            )
            stack.append("DynamicCaptionFont")
        else:
            requested = str(style.get("fontFamily") or "").strip()
            if requested:
                # Declare the requested family as local so strict font checks pass.
                font_face_rules.append(
                    "@font-face {"
                    f"font-family: {json.dumps(requested, ensure_ascii=False)};"
                    f"src: local({json.dumps(requested, ensure_ascii=False)});"
                    "}"
                )
                stack.append(requested)
        for family_name, src in system_faces:
            font_face_rules.append(
                f"@font-face {{ font-family: {json.dumps(family_name)}; src: {src}; }}"
            )
            stack.append(family_name)
        stack.append("sans-serif")
        font_face = "\n      ".join(font_face_rules)
        font_family_css = ", ".join(
            json.dumps(name, ensure_ascii=False) if name != "sans-serif" else "sans-serif"
            for name in stack
        )

        font_weight = {
            "short-video-bold": 800,
            "clean-white": 600,
            "cinema-soft": 500,
            "caption-box": 700,
        }.get(str(style.get("preset")), 600)

        background_rule = background_color if box_enabled else "transparent"
        radius_rule = f"{box_radius}px" if box_enabled else "0"
        # Outer node is a time clip (framework-owned visibility).
        # Inner node receives GSAP enter/exit + hard kill (hyperframes strict rule).
        caption_inner_class = "caption-inner pop" if style.get("animation") == "pop" else "caption-inner"
        captions = "\n".join(
            (
                f'<div id="{caption.id}" class="clip" '
                f'data-start="{caption.start_ms / 1000:.3f}" '
                f'data-duration="{(caption.end_ms - caption.start_ms) / 1000:.3f}" '
                'data-track-index="1" data-layout-allow-occlusion>'
                f'<div id="{caption.id}-inner" class="{caption_inner_class}">'
                f"{self._caption_markup(caption.text, highlight_words, highlight_style, style)}"
                f"</div></div>"
            )
            for caption in plan.captions
        )
        fade_in = max(0, min(1000, int(style.get("fadeInMs", 120)))) / 1000
        fade_out = max(0, min(1000, int(style.get("fadeOutMs", 120)))) / 1000
        timelines = "\n".join(
            self._timeline_statement(
                caption,
                style.get("animation", "fade"),
                highlight_scale,
                fade_in,
                fade_out,
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
      * {{ box-sizing: border-box; }}
      html, body {{ width: {width}px; height: {height}px; margin: 0; overflow: hidden; background: transparent; }}
      body {{ font-family: {font_family_css}; }}
      #caption-root {{ position: relative; width: {width}px; height: {height}px; overflow: hidden; }}
      .clip {{
        position: absolute; {caption_position} bottom: {bottom}px;
        width: fit-content; max-width: 86.6%;
      }}
      .caption-inner {{
        width: fit-content; max-width: 100%; padding: {pad_y}px {pad_x}px;
        color: {text_color}; background: {background_rule}; border-radius: {radius_rule};
        font-size: {font_size}px; font-weight: {font_weight}; line-height: 1.28; text-align: {text_alignment};
        white-space: nowrap; word-break: keep-all;
        -webkit-text-stroke: {stroke_width}px {outline_color};
        text-shadow: {shadow}px {shadow}px {max(1, shadow * 2)}px {outline_color};
      }}
      .caption-inner.pop {{ color: {accent_color}; }}
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
        fade_in: float = 0.12,
        fade_out: float = 0.12,
    ) -> str:
        """GSAP targets the inner non-clip node; hard-kill at clip end for --strict."""
        start = caption.start_ms / 1000
        end = caption.end_ms / 1000
        duration = max(0.05, end - start)
        enter = min(fade_in if fade_in > 0 else 0.18, max(0.05, duration * 0.35))
        exit_dur = min(fade_out if fade_out > 0 else 0.12, max(0.04, duration * 0.3))
        exit_at = max(start + enter, end - exit_dur)
        # Keep exit fully before the clip end so hard kill sits on the boundary cleanly.
        if exit_at + exit_dur > end:
            exit_at = max(start, end - exit_dur)
        inner = f"#{caption.id}-inner"
        hard_kill = f'tl.set("{inner}", {{ autoAlpha: 0 }}, {end:.3f});'

        if animation == "none":
            return (
                f'tl.set("{inner}", {{ autoAlpha: 1 }}, {start:.3f});\n'
                f"{hard_kill}"
            )
        if animation == "word-pop":
            return (
                f'tl.fromTo("{inner}", {{ autoAlpha: 0, y: 22 }}, '
                f'{{ autoAlpha: 1, y: 0, duration: {enter:.3f}, ease: "power2.out" }}, {start:.3f});\n'
                f'tl.fromTo("{inner} .highlight", {{ autoAlpha: 0, scale: 0.72 }}, '
                f'{{ autoAlpha: 1, scale: {highlight_scale:.2f}, duration: {enter:.3f}, '
                f'ease: "back.out(2.4)", stagger: 0.08 }}, {start + 0.08:.3f});\n'
                f'tl.to("{inner} .highlight", {{ scale: 1, duration: 0.14, '
                f'ease: "power2.out", stagger: 0.08 }}, {start + enter:.3f});\n'
                f'tl.to("{inner}", {{ autoAlpha: 0, y: 10, duration: {exit_dur:.3f}, '
                f'ease: "power2.in" }}, {exit_at:.3f});\n'
                f"{hard_kill}"
            )
        if animation == "pop":
            return (
                f'tl.fromTo("{inner}", {{ autoAlpha: 0, scale: 0.72, y: 26 }}, '
                f'{{ autoAlpha: 1, scale: 1.08, y: 0, duration: {enter:.3f}, ease: "back.out(2.4)" }}, {start:.3f});\n'
                f'tl.to("{inner}", {{ scale: 1, duration: 0.16, ease: "power2.out" }}, {start + enter:.3f});\n'
                f'tl.to("{inner}", {{ autoAlpha: 0, scale: 0.96, y: 10, duration: {exit_dur:.3f}, '
                f'ease: "power2.in" }}, {exit_at:.3f});\n'
                f"{hard_kill}"
            )
        # Default: ease-in / ease-out fade.
        return (
            f'tl.fromTo("{inner}", {{ autoAlpha: 0, y: 22 }}, '
            f'{{ autoAlpha: 1, y: 0, duration: {enter:.3f}, ease: "power2.out" }}, {start:.3f});\n'
            f'tl.to("{inner}", {{ autoAlpha: 0, y: 10, duration: {exit_dur:.3f}, '
            f'ease: "power2.in" }}, {exit_at:.3f});\n'
            f"{hard_kill}"
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
    def _caption_markup(
        text: str,
        highlight_words: list[str],
        highlight_style: str,
        style: dict[str, Any] | None = None,
    ) -> str:
        def escape_fragment(fragment: str) -> str:
            return html.escape(fragment).replace("\n", "<br>")

        style = style or {}
        accent = HyperframesCaptionRenderer._hex_color(style.get("accentColor"), "#FFD43B")
        keyword_colors = style.get("keywordColors") if isinstance(style.get("keywordColors"), dict) else {}
        # Merge keywordColors-only keys into the highlight list.
        words = list(highlight_words)
        for key in keyword_colors:
            if str(key).strip() and not any(str(key).casefold() == w.casefold() for w in words):
                words.append(str(key).strip())
        words = HyperframesCaptionRenderer._highlight_words(words)
        if not words:
            return escape_fragment(text)

        matcher = re.compile(
            "(" + "|".join(re.escape(word) for word in words) + ")",
            flags=re.IGNORECASE,
        )
        color_by_key: dict[str, str] = {}
        for word in words:
            override = None
            if isinstance(keyword_colors, dict):
                override = keyword_colors.get(word)
                if not override:
                    for raw_key, raw_color in keyword_colors.items():
                        if str(raw_key).casefold() == word.casefold():
                            override = raw_color
                            break
            color_by_key[word.casefold()] = HyperframesCaptionRenderer._hex_color(
                override,
                accent,
            )

        fragments: list[str] = []
        for fragment in matcher.split(text):
            if not fragment:
                continue
            escaped = escape_fragment(fragment)
            key = fragment.casefold()
            if key in color_by_key:
                color = color_by_key[key]
                if highlight_style == "badge":
                    fragments.append(
                        f'<span class="highlight highlight-badge" '
                        f'style="background:{html.escape(color)};color:#17110a">{escaped}</span>'
                    )
                else:
                    fragments.append(
                        f'<span class="highlight highlight-{html.escape(highlight_style)}" '
                        f'style="color:{html.escape(color)}">{escaped}</span>'
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
