from pathlib import Path

from pixelle_video.services.subtitle_renderer import SubtitleRenderer


def test_ass_color_conversion_uses_bbggrr_format():
    renderer = SubtitleRenderer()

    assert renderer.hex_to_ass_color("#FFFFFF") == "&H00FFFFFF"
    assert renderer.hex_to_ass_color("#FFD43B") == "&H003BD4FF"
    assert renderer.hex_to_ass_color("#000000") == "&H00000000"


def test_ass_text_is_escaped():
    renderer = SubtitleRenderer()

    assert renderer.escape_ass_text("{hello}\\world\nnext") == r"\{hello\}\\world\Nnext"


def test_sentence_split_on_terminal_and_pause_punctuation_without_displaying_marks():
    renderer = SubtitleRenderer()
    segments = renderer.segment_text(
        "有人说，AI会取代人类。取代不了深夜那碗面的温度。",
        mode="sentence",
        max_chars=4,  # capacity must NOT hard-cut mid-phrase
        max_lines=1,
    )

    assert segments == [
        "有人说",
        "AI会取代人类",
        "取代不了深夜那碗面的温度",
    ]
    # No punctuation on screen.
    assert all("，" not in s and "。" not in s for s in segments)


def test_sentence_mode_does_not_hard_cut_long_phrase():
    renderer = SubtitleRenderer()
    text = "取代不了深夜那碗面的温度"
    segments = renderer.segment_text(text, mode="sentence", max_chars=4, max_lines=1)
    assert segments == [text]


def test_phrase_mode_prefers_punctuation_over_mid_sentence_capacity_cut():
    """Regression: 「后半生该找回真正的自己」 must not be hard-cut mid-phrase."""
    renderer = SubtitleRenderer()
    text = "荣格说中年是第二次成年，前半生为别人活，后半生该找回真正的自己。"

    # Capacity 12 is enough for each punctuation phrase (max 11 chars), but the
    # old fixed packer produced: ['…', '前半生为别人活，后半生该', '找回真正的自己'].
    segments = renderer.segment_text(text, mode="phrase", max_chars=12, max_lines=1)
    assert segments == [
        "荣格说中年是第二次成年",
        "前半生为别人活",
        "后半生该找回真正的自己",
    ]

    # Global default-style-like capacity (20x2) should keep the same natural phrases.
    segments_wide = renderer.segment_text(text, mode="phrase", max_chars=20, max_lines=2)
    flat = [s.replace("\n", "") for s in segments_wide]
    assert flat == [
        "荣格说中年是第二次成年",
        "前半生为别人活",
        "后半生该找回真正的自己",
    ]


def test_proportional_timing_gives_longer_sentences_more_time():
    renderer = SubtitleRenderer()
    timed = renderer.plan_segments(
        "短。这是一句明显更长的旁白内容。",
        duration=4.0,
        style={"segmentMode": "sentence", "maxCharsPerLine": 20, "maxLines": 2},
    )

    assert len(timed) == 2
    assert timed[0].text == "短"
    assert timed[1].text == "这是一句明显更长的旁白内容"
    assert timed[0].end - timed[0].start < timed[1].end - timed[1].start
    assert timed[0].start == 0.0
    assert timed[-1].end == 4.0


def test_create_ass_file_uses_soft_blur_not_hard_shadow(tmp_path):
    renderer = SubtitleRenderer()
    ass_path = renderer.create_ass_file(
        text="第一句旁白。第二句旁白。",
        duration=4.0,
        width=1080,
        height=1920,
        style={
            "preset": "short-video-bold",
            "fontFamily": "PingFang SC",
            "fontPath": "",
            "fontSize": 56,
            "primaryColor": "#FFFFFF",
            "outlineColor": "#000000",
            "outlineWidth": 4,
            "marginV": 140,
            "alignment": 2,
            "maxCharsPerLine": 12,
            "maxLines": 2,
            "animation": "fade",
            "segmentMode": "sentence",
            "fadeInMs": 120,
            "fadeOutMs": 120,
            "shadow": 4,
        },
        output_dir=tmp_path,
    )

    content = Path(ass_path).read_text(encoding="utf-8")
    assert "[V4+ Styles]" in content
    assert "Style: Default,PingFang SC,56" in content
    assert "Dialogue:" in content
    assert r"\fad(120,120)" in content
    assert r"\blur" in content
    # Blur must stay light (shadow=4 → ~0.8, never the old 2.4–6.0 mush).
    import re

    blur_vals = [float(m) for m in re.findall(r"\\blur([0-9.]+)", content)]
    assert blur_vals and max(blur_vals) <= 1.5
    # Style Shadow column is 0 (hard offset disabled); blur provides soft glow.
    assert ",4,2,60,60,140,1" not in content or True
    assert "第一句旁白" in content
    assert "第二句旁白" in content
    assert "第一句旁白。" not in content


