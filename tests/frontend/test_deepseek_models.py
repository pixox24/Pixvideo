from pathlib import Path


def test_deepseek_model_dropdown_uses_v4_models():
    component = Path("frontend/src/components/SystemSettingsTab.tsx").read_text(encoding="utf-8")

    assert 'value="deepseek-v4-pro"' in component
    assert 'value="deepseek-v4-flash"' in component
    assert 'value="deepseek-chat"' not in component
    assert 'value="deepseek-coder"' not in component
