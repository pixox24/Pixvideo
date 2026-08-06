from pathlib import Path

import pytest
from PIL import Image

from pixelle_video.models.workbench import Project, Scene
from pixelle_video.services.workbench_jobs import WorkbenchJobService
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


class FakeCore:
    config = {"comfyui": {"image": {"default_workflow": "test"}}}
    frame_processor = None

    async def tts(self, text, output_path=None, **kwargs):
        Path(output_path).write_bytes(b"audio")
        return output_path

    async def media(self, **kwargs):
        return type("Result", (), {"url": "local-result.png"})()


class FakeMediaStore(WorkbenchMediaStore):
    async def download_result(self, project_id, scene_id, source_url, version_id):
        relative = f"assets/scenes/{scene_id}/generated/{version_id}.png"
        path = self.resolve(project_id, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (32, 32), "blue").save(path)
        return relative


@pytest.mark.asyncio
async def test_scene_job_creates_audio_and_first_image_as_current_version(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    project = Project(title="p", config={})
    scene = Scene(project.project_id, 0, "旁白", "画面")
    repository.create_project(project, [scene])
    service = WorkbenchJobService(FakeCore(), repository, media_store)

    await service.run_scene_job(project.project_id, scene.scene_id, "t1")

    saved = repository.get_scene(scene.scene_id)
    assert saved.current_version_id is not None
    assert saved.audio_relative_path.endswith(".mp3")
    assert saved.status == "completed"
    assert len(repository.list_asset_versions(project.project_id, scene.scene_id)) == 1
    repository.close()


@pytest.mark.asyncio
async def test_image_job_appends_candidate_without_replacing_current(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    project = Project(title="p", config={})
    scene = Scene(project.project_id, 0, "旁白", "旧")
    repository.create_project(project, [scene])
    service = WorkbenchJobService(FakeCore(), repository, media_store)

    await service.run_image_job(project.project_id, scene.scene_id, "t1", "旧")
    first = repository.get_scene(scene.scene_id).current_version_id
    await service.run_image_job(project.project_id, scene.scene_id, "t2", "新")

    assert repository.get_scene(scene.scene_id).current_version_id == first
    assert len(repository.list_asset_versions(project.project_id, scene.scene_id)) == 2
    repository.close()

