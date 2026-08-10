from pathlib import Path


def test_quick_create_exposes_keyword_color_editor_and_ai_extract():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")

    assert "AI 自动抽词" in component
    assert "keywordColors" in component
    assert "extractHighlightKeywords" in component
    assert "aiKeywordSuggestions" in component
    assert "keywordPreferences" in component
    assert "换一批" in component
    assert component.count("AI 自动抽词") == 1
    assert 'type="color"' in component
    assert "/api/content/keywords" in api


def test_font_select_loads_real_font_faces():
    component = Path("frontend/src/components/FontSelect.tsx").read_text(encoding="utf-8")
    quick = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "FontFace" in component
    assert "/api/resources/fonts/file?path=" in component
    assert "FontSelect" in quick
    assert "previewText" in component


def test_content_keywords_route_is_registered():
    router = Path("api/routers/content.py").read_text(encoding="utf-8")
    schemas = Path("api/schemas/content.py").read_text(encoding="utf-8")

    assert '"/keywords"' in router or "'/keywords'" in router
    assert "KeywordExtractRequest" in schemas
    assert "generate_highlight_keywords" in router
