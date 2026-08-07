import pytest
from fastapi import HTTPException

from api.routers.projects import create_export
from api.schemas.workbench import ExportRequest
from pixelle_video.models.workbench import AssetSource, AssetVersion, Project, Scene
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


class Core:
    def __init__(self, tmp_path):
        self.workbench_repository = WorkbenchRepository(tmp_path / "db.sqlite3")
        self.workbench_media = WorkbenchMediaStore(tmp_path / "projects")
        self.workbench_jobs = None


@pytest.mark.asyncio
async def test_export_snapshot_freezes_selected_version(tmp_path, monkeypatch):
    core = Core(tmp_path)
    project = Project("p", {"bgm": "none"})
    scene = Scene(project.project_id, 0, "n", "p", audio_relative_path="audio/a.mp3")
    core.workbench_repository.create_project(project, [scene])
    old = AssetVersion(project.project_id, scene.scene_id, AssetSource.UPLOAD, "assets/old.png")
    new = AssetVersion(project.project_id, scene.scene_id, AssetSource.UPLOAD, "assets/new.png")
    core.workbench_repository.create_asset_version(old)
    core.workbench_repository.create_asset_version(new)
    core.workbench_repository.select_asset_version(project.project_id, scene.scene_id, old.version_id)

    response = await create_export(project.project_id, core, ExportRequest())
    snapshot = core.workbench_repository.get_export_revision(response["exportId"])
    core.workbench_repository.select_asset_version(project.project_id, scene.scene_id, new.version_id)

    assert snapshot.snapshot["scenes"][0]["versionId"] == old.version_id
    assert response["candidateWarnings"] == []
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_export_warns_about_unconfirmed_ai_candidate_without_replacing_current(tmp_path):
    core = Core(tmp_path)
    project = Project("p", {})
    scene = Scene(project.project_id, 0, "n", "p", audio_relative_path="audio/a.mp3")
    core.workbench_repository.create_project(project, [scene])
    current = AssetVersion(project.project_id, scene.scene_id, AssetSource.AI, "assets/current.png")
    candidate = AssetVersion(project.project_id, scene.scene_id, AssetSource.AI, "assets/candidate.png")
    core.workbench_repository.create_asset_version(current)
    core.workbench_repository.create_asset_version(candidate)
    core.workbench_repository.select_asset_version(project.project_id, scene.scene_id, current.version_id)

    response = await create_export(project.project_id, core, ExportRequest())
    snapshot = core.workbench_repository.get_export_revision(response["exportId"])
    assert response["candidateWarnings"] == [scene.scene_id]
    assert snapshot.snapshot["scenes"][0]["versionId"] == current.version_id
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_incomplete_export_requires_explicit_confirmation(tmp_path):
    core = Core(tmp_path)
    project = Project("p", {})
    scene = Scene(project.project_id, 0, "n", "p")
    core.workbench_repository.create_project(project, [scene])

    with pytest.raises(HTTPException) as error:
        await create_export(project.project_id, core, ExportRequest())

    assert error.value.status_code == 409
    core.workbench_repository.close()
