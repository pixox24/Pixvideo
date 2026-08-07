import pytest

from api.routers.projects import regenerate_image
from api.schemas.workbench import RegenerateImageRequest
from api.tasks import task_manager
from pixelle_video.models.workbench import Project, Scene
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


class FakeJobs:
    async def run_image_job(self, *args):
        return None


class Core:
    def __init__(self, tmp_path):
        self.workbench_repository = WorkbenchRepository(tmp_path / "db.sqlite3")
        self.workbench_media = WorkbenchMediaStore(tmp_path / "projects")
        self.workbench_jobs = FakeJobs()


@pytest.mark.asyncio
async def test_regenerate_image_persists_prompt_snapshot(tmp_path, monkeypatch):
    core = Core(tmp_path)
    project = Project("p", {})
    scene = Scene(project.project_id, 0, "旁白", "旧")
    core.workbench_repository.create_project(project, [scene])
    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(task_manager, "execute_task", noop)

    response = await regenerate_image(project.project_id, scene.scene_id, RegenerateImageRequest(prompt="new prompt"), core)
    job = core.workbench_repository.get_generation_job(response.job_id)

    assert response.kind == "image"
    assert job.request_snapshot == {"prompt": "new prompt"}
    core.workbench_repository.close()
