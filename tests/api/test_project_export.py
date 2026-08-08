import pytest
from fastapi import HTTPException

import api.app as api_app
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
async def test_startup_resumes_exports_even_if_generation_resume_fails(monkeypatch):
    calls = []

    class Generation:
        async def resume_active_runs(self):
            raise RuntimeError("generation recovery failed")

    class Jobs:
        async def resume_active_exports(self, manager):
            calls.append(manager)

    core = type("Core", (), {"project_generation": Generation(), "workbench_jobs": Jobs()})()

    async def noop():
        return None

    async def get_core():
        return core

    monkeypatch.setattr(api_app.task_manager, "start", noop)
    monkeypatch.setattr(api_app.task_manager, "stop", noop)
    monkeypatch.setattr(api_app, "get_pixelle_video", get_core)
    monkeypatch.setattr(api_app, "shutdown_pixelle_video", noop)

    async with api_app.lifespan(api_app.app):
        pass

    assert calls == [api_app.task_manager]


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
    core.workbench_repository.update_project(project.project_id, config={"bgm": "changed"})

    assert snapshot.snapshot["scenes"][0]["versionId"] == old.version_id
    assert snapshot.snapshot["config"] == {"bgm": "none"}
    assert snapshot.snapshot["purpose"] == "manual"
    assert snapshot.snapshot["createdFromRunId"] is None
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


@pytest.mark.asyncio
async def test_incomplete_export_omits_blocking_scenes(tmp_path):
    core = Core(tmp_path)
    project = Project("p", {})
    complete = Scene(project.project_id, 0, "complete", "p", audio_relative_path="audio/a.mp3")
    incomplete = Scene(project.project_id, 1, "incomplete", "p")
    core.workbench_repository.create_project(project, [complete, incomplete])
    version = AssetVersion(project.project_id, complete.scene_id, AssetSource.UPLOAD, "assets/complete.png")
    core.workbench_repository.create_asset_version(version)
    core.workbench_repository.select_asset_version(project.project_id, complete.scene_id, version.version_id)

    response = await create_export(project.project_id, core, ExportRequest(allowIncomplete=True))
    revision = core.workbench_repository.get_export_revision(response["exportId"])

    assert revision.snapshot["sceneOrder"] == [complete.scene_id]
    assert [scene["sceneId"] for scene in revision.snapshot["scenes"]] == [complete.scene_id]
    assert response["blockingScenes"] == [incomplete.scene_id]
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_incomplete_export_rejects_an_empty_video(tmp_path):
    core = Core(tmp_path)
    project = Project("p", {})
    scene = Scene(project.project_id, 0, "n", "p")
    core.workbench_repository.create_project(project, [scene])

    with pytest.raises(HTTPException) as error:
        await create_export(project.project_id, core, ExportRequest(allowIncomplete=True))

    assert error.value.status_code == 409
    assert error.value.detail["blockingScenes"] == [scene.scene_id]
    core.workbench_repository.close()
