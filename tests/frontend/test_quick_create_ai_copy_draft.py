from pathlib import Path


def test_quick_create_ai_mode_has_editable_copy_draft_step():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "copyDraftMode" in component
    assert "setCopyDraftMode" in component
    assert "copyDraft" in component
    assert "setCopyDraft" in component
    assert "整篇口播稿" in component
    assert "分镜旁白列表" in component
    assert "AI 生成文案草稿" in component
    assert "生成口播稿草稿" in component
    assert "生成分镜旁白草稿" in component
    assert "基于确认文案生成 AI 分镜脚本" in component


def test_quick_create_calls_copy_draft_and_confirmed_script_endpoints():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert 'fetch("/api/generate-copy-draft"' in component
    assert "draftMode: copyDraftMode" in component
    assert "targetCharCount: copyCharCount" in component
    assert "charCountMode: copyCharCountMode" in component
    assert "confirmedText: copyDraft.trim()" in component


def test_quick_create_exposes_total_copy_length_controls_using_storyboards():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "suggestCopyCharCount" in component
    assert "copyCharCount" in component
    assert "copyCharCountMode" in component
    assert "文案总字数" in component
    assert "字左右" in component
    assert "字以内" in component
    assert "每分镜约" in component
    assert "预计口播" in component
    assert "分镜切片数量: {aiSceneCount} 个分镜" in component
    assert "建议 5-10 个分镜" in component


def test_quick_create_render_uses_confirmed_copy_in_ai_mode():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "buildScenesForRender" in component
    assert "const renderScenes = buildScenesForRender()" in component
    assert "scenes: renderScenes" in component
    assert "请先生成或填写确认文案，再开始生成视频" in component
    assert 'visualPrompt: "Creative visualization of: " + aiTopic' not in component
