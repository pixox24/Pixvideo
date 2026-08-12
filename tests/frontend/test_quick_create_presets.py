from pathlib import Path


def test_app_supports_multi_preset_api_actions():
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "defaultPresetId" in app
    assert "handleCreatePreset" in app
    assert "handleUpdatePreset" in app
    assert "handleDeletePreset" in app
    assert "handleSetDefaultPreset" in app
    assert 'fetch("/api/presets",' in app
    assert 'fetch(`/api/presets/${presetId}`' in app
    assert 'fetch(`/api/presets/${presetId}/default`' in app
    assert 'fetch(`/api/presets/${presetId}`' in app and 'method: "DELETE"' in app
    assert "setActivePreset(data.preset)" in app


def test_quick_create_exposes_full_workbench_preset_controls():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "presetNameDraft" in component
    assert "presetMenuOpen" in component
    assert "buildWorkbenchPreset" in component
    assert "onCreatePreset" in component
    assert "onUpdatePreset" in component
    assert "onDeletePreset" in component
    assert "onSetDefaultPreset" in component
    assert "工作台预设" in component
    assert "另存为" in component
    assert "覆盖当前预设" in component
    assert "设为默认" in component
    assert "删除预设" in component


def test_quick_create_preset_payload_includes_global_workbench_parameters_only():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "sceneCount: aiSceneCount" in component
    assert "copyCharCount" in component
    assert "copyCharCountMode" in component
    assert "copyDraftMode" in component
    assert "mediaWidth: imageWidth" in component
    assert "mediaHeight: imageHeight" in component
    assert "videoFps" in component
    assert "imageAspectRatio" in component
    assert "subtitleStyle" in component
    assert "aiTopic:" not in component
    assert "copyDraft:" not in component
    assert "previewTtsText:" not in component
