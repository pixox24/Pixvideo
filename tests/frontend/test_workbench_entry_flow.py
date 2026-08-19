from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_quick_create_exposes_project_entry_callback():
    source = (ROOT / "frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    assert "onCreateProject" in source
    assert "onGenerateTask" in source
    assert 'handleTriggerRender(true)' in source
    assert "onCreateProject({" in source
    # Visual prompts must be explicit; narration must never be used as a
    # silent fallback because that produces semantically unrelated imagery.
    assert "const missingVisualPrompts = renderScenes.filter" in source
    assert "请先点击“按当前导演设置生成分镜”" in source
    assert "visualPrompt: scene.visualPrompt.trim()" in source
    # Labels may live in CreateStickyFooter (PR-C)
    footer = (ROOT / "frontend/src/components/quickCreate/CreateStickyFooter.tsx").read_text(encoding="utf-8")
    assert "仅生成成片" in source or "仅生成成片" in footer
    assert "生成初稿并打开工作台" in source or "生成初稿并打开工作台" in footer


def test_app_registers_project_workbench_tab():
    source = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert 'activeTab === "project-workbench"' in source
    assert "activeProjectId" in source


def test_workbench_exposes_project_settings_and_debounced_holds():
    workbench = (ROOT / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
    timeline = (ROOT / "frontend/src/components/WorkbenchTimeline.tsx").read_text(encoding="utf-8")

    assert "patchProject" in workbench
    assert "BGM" in workbench
    assert "enableSubtitles" in workbench
    assert "beforeunload" in workbench
    assert "window.setTimeout(() => onHold(sceneId, value), 350)" in timeline
