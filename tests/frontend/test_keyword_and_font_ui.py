from pathlib import Path


def test_quick_create_exposes_keyword_color_editor_and_ai_extract():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")

    assert "字幕高亮词（可选）" in component
    assert "AI 抽词" in component
    assert "keywordColors" in component
    assert "extractHighlightKeywords" in component
    assert "aiKeywordSuggestions" in component
    assert "keywordPreferences" in component
    assert "换一批" in component
    assert component.count("renderKeywordExtractionPanel") >= 3
    assert "抽词选项" in component
    assert "ui-chip" in component
    assert 'type="color"' in component
    assert "/api/content/keywords" in api


def test_keyword_editor_lives_in_content_and_style_is_read_only():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "去内容里改词" in component
    assert "去内容里添加" in component
    assert "未选高亮词" in component
    assert "mode !== \"ai\" && renderSelectedKeywordEditor()" not in component
    assert "已选 {(subtitleStyle.highlightWords || []).length} 个词 · 编辑" not in component


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
