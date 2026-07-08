from pathlib import Path


def test_manual_scene_editor_uses_resizable_textareas_for_long_text():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text()

    assert "分镜配音旁白 (TTS Text)" in component
    assert "画面视觉绘图 Prompt (英文最佳)" in component
    assert component.count("resize-y max-h-48") >= 2
    assert component.count("rows={3}") >= 5
