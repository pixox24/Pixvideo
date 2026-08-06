from pathlib import Path

from pixelle_video.services.hyperframes_caption_renderer import HyperframesCaptionRenderer


def test_caption_plan_uses_style_segmentation_and_canvas_dimensions():
    renderer = HyperframesCaptionRenderer()

    plan = renderer.build_caption_plan(
        text="第一句旁白。第二句旁白。",
        duration=4.0,
        width=1080,
        height=1920,
        fps=30,
        style={
            "mode": "hyperframes",
            "fontSize": 64,
            "segmentMode": "sentence",
            "animation": "pop",
        },
    )

    assert plan.canvas == {"width": 1080, "height": 1920, "fps": 30}
    assert plan.duration_ms == 4000
    # Punctuation is a split point only; it is not shown on captions.
    assert [segment.text for segment in plan.captions] == ["第一句旁白", "第二句旁白"]
    assert plan.captions[0].start_ms == 0
    assert plan.captions[-1].end_ms == 4000
    assert plan.style["animation"] == "pop"


def test_prepared_project_uses_custom_font_and_escaped_caption_text(tmp_path):
    font_path = tmp_path / "字体.ttf"
    font_path.write_bytes(b"font-bytes")
    renderer = HyperframesCaptionRenderer()
    plan = renderer.build_caption_plan(
        text="<script>不要执行</script>",
        duration=2.0,
        width=720,
        height=1280,
        fps=24,
        style={
            "mode": "hyperframes",
            "fontFamily": "品牌字体",
            "fontPath": str(font_path),
            "preset": "caption-box",
        },
    )

    project_dir = renderer.prepare_project(plan, tmp_path / "project")
    composition = (project_dir / "compositions" / "caption-overlay.html").read_text(
        encoding="utf-8"
    )

    assert (project_dir / "assets" / font_path.name).read_bytes() == b"font-bytes"
    assert (project_dir / "index.html").read_text(encoding="utf-8") == composition
    assert "@font-face" in composition
    assert "assets/" + font_path.name in composition
    assert "<script>不要执行" not in composition
    assert "&lt;script&gt;" in composition
    assert "ript&gt;" in composition
    assert "data-composition-id=\"dynamic-caption-overlay\"" in composition


def test_composition_limits_dynamic_font_size_to_the_requested_line_length(tmp_path):
    renderer = HyperframesCaptionRenderer()
    plan = renderer.build_caption_plan(
        text="让每一帧，都更有表达力。",
        duration=1.2,
        width=360,
        height=640,
        fps=24,
        style={
            "mode": "hyperframes",
            "fontSize": 38,
            "maxCharsPerLine": 8,
            "maxLines": 2,
        },
    )

    project_dir = renderer.prepare_project(plan, tmp_path / "project")
    composition = (project_dir / "compositions" / "caption-overlay.html").read_text(
        encoding="utf-8"
    )

    assert "font-size: 32px" in composition
    assert "white-space: nowrap" in composition


def test_composition_renders_manual_highlights_and_staggered_emphasis(tmp_path):
    renderer = HyperframesCaptionRenderer()
    plan = renderer.build_caption_plan(
        text="让重点在恰好的时刻出现，表达力更强。",
        duration=2.4,
        width=1080,
        height=1920,
        fps=30,
        style={
            "mode": "hyperframes",
            "animation": "word-pop",
            "highlightWords": ["表达力", "重点"],
            "highlightStyle": "badge",
            "highlightScale": 135,
            "backgroundOpacity": 45,
            "preset": "caption-box",
            "alignment": 3,
            "shadow": 4,
        },
    )

    project_dir = renderer.prepare_project(plan, tmp_path / "project")
    composition = (project_dir / "compositions" / "caption-overlay.html").read_text(
        encoding="utf-8"
    )

    assert "highlight-badge" in composition
    assert ">重点</span>" in composition
    assert ">表达力</span>" in composition
    assert "scale: 1.35" in composition
    assert "stagger: 0.08" in composition
    assert "rgba(0, 0, 0, 0.45)" in composition
    assert "text-align: right" in composition
    assert "text-shadow: 4px 4px 8px" in composition
    # Ease-out should be present on the timeline.
    assert 'ease: "power2.in"' in composition


def test_caption_plan_keeps_highlighted_phrase_intact_across_phrase_boundaries():
    renderer = HyperframesCaptionRenderer()

    plan = renderer.build_caption_plan(
        text="一二三表达力",
        duration=2.0,
        width=1080,
        height=1920,
        fps=30,
        style={
            "mode": "hyperframes",
            "segmentMode": "phrase",
            "maxCharsPerLine": 4,
            "maxLines": 1,
            "highlightWords": ["表达力"],
        },
    )

    assert [caption.text.replace("\n", "") for caption in plan.captions] == ["一二三", "表达力"]


def test_caption_plan_uses_proportional_timing_for_uneven_sentences():
    renderer = HyperframesCaptionRenderer()
    plan = renderer.build_caption_plan(
        text="短。这是一句明显更长的旁白内容。",
        duration=4.0,
        width=1080,
        height=1920,
        fps=30,
        style={"mode": "hyperframes", "segmentMode": "sentence", "maxCharsPerLine": 20, "maxLines": 2},
    )
    assert len(plan.captions) == 2
    first_dur = plan.captions[0].end_ms - plan.captions[0].start_ms
    second_dur = plan.captions[1].end_ms - plan.captions[1].start_ms
    assert first_dur < second_dur
    assert plan.captions[-1].end_ms == 4000


def test_render_overlay_runs_pinned_cli_and_returns_webm(monkeypatch, tmp_path):
    renderer = HyperframesCaptionRenderer()
    plan = renderer.build_caption_plan(
        text="动态字幕",
        duration=1.0,
        width=360,
        height=640,
        fps=24,
        style={"mode": "hyperframes"},
    )
    captured: dict[str, object] = {}

    def fake_run(command, cwd, check, capture_output, text, timeout):
        captured["command"] = command
        captured["cwd"] = cwd
        Path(cwd, "caption-overlay.webm").write_bytes(b"webm")

    monkeypatch.setattr("pixelle_video.services.hyperframes_caption_renderer.subprocess.run", fake_run)

    output = renderer.render_overlay(plan, tmp_path)

    assert output == str(tmp_path / "caption-overlay.webm")
    assert Path(output).read_bytes() == b"webm"
    assert captured["command"] == [
        "npx",
        "--yes",
        "hyperframes@0.7.48",
        "render",
        ".",
        "--composition",
        "compositions/caption-overlay.html",
        "--format",
        "webm",
        "--output",
        "caption-overlay.webm",
        "--fps",
        "24",
        "--quality",
        "draft",
        "--workers",
        "1",
        "--strict",
    ]
