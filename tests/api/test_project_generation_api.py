from types import SimpleNamespace

import pytest
from PIL import Image

from api.routers.projects import (
    get_active_generation_run,
    get_generation_run,
    get_project,
    pause_generation_run,
    start_generation_run,
)
from api.schemas.workbench import GenerationRunCreateRequest
from api.tasks import task_manager
from pixelle_video.models.workbench import (
    AssetSource,
    AssetVersion,
    GenerationRun,
    GenerationRunItem,
    Project,
    Scene,
)
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


class Core:
    def __init__(self, tmp_path):
        self.workbench_repository = WorkbenchRepository(tmp_path / "db.sqlite3")
        self.workbench_media = WorkbenchMediaStore(tmp_path / "projects")
        self.project_generation = SimpleNamespace()


@pytest.mark.asyncio
async def test_start_and_get_generation_run_response(tmp_path, monkeypatch):
    core = Core(tmp_path)
    project = Project("p", {})
    scene = Scene(project.project_id, 0, "narration", "prompt")
    core.workbench_repository.create_project(project, [scene])
    run = GenerationRun(project.project_id, "task-1", {})
    item = GenerationRunItem(run.run_id, scene.scene_id, 0, "narration", "prompt", "tts", "image")
    core.workbench_repository.create_generation_run(run, [item])

    async def start(*args, **kwargs):
        return run

    async def pause(run_id):
        return run

    core.project_generation.start = start
    core.project_generation.request_pause = pause
    monkeypatch.setattr(task_manager, "execute_task", lambda *args, **kwargs: None)

    created = await start_generation_run(project.project_id, GenerationRunCreateRequest(), core)
    loaded = await get_generation_run(project.project_id, run.run_id, core)
    paused = await pause_generation_run(project.project_id, run.run_id, core)
    assert created.run_id == loaded.run_id == paused.run_id == run.run_id
    assert loaded.items[0].scene_id == scene.scene_id
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_active_generation_run_can_be_restored_after_page_reload(tmp_path):
    core = Core(tmp_path)
    project = Project("p", {})
    scene = Scene(project.project_id, 0, "narration", "prompt")
    core.workbench_repository.create_project(project, [scene])
    run = GenerationRun(project.project_id, "task-1", {})
    core.workbench_repository.create_generation_run(
        run,
        [GenerationRunItem(run.run_id, scene.scene_id, 0, "narration", "prompt", "tts", "image")],
    )
    active = await get_active_generation_run(project.project_id, core)
    assert active is not None
    assert active.run_id == run.run_id
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_project_response_includes_jobs_and_generation_state(tmp_path):
    core = Core(tmp_path)
    project = Project("p", {})
    scene = Scene(project.project_id, 0, "narration", "prompt")
    core.workbench_repository.create_project(project, [scene])
    response = await get_project(project.project_id, core, None)
    assert response.scenes[0].generation_state["image"] == "missing"
    assert response.jobs == []
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_project_response_marks_fingerprint_mismatches_stale(tmp_path):
    core = Core(tmp_path)
    project = Project("p", {})
    scene = Scene(project.project_id, 0, "narration", "prompt")
    core.workbench_repository.create_project(project, [scene])
    image_relative = "assets/scenes/scene-0/generated/current.png"
    image_path = core.workbench_media.resolve(project.project_id, image_relative)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (2, 2), "blue").save(image_path)
    version = AssetVersion(
        project.project_id,
        scene.scene_id,
        AssetSource.AI,
        image_relative,
        parameters={"imageFingerprint": "old-image"},
    )
    core.workbench_repository.create_asset_version(version)
    core.workbench_repository.select_asset_version(project.project_id, scene.scene_id, version.version_id)
    audio_relative = "assets/scenes/scene-0/audio/current.mp3"
    audio_path = core.workbench_media.resolve(project.project_id, audio_relative)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"audio")
    core.workbench_repository.update_scene(
        scene.scene_id,
        audio_relative_path=audio_relative,
        audio_fingerprint="old-audio",
    )
    response = await get_project(project.project_id, core, None)
    assert response.scenes[0].generation_state["image"] == "stale"
    assert response.scenes[0].generation_state["audio"] == "stale"
    core.workbench_repository.close()
