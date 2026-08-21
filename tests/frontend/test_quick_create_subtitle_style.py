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


def test_subtitle_preview_loads_a_selected_font_through_the_resource_api():
    component = Path("frontend/src/components/SubtitleStylePreview.tsx").read_text(
        encoding="utf-8"
    )

    assert "/api/resources/fonts/file?path=" in component
    assert "new FontFace" in component


def test_quick_create_exposes_dynamic_subtitle_mode():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    types = Path("frontend/src/types.ts").read_text(encoding="utf-8")

    assert "动态字幕" in component
    assert 'value="hyperframes"' in component
    assert 'const dynamicSubtitleEnabled = subtitleStyle.mode === "hyperframes"' in component
    assert "subtitleStyle," in component
    assert '"hyperframes"' in types


def test_quick_create_exposes_dynamic_highlight_controls():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    types = Path("frontend/src/types.ts").read_text(encoding="utf-8")

    assert "高亮词" in component
    assert "高亮样式" in component
    assert "高亮缩放" in component
    assert 'value="pop"' in component
    assert "highlightWords" in types
    assert "highlightStyle" in types
    assert "backgroundOpacity" in types
    assert "底色透明度" in component
    assert "去内容里改词" in component
