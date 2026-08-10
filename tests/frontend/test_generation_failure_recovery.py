from pathlib import Path


def test_workbench_surfaces_failed_scenes_and_targeted_retry():
    source = (Path(__file__).parents[2] / "frontend/src/components/GenerationRunPanel.tsx").read_text(encoding="utf-8")
    workbench = (Path(__file__).parents[2] / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")

    assert "failedItems" in source
    assert 'role="alert"' in source
    assert "仅重试失败项" in source
    assert "onLocateFailure" in source
    assert "onLocateFailure={(sceneId)" in workbench
