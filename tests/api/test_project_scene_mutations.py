import pytest
from fastapi import HTTPException

from api.routers.projects import reorder_scenes, select_asset_version, update_scene, update_timeline
from api.schemas.workbench import ReorderScenesRequest, TimelineUpdateRequest, UpdateSceneRequest
from pixelle_video.models.workbench import AssetSource, AssetVersion, Project, Scene
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


class Core:
    def __init__(self, tmp_path):
        self.workbench_repository = WorkbenchRepository(tmp_path / "db.sqlite3")
        self.workbench_media = WorkbenchMediaStore(tmp_path / "projects")


@pytest.mark.asyncio
async def test_selecting_candidate_keeps_previous_version(tmp_path):
    core = Core(tmp_path)
    project = Project("p", {})
    scene = Scene(project.project_id, 0, "旁白", "画面")
    core.workbench_repository.create_project(project, [scene])
    first = AssetVersion(project.project_id, scene.scene_id, AssetSource.UPLOAD, "a.png")
    second = AssetVersion(project.project_id, scene.scene_id, AssetSource.UPLOAD, "b.png")
    core.workbench_repository.create_asset_version(first)
    core.workbench_repository.create_asset_version(second)

    response = await select_asset_version(project.project_id, scene.scene_id, second.version_id, core)

    assert response["currentVersionId"] == second.version_id
    assert core.workbench_repository.get_asset(first.version_id) is not None
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_scene_update_rejects_duration_shorter_than_audio(tmp_path):
    core = Core(tmp_path)
    project = Project("p", {})
    scene = Scene(project.project_id, 0, "旁白", "画面", duration_seconds=5)
    core.workbench_repository.create_project(project, [scene])

    with pytest.raises(HTTPException) as error:
        await update_scene(project.project_id, scene.scene_id, UpdateSceneRequest(durationSeconds=4), core)

    assert error.value.status_code == 422
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_reorder_requires_exact_scene_set(tmp_path):
    core = Core(tmp_path)
    project = Project("p", {})
    scenes = [Scene(project.project_id, i, str(i), str(i)) for i in range(2)]
    core.workbench_repository.create_project(project, scenes)

    with pytest.raises(HTTPException) as error:
        await reorder_scenes(project.project_id, ReorderScenesRequest(sceneIds=[scenes[0].scene_id]), core)

    assert error.value.status_code == 422
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_timeline_persists_order_and_hold_without_shortening_audio(tmp_path):
    core = Core(tmp_path)
    project = Project("p", {})
    scenes = [Scene(project.project_id, i, str(i), str(i), duration_seconds=2) for i in range(2)]
    core.workbench_repository.create_project(project, scenes)

    response = await update_timeline(
        project.project_id,
        TimelineUpdateRequest(sceneIds=[scenes[1].scene_id, scenes[0].scene_id], holds={scenes[0].scene_id: 1.5}),
        core,
    )

    assert response["sceneIds"] == [scenes[1].scene_id, scenes[0].scene_id]
    updated = core.workbench_repository.get_scene(scenes[0].scene_id)
    assert updated.manual_hold_seconds == 1.5
    assert updated.duration_seconds == 3.5
    await update_timeline(
        project.project_id,
        TimelineUpdateRequest(sceneIds=response["sceneIds"], holds={scenes[0].scene_id: 0.5}),
        core,
    )
    updated = core.workbench_repository.get_scene(scenes[0].scene_id)
    assert updated.duration_seconds == 2.5
    assert [scene.scene_id for scene in core.workbench_repository.list_project_scenes(project.project_id)] == response["sceneIds"]
    core.workbench_repository.close()


def test_timeline_rejects_negative_hold():
    with pytest.raises(Exception):
        TimelineUpdateRequest(sceneIds=["s1"], holds={"s1": -1})
