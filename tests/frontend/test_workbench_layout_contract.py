from pathlib import Path


def test_workbench_layout_has_scene_preview_inspector_and_queue_regions():
    root = Path(__file__).parents[2] / "frontend/src/components"
    workbench = (root / "ProjectWorkbench.tsx").read_text(encoding="utf-8")
    inspector = (root / "SceneInspector.tsx").read_text(encoding="utf-8")
    assert "SceneList" in workbench
    assert "SceneInspector" in workbench
    assert "GenerationQueue" in workbench
    for marker in ["画面预览", "提示词", "重新生成"]:
        assert marker in (workbench + inspector)
    assert "audioRef" in workbench
    assert "togglePlay" in workbench
    assert "上一个分镜" in workbench
    assert "下一个分镜" in workbench
    assert "ui-panel" in inspector
