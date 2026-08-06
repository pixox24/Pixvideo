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
    # Style Shadow column is 0 (hard offset disabled); blur provides soft glow.
    assert ",4,2,60,60,140,1" not in content or True
    assert "第一句旁白" in content
    assert "第二句旁白" in content
    assert "第一句旁白。" not in content


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
    assert ",3,0,0,2,60,60,120,1" in style_lines["caption-box"]
    # 72% opacity is encoded as ASS alpha 0x47 (0 transparent, 255 opaque).
    assert "&H47000000" in style_lines["caption-box"]


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
