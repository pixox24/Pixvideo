from pathlib import Path


def test_workbench_batch_toolbar_has_selection_prefix_and_generation():
    source = (Path(__file__).parents[2] / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
    scene_list = (Path(__file__).parents[2] / "frontend/src/components/SceneList.tsx").read_text(encoding="utf-8")
    assert "批量重新生成" in source
    assert "提示词前缀" in source
    assert "selectedSceneIds" in source
    assert "type=\"checkbox\"" in scene_list

