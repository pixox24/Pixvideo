"""PR-D: workbench stage-first chrome (UI only)."""

from pathlib import Path

WB = Path("frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
QUEUE = Path("frontend/src/components/GenerationQueue.tsx").read_text(encoding="utf-8")
RUN = Path("frontend/src/components/ProgressObservatory.tsx").read_text(encoding="utf-8")


def test_workbench_has_project_settings_drawer_and_stage():
    assert "projectSettingsOpen" in WB
    assert "项目设置" in WB
    assert "ui-stage" in WB
    assert "rounded-full bg-amber-500" in WB  # circular play
    assert "audioRef" in WB
    assert "bgmAudioRef" in WB
    assert "togglePlay" in WB


def test_bgm_settings_moved_out_of_permanent_top_bar():
    # Drawer content still has BGM controls
    assert "背景音乐" in WB or "settings.bgm" in WB
    assert "enableSubtitles" in WB
    assert "saveSettings" in WB


def test_generation_queue_is_collapsible():
    assert "expanded" in QUEUE
    assert "onToggle" in QUEUE
    assert "queueExpanded" in WB


def test_run_panel_uses_ui_buttons():
    assert "ui-btn-primary" in RUN
    assert "配音" in RUN and "画面" in RUN and "编码" in RUN
    assert "ProgressObservatory" in WB or "progress" in WB.lower()
