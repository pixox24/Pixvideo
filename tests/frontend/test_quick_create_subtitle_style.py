from pathlib import Path


def test_quick_create_exposes_subtitle_style_controls():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "subtitleStyle" in component
    assert "字幕样式" in component
    assert "自定义字体文件夹" in component
    assert "fontPath" in component
    assert "fontSize" in component
    assert "primaryColor" in component
    assert "outlineColor" in component


def test_video_payload_sends_subtitle_style():
    api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")

    assert "subtitle_style" in api
    assert "input.subtitleStyle" in api


def test_quick_create_fetches_font_resources():
    api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")
    types = Path("frontend/src/types.ts").read_text(encoding="utf-8")

    assert 'fetchJson<any>("/api/resources/fonts")' in api
    assert "fonts: FontOption[]" in types
