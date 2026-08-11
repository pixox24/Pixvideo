"""PR-F: System settings soft-dark cards."""

from pathlib import Path

SETTINGS = Path("frontend/src/components/SystemSettingsTab.tsx").read_text(encoding="utf-8")


def test_settings_uses_ui_card_and_input():
    assert "ui-card" in SETTINGS
    assert "ui-input" in SETTINGS
    assert "ui-btn-primary" in SETTINGS
    assert "ui-btn-secondary" in SETTINGS


def test_settings_preserves_save_and_test_actions():
    assert "onSaveSettings" in SETTINGS
    assert "testConnection" in SETTINGS
    assert "保存所有设置" in SETTINGS
    assert "测试 LLM 连接" in SETTINGS
    assert "测试 MiniMax" in SETTINGS or "MiniMax" in SETTINGS
    assert "mimoKey" in SETTINGS


def test_settings_sections_present():
    for marker in ["语言模型", "图片生成", "ComfyUI", "RunningHub", "MiMo"]:
        assert marker in SETTINGS
