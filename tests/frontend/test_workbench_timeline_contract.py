from pathlib import Path


def test_timeline_has_audio_driven_clips_and_reorder_controls():
    source = (Path(__file__).parents[2] / "frontend/src/components/WorkbenchTimeline.tsx").read_text(encoding="utf-8")
    assert "effectiveSceneDuration" in source
    assert "Math.max(48" in source
    assert "onReorder" in source
    assert "manualHoldSeconds" in source
    assert "draggable" in source
    assert "window.setTimeout(() => onHold(sceneId, value), 350)" in source
