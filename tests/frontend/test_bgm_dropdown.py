from pathlib import Path


def test_quick_create_bgm_panel_uses_dropdown_and_custom_folder_entry():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text()

    assert "FolderOpen" in component
    assert "openCustomBgmFolder" in component
    assert 'fetch("/api/resources/bgm/select-folder"' in component
    assert "await onRefreshResources();" in component
    assert "bgmPreviewRef" in component
    assert "<audio" in component
    assert "controls" in component
    assert "await audio.play()" in component
    assert "onChange={(e) => handleBgmChange(e.target.value)}" in component
    assert 'name="bgmRadio"' not in component
