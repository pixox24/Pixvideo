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


def test_create_ass_file_contains_style_and_dialogues(tmp_path):
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
        },
        output_dir=tmp_path,
    )

    content = Path(ass_path).read_text(encoding="utf-8")
    assert "[V4+ Styles]" in content
    assert "Style: Default,PingFang SC,56" in content
    assert "Dialogue:" in content
    assert r"\fad(120,120)" in content
    assert "第一句旁白" in content
    assert "第二句旁白" in content
