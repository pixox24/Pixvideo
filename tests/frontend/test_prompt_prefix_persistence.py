import re
from pathlib import Path


def test_saved_prompt_prefix_updates_active_preset_for_quick_create_remount():
    app = Path("frontend/src/App.tsx").read_text()
    match = re.search(
        r"const handleSavePromptPrefix = async.*?^  // Delete task handler",
        app,
        flags=re.S | re.M,
    )

    assert match is not None
    assert "setActivePreset(savedPreset)" in match.group(0)


def test_quick_create_same_preset_refreshes_only_prompt_prefix():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text()

    assert "lastAppliedPresetId" in component
    assert "lastAppliedPresetId.current === activePreset.id" in component
    assert "setPromptPrefix(activePreset.promptPrefix);" in component
