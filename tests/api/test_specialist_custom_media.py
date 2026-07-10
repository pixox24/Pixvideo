from types import SimpleNamespace

import pytest
from starlette.requests import Request

from api.routers import specialist
from api.schemas.specialist import ActionTransferGenerateRequest, CustomMediaGenerateRequest, DigitalHumanGenerateRequest, ImageToVideoGenerateRequest


@pytest.mark.asyncio
async def test_custom_media_task_uses_uploaded_assets_and_persists_task_identity(monkeypatch):
    captured = {}
    task = SimpleNamespace(task_id="task-123")

    monkeypatch.setattr(specialist, "resolve_uploaded_file_keys", lambda keys, purpose: ["/uploads/camping.png"])
    monkeypatch.setattr(specialist.task_manager, "create_task", lambda **kwargs: task)

    class FakePipeline:
        def __init__(self, core):
            captured["core"] = core

        async def __call__(self, **kwargs):
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                final_video_path="output/task-123/final.mp4",
                storyboard=SimpleNamespace(total_duration=12.5),
            )

    monkeypatch.setattr(specialist, "AssetBasedPipeline", FakePipeline)

    async def execute_task(task_id, coro_func):
        captured["task_id"] = task_id
        captured["result"] = await coro_func()

    monkeypatch.setattr(specialist.task_manager, "execute_task", execute_task)
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "scheme": "http", "server": ("testserver", 80)})
    body = CustomMediaGenerateRequest(
        asset_file_keys=["data/uploads/batch/file-01.png"],
        title="Campfire",
        intent="Warm outdoor story",
        duration=15,
    )

    response = await specialist.generate_custom_media_async(body, object(), request)

    assert response.task_id == "task-123"
    assert captured["task_id"] == "task-123"
    assert captured["kwargs"]["assets"] == ["/uploads/camping.png"]
    assert captured["kwargs"]["task_id"] == "task-123"
    assert captured["result"]["duration"] == 12.5


@pytest.mark.asyncio
async def test_image_to_video_task_uses_uploaded_image_and_persists_history(monkeypatch):
    captured = {}
    task = SimpleNamespace(task_id="i2v-task")

    monkeypatch.setattr(specialist, "resolve_uploaded_file_keys", lambda keys, purpose: ["/uploads/source.png"])
    monkeypatch.setattr(specialist.task_manager, "create_task", lambda **kwargs: task)
    monkeypatch.setattr(specialist, "_update_task_progress", lambda *args: None)

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


@pytest.mark.asyncio
async def test_action_transfer_task_requires_and_passes_both_uploaded_assets(monkeypatch):
    captured = {}
    task = SimpleNamespace(task_id="action-task")

    monkeypatch.setattr(
        specialist,
        "resolve_uploaded_file_keys",
        lambda keys, purpose: ["/uploads/reference.mp4" if "video" in purpose.value else "/uploads/subject.png"],
    )
    monkeypatch.setattr(specialist.task_manager, "create_task", lambda **kwargs: task)
    monkeypatch.setattr(specialist.task_manager, "update_progress", lambda *args, **kwargs: None)

    async def execute_workflow(core, workflow_key, workflow_params, task_id):
        captured["workflow"] = (workflow_key, workflow_params, task_id)
        return "output/action-task/final.mp4"

    async def persist(*args, **kwargs):
        captured["persist"] = args

    async def execute_task(task_id, coro_func):
        captured["result"] = await coro_func()

    monkeypatch.setattr(specialist, "execute_video_workflow", execute_workflow)
    monkeypatch.setattr(specialist, "persist_specialist_video", persist)
    monkeypatch.setattr(specialist.task_manager, "execute_task", execute_task)
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "scheme": "http", "server": ("testserver", 80)})
    body = ActionTransferGenerateRequest(
        video_file_key="data/uploads/video/file-01.mp4",
        image_file_key="data/uploads/image/file-01.png",
        prompt="A dancer turns gracefully",
        duration=12,
    )

    response = await specialist.generate_action_transfer_async(body, object(), request)

    assert response.task_id == "action-task"
    assert captured["workflow"] == (
        "runninghub/af_scail.json",
        {"video": "/uploads/reference.mp4", "image": "/uploads/subject.png", "prompt": "A dancer turns gracefully", "second": 12},
        "action-task",
    )
    assert captured["persist"][2] == "action_transfer"


@pytest.mark.asyncio
async def test_digital_human_task_passes_mode_assets_and_tts_settings(monkeypatch):
    captured = {}
    task = SimpleNamespace(task_id="human-task")

    monkeypatch.setattr(
        specialist,
        "resolve_uploaded_file_keys",
        lambda keys, purpose: ["/uploads/character.png" if purpose.value.endswith("character") else "/uploads/product.png"],
    )
    monkeypatch.setattr(specialist.task_manager, "create_task", lambda **kwargs: task)
    monkeypatch.setattr(specialist.task_manager, "update_progress", lambda *args, **kwargs: None)

    async def execute_human(*args):
        captured["human"] = args
        return "output/human-task/final.mp4"

    async def persist(*args, **kwargs):
        captured["persist"] = args

    async def execute_task(task_id, coro_func):
        captured["result"] = await coro_func()

    monkeypatch.setattr(specialist, "execute_digital_human_video", execute_human)
    monkeypatch.setattr(specialist, "persist_specialist_video", persist)
    monkeypatch.setattr(specialist.task_manager, "execute_task", execute_task)
    request = Request({"type": "http", "method": "POST", "path": "/", "headers": [], "scheme": "http", "server": ("testserver", 80)})
    body = DigitalHumanGenerateRequest(
        mode="digital",
        character_file_key="data/uploads/character/file-01.png",
        product_file_key="data/uploads/product/file-01.png",
        script="介绍这款产品",
        tts_inference_mode="local",
        voice="zh-CN-XiaoxiaoNeural",
    )

    response = await specialist.generate_digital_human_async(body, object(), request)

    assert response.task_id == "human-task"
    assert captured["human"][1:6] == ("human-task", "digital", "/uploads/character.png", "介绍这款产品", "/uploads/product.png")
    assert captured["persist"][2] == "digital_human"
