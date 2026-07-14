from pathlib import Path


def test_workspace_uses_mobile_drawers_and_desktop_collapse_controls():
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    console = Path("frontend/src/components/ConsolePanel.tsx").read_text(encoding="utf-8")

    assert "sidebarOpen" in app
    assert "consoleOpen" in app
    assert "lg:static" in app
    assert "打开导航" in app
    assert "打开任务面板" in app
    assert "isOpen" in console and "onClose" in console


def test_tab_changes_reset_the_workspace_scroll_position():
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "mainScrollRef" in app
    assert "mainScrollRef.current?.scrollTo" in app
    assert "[activeTab]" in app


def test_service_status_is_truthful_and_fake_language_toggle_is_removed():
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "settings.llm.provider" in app
    assert "serviceStatus.llm" in app
    assert "LLM Connected" not in app
    assert "BizyAir Ready" not in app
    assert "setLang" not in app
    assert "serviceStatus.minimax" in app
    assert "MiniMax TTS" in app


def test_changed_form_controls_have_associated_labels_and_visible_delete_action():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert 'htmlFor="quick-create-title"' in quick_create
    assert 'id="quick-create-title"' in quick_create
    assert "opacity-0 group-hover:opacity-100" not in quick_create
    assert 'aria-label={`删除分镜 ${idx + 1}`}' in quick_create
    assert 'htmlFor={`scene-narration-${scene.id}`}' in quick_create
    assert 'htmlFor={`scene-visual-${scene.id}`}' in quick_create


def test_keyboard_focus_is_globally_visible():
    css = Path("frontend/src/index.css").read_text(encoding="utf-8")

    assert ":focus-visible" in css
    assert "outline" in css
