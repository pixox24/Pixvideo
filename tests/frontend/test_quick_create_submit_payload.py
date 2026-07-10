from pathlib import Path


def test_video_payload_preserves_each_scene_as_one_backend_segment():
    api = Path("frontend/src/lib/api.ts").read_text()

    assert 'const text = sceneTexts.join("\\n\\n") || input.title;' in api
    assert 'split_mode: scenes.length > 0 ? "paragraph" : input.splitType || "line"' in api
