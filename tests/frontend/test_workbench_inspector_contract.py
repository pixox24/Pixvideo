from pathlib import Path


def test_inspector_keeps_candidate_selection_explicit():
    source = (Path(__file__).parents[2] / "frontend/src/components/SceneInspector.tsx").read_text(encoding="utf-8")
    assert "使用此版本" in source
    assert "currentVersionId" in source
    assert "onRegenerateImage" in source
    assert "onUpload" in source
    assert "500" in source

