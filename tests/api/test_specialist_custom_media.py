from types import SimpleNamespace

import pytest
from starlette.requests import Request

from api.routers import specialist
from api.schemas.specialist import ImageToVideoGenerateRequest


@pytest.mark.asyncio
async def test_image_to_video_task_uses_uploaded_image_and_persists_history(monkeypatch):
    captured = {}
    task = SimpleNamespace(task_id="i2v-task")

    monkeypatch.setattr(specialist, "resolve_uploaded_file_keys", lambda keys, purpose: ["/uploads/source.png"])
    monkeypatch.setattr(specialist.task_manager, "create_task", lambda **kwargs: task)

    async def execute_workflow(core, workflow_key, workflow_params, task_id):
        captured["workflow"] = (core, workflow_key, workflow_params, task_id)
        return "output/i2v-task/final.mp4"

    async def persist(*args, **kwargs):
        captured["persist"] = (args, kwargs)

    async def execute_task(task_id, coro_func):
        captured["task_id"] = task_id
        captured["result"] = await coro_func()

    monkeypatch.setattr(specialist, "execute_video_workflow", execute_workflow)
    monkeypatch.setattr(specialist, "persist_specialist_video", persist)
    monkeypatch.setattr(specialist.task_manager, "execute_task", execute_task)
    monkeypatch.setattr(specialist.task_manager, "update_progress", lambda *args, **kwargs: None)
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "scheme": "http", "server": ("testserver", 80)})
    body = ImageToVideoGenerateRequest(
        image_file_key="data/uploads/batch/file-01.png",
        prompt="Camera pushes forward through the scene",
        workflow_key="runninghub/i2v_LTX2.json",
        title="Motion test",
    )

    response = await specialist.generate_image_to_video_async(body, object(), request)

    assert response.task_id == "i2v-task"
    assert captured["task_id"] == "i2v-task"
    assert captured["workflow"][1:] == (
        "runninghub/i2v_LTX2.json",
        {"image": "/uploads/source.png", "prompt": "Camera pushes forward through the scene"},
        "i2v-task",
    )
    assert captured["persist"][0][2] == "image_to_video"


def test_removed_specialist_modes_are_absent():
    source = open("api/routers/specialist.py", encoding="utf-8").read()
    assert "custom-media" not in source
    assert "action-transfer" not in source
    assert "digital-human" not in source
    assert "image-to-video" in source
