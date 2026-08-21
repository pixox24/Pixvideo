import json
from pathlib import Path

from pixelle_video.utils.storyboard_split import (
    STORYBOARD_SCENE_MAX,
    heal_mid_cuts,
    soft_expand_by_pause,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "storyboard_contract.json"
FRONTEND_SPLIT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "storyboardSplit.ts"


def test_scene_max_is_aligned_between_python_and_typescript():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    frontend = FRONTEND_SPLIT.read_text(encoding="utf-8")
    assert STORYBOARD_SCENE_MAX == payload["sceneMax"] == 100
    assert "export const STORYBOARD_SCENE_MAX = 100;" in frontend


def test_shared_storyboard_contract_cases():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fns = {
        "soft_expand_by_pause": soft_expand_by_pause,
        "heal_mid_cuts": heal_mid_cuts,
    }
    for case in payload["cases"]:
        result = fns[case["fn"]](case["input"])
        if "expected" in case:
            assert result == case["expected"], case["name"]
        if "expectedContains" in case:
            assert any(case["expectedContains"] in item for item in result), case["name"]
