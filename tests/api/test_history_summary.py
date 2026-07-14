import pytest

from api.routers import history


class DetailHistory:
    async def get_task_detail(self, task_id):
        return {
            "metadata": {
                "task_id": task_id,
                "input": {
                    "tts_inference_mode": "minimax",
                    "media_workflow": "bizyair/image_flux.json",
                    "bgm_path": "bgm/calm.mp3",
                },
            }
        }


class Pixelle:
    history = DetailHistory()


class BrokenDetailHistory:
    async def get_task_detail(self, _task_id):
        raise ValueError("corrupt metadata")


class PixelleWithBrokenDetail:
    history = BrokenDetailHistory()


@pytest.mark.asyncio
async def test_history_summary_is_enriched_with_persisted_request_parameters():
    assert hasattr(history, "_enrich_history_task")
    enriched = await history._enrich_history_task(
        Pixelle(), {"task_id": "task-1", "n_frames": 3}
    )

    assert enriched["request_params"] == {
        "tts_inference_mode": "minimax",
        "media_workflow": "bizyair/image_flux.json",
        "bgm_path": "bgm/calm.mp3",
    }


@pytest.mark.asyncio
async def test_one_corrupt_history_detail_does_not_break_the_history_list():
    summary = {"task_id": "legacy-task", "n_frames": 2, "status": "running"}

    enriched = await history._enrich_history_task(PixelleWithBrokenDetail(), summary)

    assert enriched == summary
