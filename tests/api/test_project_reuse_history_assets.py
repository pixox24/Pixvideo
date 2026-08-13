"""Quick Create 「沿用历史素材」 must import history frames so generation can skip API."""

from pathlib import Path

import pytest
from PIL import Image

from api.routers.projects import create_project
from api.schemas.workbench import CreateProjectRequest
from pixelle_video.services.workbench_generation import (
    ProjectGenerationPlanner,
    build_parameter_snapshot,
)
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


class Frame:
    def __init__(self, index, image_path, audio_path, narration=None, image_prompt=None):
        self.narration = narration if narration is not None else f"旁白{index}"
        self.image_prompt = image_prompt if image_prompt is not None else f"画面{index}"
        self.image_path = str(image_path)
        self.audio_path = str(audio_path)
        self.duration = 2.0
        self.status = "completed"


class History:
    def __init__(self, storyboard):
        self.storyboard = storyboard

    async def get_task_detail(self, task_id):
        return {
            "metadata": {"input": {"ttsMode": "edge", "voice": "zh-CN-YunjianNeural"}},
            "storyboard": self.storyboard,
        }


class Core:
    def __init__(self, tmp_path, storyboard):
        self.workbench_repository = WorkbenchRepository(tmp_path / "db.sqlite3")
        self.workbench_media = WorkbenchMediaStore(tmp_path / "projects")
        self.history = History(storyboard)
        self.config = {}


@pytest.mark.asyncio
async def test_create_project_with_reuse_task_id_imports_assets_and_skips_image(tmp_path):
    frames = []
    for index in range(2):
        image = tmp_path / f"image-{index}.png"
        Image.new("RGB", (16, 16), "red").save(image)
        audio = tmp_path / f"audio-{index}.mp3"
        audio.write_bytes(b"fake-audio")
        frames.append(Frame(index, image, audio))
    storyboard = type("Storyboard", (), {"title": "src", "frames": frames})()
    core = Core(tmp_path, storyboard)

    body = CreateProjectRequest(
        title="复用项目",
        config={
            "reuseTaskId": "completed-task-1",
            "ttsMode": "edge",
            "voice": "zh-CN-YunjianNeural",
            "useApiImage": True,
        },
        scenes=[
            {"narration": "旁白0", "visualPrompt": "画面0"},
            {"narration": "旁白1", "visualPrompt": "画面1"},
        ],
    )
    created = await create_project(body, core, None)
    scenes = core.workbench_repository.list_project_scenes(created.project_id)

    assert all(scene.current_version_id for scene in scenes)
    assert all(scene.audio_relative_path for scene in scenes)
    for scene in scenes:
        version = core.workbench_repository.get_asset_version(scene.current_version_id)
        assert version is not None
        assert core.workbench_media.resolve(created.project_id, version.relative_path).is_file()
        assert core.workbench_media.resolve(created.project_id, scene.audio_relative_path).is_file()

    project = core.workbench_repository.get_project(created.project_id)
    planner = ProjectGenerationPlanner(core.workbench_repository, core.workbench_media, {})
    snapshot = build_parameter_snapshot(project, runtime_config={})
    items = planner.plan_items(project, scenes, snapshot)
    assert all(item.image_status.value == "skipped" for item in items)
    assert all(item.tts_status.value == "skipped" for item in items)
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_reuse_skips_audio_when_narration_changed(tmp_path):
    image = tmp_path / "image-0.png"
    Image.new("RGB", (8, 8), "blue").save(image)
    audio = tmp_path / "audio-0.mp3"
    audio.write_bytes(b"audio")
    frame = Frame(0, image, audio, narration="原始旁白", image_prompt="画面")
    storyboard = type("Storyboard", (), {"title": "src", "frames": [frame]})()
    core = Core(tmp_path, storyboard)

    body = CreateProjectRequest(
        title="改旁白",
        config={"reuseTaskId": "task-x"},
        scenes=[{"narration": "改过的旁白", "visualPrompt": "画面"}],
    )
    created = await create_project(body, core, None)
    scene = core.workbench_repository.list_project_scenes(created.project_id)[0]
    # Image still reused by position; audio must regenerate for new narration.
    assert scene.current_version_id
    assert not scene.audio_relative_path
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_reuse_does_not_collide_with_from_history_unique_link(tmp_path):
    """
    「复制为项目」binds source_history_task_id uniquely.
    Quick Create 「沿用历史素材」must still create a *new* project for the same task.
    """
    from api.routers.projects import create_project_from_history

    image = tmp_path / "image-0.png"
    Image.new("RGB", (8, 8), "green").save(image)
    audio = tmp_path / "audio-0.mp3"
    audio.write_bytes(b"audio")
    frame = Frame(0, image, audio)
    storyboard = type("Storyboard", (), {"title": "src", "frames": [frame]})()
    core = Core(tmp_path, storyboard)

    from_history = await create_project_from_history("shared-history-task", core, None)
    assert from_history.project_id

    # Second from-history returns the same project (UNIQUE link).
    again = await create_project_from_history("shared-history-task", core, None)
    assert again.project_id == from_history.project_id

    # Quick Create + reuseTaskId must create a separate project (no UNIQUE collision).
    created = await create_project(
        CreateProjectRequest(
            title="沿用再开一份",
            config={"reuseTaskId": "shared-history-task"},
            scenes=[{"narration": "旁白0", "visualPrompt": "画面0"}],
        ),
        core,
        None,
    )
    assert created.project_id != from_history.project_id
    project = core.workbench_repository.get_project(created.project_id)
    assert project.source_history_task_id is None
    assert project.config.get("reuseTaskId") == "shared-history-task"
    scenes = core.workbench_repository.list_project_scenes(created.project_id)
    assert scenes[0].current_version_id  # image imported
    core.workbench_repository.close()
