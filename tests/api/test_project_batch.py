from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.routers.projects import batch_image_generations
from api.schemas.workbench import BatchImageRequest
from api.tasks import task_manager
from pixelle_video.models.workbench import Project, Scene
from pixelle_video.services.project_generation_service import ActiveSceneLockedError
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


class Jobs:
    async def run_image_job_limited(self, *args):
        return None


class Core:
    def __init__(self, tmp_path):
        self.workbench_repository = WorkbenchRepository(tmp_path / "db.sqlite3")
        self.workbench_media = WorkbenchMediaStore(tmp_path / "projects")
        self.workbench_jobs = Jobs()


def test_batch_request_rejects_duplicate_scene_ids():
    with pytest.raises(ValidationError):
        BatchImageRequest(sceneIds=["s1", "s1"])


@pytest.mark.asyncio
async def test_batch_creates_one_job_per_scene(tmp_path, monkeypatch):
    core = Core(tmp_path)
    project = Project("p", {})
    scenes = [Scene(project.project_id, index, str(index), f"prompt-{index}") for index in range(2)]
    core.workbench_repository.create_project(project, scenes)

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(task_manager, "execute_task", noop)
    response = await batch_image_generations(project.project_id, BatchImageRequest(sceneIds=[scene.scene_id for scene in scenes], promptPrefix="warm"), core)

    assert len(response["jobs"]) == 2
    assert all(job["kind"] == "image" for job in response["jobs"])
    assert core.workbench_repository.get_generation_job(response["jobs"][0]["jobId"]).request_snapshot["prompt"].startswith("warm")
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_batch_skips_user_locked_scenes(tmp_path, monkeypatch):
    core = Core(tmp_path)
    project = Project("p", {})
    locked = Scene(project.project_id, 0, "locked", "prompt", locked=True)
    open_scene = Scene(project.project_id, 1, "open", "prompt")
    core.workbench_repository.create_project(project, [locked, open_scene])

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(task_manager, "execute_task", noop)
    response = await batch_image_generations(
        project.project_id,
        BatchImageRequest(sceneIds=[locked.scene_id, open_scene.scene_id]),
        core,
    )
    assert [job["sceneId"] for job in response["jobs"]] == [open_scene.scene_id]
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_batch_rejects_when_all_selected_scenes_are_user_locked(tmp_path):
    core = Core(tmp_path)
    project = Project("p", {})
    scene = Scene(project.project_id, 0, "locked", "prompt", locked=True)
    core.workbench_repository.create_project(project, [scene])

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await batch_image_generations(project.project_id, BatchImageRequest(sceneIds=[scene.scene_id]), core)
    assert error.value.status_code == 409
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_batch_rejects_locked_active_scene_before_creating_jobs(tmp_path, monkeypatch):
    core = Core(tmp_path)
    project = Project("p", {})
    scene = Scene(project.project_id, 0, "0", "prompt")
    core.workbench_repository.create_project(project, [scene])

    def assert_scene_editable(project_id, scene_id):
        raise ActiveSceneLockedError("run-1", scene_id)

    core.project_generation = SimpleNamespace(assert_scene_editable=assert_scene_editable)
    executed = False

    async def should_not_execute(*args, **kwargs):
        nonlocal executed
        executed = True

    monkeypatch.setattr(task_manager, "execute_task", should_not_execute)
    with pytest.raises(Exception) as error:
        await batch_image_generations(
            project.project_id,
            BatchImageRequest(sceneIds=[scene.scene_id]),
            core,
        )
    assert getattr(error.value, "status_code", None) == 409
    assert executed is False
    assert core.workbench_repository.list_generation_jobs(project.project_id) == []
    core.workbench_repository.close()

