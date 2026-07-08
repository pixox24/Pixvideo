from pathlib import Path


def test_completed_video_previews_preserve_actual_aspect_ratio():
    preview_component = Path("frontend/src/components/VideoPreview.tsx")
    assert preview_component.exists()

    component = preview_component.read_text()
    assert "aspect-square" in component
    assert "object-contain" in component
    assert "object-cover" not in component

    console_panel = Path("frontend/src/components/ConsolePanel.tsx").read_text()
    history_list = Path("frontend/src/components/HistoryList.tsx").read_text()

    assert 'from "./VideoPreview"' in console_panel
    assert 'from "./VideoPreview"' in history_list
    assert "<VideoPreview" in console_panel
    assert "<VideoPreview" in history_list
