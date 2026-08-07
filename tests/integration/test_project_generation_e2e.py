import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "services"))
from pixelle_video.models.workbench import GenerationRunStatus
from tests.services.project_generation_fixtures import FakeSceneBehavior
from tests.services.test_project_generation_service import _setup


async def _wait_terminal(repository, run_id):
    for _ in range(200):
        run = repository.get_generation_run(run_id)
        if run and run.is_terminal:
            return run
        await asyncio.sleep(0.005)
    raise AssertionError("run did not finish")


@pytest.mark.asyncio
async def test_three_scene_failure_retry_and_candidate_flow(tmp_path):
    provider, _, repository, _, service, _ = _setup(
        tmp_path,
        {"scene-1": FakeSceneBehavior(tts_error="temporary")},
        scene_count=3,
    )

    first = await service.start("project-1")
    failed = await _wait_terminal(repository, first.run_id)
    assert failed.status == GenerationRunStatus.COMPLETED_WITH_FAILURES
    assert [call.scene_id for call in provider.completed_calls] == ["scene-0", "scene-0", "scene-2", "scene-2"]

    provider.behaviors["scene-1"].tts_error = None
    retry = await service.retry_failed(first.run_id)
    completed = await _wait_terminal(repository, retry.run_id)
    assert completed.status == GenerationRunStatus.COMPLETED
    assert [item.scene_id for item in repository.list_generation_run_items(retry.run_id)] == ["scene-1"]
    repository.close()
