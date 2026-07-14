import asyncio

import pytest

from api.tasks.manager import TaskManager
from api.tasks.models import TaskStatus, TaskType
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


class RecordingPersistence:
    def __init__(self):
        self.metadata = []

    async def save_task_metadata(self, task_id, metadata):
        self.metadata.append((task_id, metadata))

    async def save_storyboard(self, *_args):
        return None


class PipelineCore:
    def __init__(self):
        self.config = {"comfyui": {"image": {"prompt_prefix": ""}}}
        self.llm = object()
        self.tts = object()
        self.media = object()
        self.video = object()
        self.persistence = RecordingPersistence()


@pytest.mark.asyncio
async def test_standard_pipeline_uses_api_task_id_for_output_and_history(monkeypatch, tmp_path):
    created_ids = []

    def fake_create_task_output_dir(task_id=None):
        created_ids.append(task_id)
        task_dir = tmp_path / str(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        return str(task_dir), task_id

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.create_task_output_dir",
        fake_create_task_output_dir,
    )
    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.get_task_final_video_path",
        lambda task_id: str(tmp_path / str(task_id) / "final.mp4"),
    )

    core = PipelineCore()
    pipeline = StandardPipeline(core)
    ctx = PipelineContext(input_text="旁白", params={"task_id": "api-task-123"})

    await pipeline.setup_environment(ctx)

    assert created_ids == ["api-task-123"]
    assert ctx.task_id == "api-task-123"
    assert core.persistence.metadata[-1][0] == "api-task-123"


@pytest.mark.asyncio
async def test_task_manager_awaits_cancelled_future_and_keeps_cancelled_status():
    manager = TaskManager()
    task = manager.create_task(TaskType.VIDEO_GENERATION)
    cancellation_observed = asyncio.Event()

    async def long_running_job():
        try:
            await asyncio.Event().wait()
        finally:
            cancellation_observed.set()

    await manager.execute_task(task.task_id, long_running_job)
    await asyncio.sleep(0)

    assert await manager.cancel_task(task.task_id) is True
    assert cancellation_observed.is_set()
    assert manager.get_task(task.task_id).status == TaskStatus.CANCELLED


def test_task_manager_reuses_task_for_the_same_client_request_key():
    manager = TaskManager()

    first = manager.create_task(
        TaskType.VIDEO_GENERATION,
        request_params={"title": "first"},
        request_key="stable-request-key",
    )
    second = manager.create_task(
        TaskType.VIDEO_GENERATION,
        request_params={"title": "duplicate"},
        request_key="stable-request-key",
    )

    assert second is first
    assert len(manager.list_tasks()) == 1


@pytest.mark.asyncio
async def test_idempotent_task_is_not_executed_twice():
    manager = TaskManager()
    task = manager.create_task(TaskType.VIDEO_GENERATION, request_key="stable-request-key")
    executions = 0
    release = asyncio.Event()

    async def job():
        nonlocal executions
        executions += 1
        await release.wait()

    await manager.execute_task(task.task_id, job)
    await asyncio.sleep(0)
    await manager.execute_task(task.task_id, job)
    await asyncio.sleep(0)

    assert executions == 1
    release.set()
    await manager._task_futures[task.task_id]


@pytest.mark.asyncio
async def test_standard_pipeline_persists_cancelled_terminal_state():
    core = PipelineCore()
    pipeline = StandardPipeline(core)
    ctx = PipelineContext(input_text="旁白", params={"task_id": "api-task-123"})
    ctx.final_video_path = "output/api-task-123/final.mp4"

    await pipeline.handle_cancellation(ctx)

    task_id, metadata = core.persistence.metadata[-1]
    assert task_id == "api-task-123"
    assert metadata["status"] == "cancelled"
    assert metadata["completed_at"] is not None
