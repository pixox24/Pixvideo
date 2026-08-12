from pathlib import Path


def test_workbench_surfaces_failed_scenes_and_targeted_retry():
    source = (Path(__file__).parents[2] / "frontend/src/components/ProgressObservatory.tsx").read_text(encoding="utf-8")
    workbench = (Path(__file__).parents[2] / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")

    assert "重试失败" in source
    assert "重试导出" in source
    assert "onLocateScene" in source
    assert "onLocateScene=" in workbench
    assert "ProgressObservatory" in workbench