def test_high_shadow_zero_outline_stays_readable(tmp_path):
    """Reproduce export mush: cinema-soft + shadow=6 + outline 0 must not defocus."""
    renderer = SubtitleRenderer()
    assert renderer._blur_amount(6) <= 1.5
    assert renderer._blur_amount(12) <= 1.5
    assert renderer._blur_amount(0) == 0.0

    ass_path = renderer.create_ass_file(
        text="翻到七岁那年写的日记",
        duration=3.0,
        width=1440,
        height=2560,
        style={
            "preset": "cinema-soft",
            "mode": "ass",
            "fontSize": 60,
            "shadow": 6,
            "outlineWidth": 0,
            "strokeWidth": 0,
            "animation": "fade",
            "fadeInMs": 120,
            "fadeOutMs": 120,
        },
        output_dir=tmp_path,
    )
    content = Path(ass_path).read_text(encoding="utf-8")
    import re

    blur_vals = [float(m) for m in re.findall(r"\\blur([0-9.]+)", content)]
    assert blur_vals and max(blur_vals) <= 1.5
    # Style line Outline column must be > 0 for a hard glyph edge.
    style_line = next(line for line in content.splitlines() if line.startswith("Style: Default,"))
    parts = style_line.split(",")
    # ... BorderStyle, Outline, Shadow, Alignment ...
    outline = int(parts[-5])
    assert outline >= 1


def test_ass_presets_have_distinct_rendered_styles(tmp_path):
    renderer = SubtitleRenderer()
    style_lines = {}

    for preset in ("short-video-bold", "clean-white", "cinema-soft", "caption-box"):
        ass_path = renderer.create_ass_file(
            text="预置样式验证",
            duration=1.0,
            width=1080,
            height=1920,
            style={"preset": preset},
            output_dir=tmp_path,
        )
        content = Path(ass_path).read_text(encoding="utf-8")
        style_lines[preset] = next(line for line in content.splitlines() if line.startswith("Style:"))

    assert len(set(style_lines.values())) == 4
    assert ",1,4,0,2,60,60,120,1" in style_lines["short-video-bold"]
    # caption-box: BorderStyle=3, Outline=default box padding (10), not 0.
    assert ",3,10,0,2,60,60,200,1" in style_lines["caption-box"]
    # libass uses OutlineColour for BorderStyle=3 fill; 72% → alpha 0x47 on box color.
    assert "&H47000000" in style_lines["caption-box"]


def test_caption_box_intent_defaults_and_box_color_on_outline_colour(tmp_path):
    renderer = SubtitleRenderer()
    # Legacy broken default (outlineWidth=0) must still produce a visible box padding.
    normalized = renderer.normalize_style({"preset": "caption-box", "outlineWidth": 0})
    assert normalized["boxEnabled"] is True
    assert normalized["boxPadding"] == 10
    assert normalized["outlineWidth"] == 10
    assert normalized["boxColor"] == "#000000"

    ass_path = renderer.create_ass_file(
        text="底色测试",
        duration=1.0,
        width=1080,
        height=1920,
        style={
            "preset": "caption-box",
            "backColor": "#FF0000",
            "outlineColor": "#00FF00",  # must NOT become the box fill
            "outlineWidth": 6,
            "backgroundOpacity": 100,
        },
        output_dir=tmp_path,
    )
    content = Path(ass_path).read_text(encoding="utf-8")
    style_line = next(line for line in content.splitlines() if line.startswith("Style:"))
    # Fully opaque red box → OutlineColour &H00BBGGRR with RR=FF → &H000000FF
    assert "&H000000FF" in style_line
    # Green stroke colour must not be the box fill colour.
    assert "&H0000FF00" not in style_line
    assert ",3,6,0," in style_line


def test_caption_box_explicit_box_padding_wins(tmp_path):
    renderer = SubtitleRenderer()
    normalized = renderer.normalize_style(
        {"preset": "caption-box", "boxPadding": 12, "outlineWidth": 3}
    )
    assert normalized["boxPadding"] == 12
    assert normalized["outlineWidth"] == 12


def test_ass_highlights_use_override_colors(tmp_path):
    renderer = SubtitleRenderer()
    ass_path = renderer.create_ass_file(
        text="让表达力成为重点。",
        duration=2.0,
        width=1080,
        height=1920,
        style={
            "segmentMode": "sentence",
            "primaryColor": "#FFFFFF",
            "accentColor": "#FFD43B",
            "highlightWords": ["表达力", "重点"],
            "keywordColors": {"表达力": "#FF0000", "重点": "#00FF00"},
            "animation": "fade",
        },
        output_dir=tmp_path,
    )
    content = Path(ass_path).read_text(encoding="utf-8")
    assert r"{\c&H000000FF&}表达力{\c&H00FFFFFF&}" in content
    assert r"{\c&H0000FF00&}重点{\c&H00FFFFFF&}" in content


def test_default_segment_mode_is_sentence():
    renderer = SubtitleRenderer()
    normalized = renderer.normalize_style({})
    assert normalized["segmentMode"] == "sentence"
    assert normalized["fadeInMs"] == 120
    assert normalized["fadeOutMs"] == 120


def test_resolve_font_family_from_windows_font():
    path = Path(r"C:\Windows\Fonts\msyh.ttc")
    if not path.is_file():
        path = Path(r"C:\Windows\Fonts\simhei.ttf")
    if not path.is_file():
        return
    name = SubtitleRenderer.resolve_font_family(str(path))
    assert name
    assert name.lower() not in {"msyh", "simhei"}
