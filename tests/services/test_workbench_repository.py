from pixelle_video.models.workbench import (
    AssetSource,
    AssetVersion,
    ExportRevision,
    GenerationJob,
    GenerationKind,
    GenerationStatus,
    Project,
    Scene,
)
from pixelle_video.services.workbench_repository import WorkbenchRepository


def test_schema_creates_all_project_tables(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")

    assert repository.table_names() == {
        "projects",
        "scenes",
        "asset_versions",
        "generation_jobs",
        "export_revisions",
        "generation_runs",
        "generation_run_items",
    }


def test_project_and_scenes_round_trip_after_reopening(tmp_path):
    db_path = tmp_path / "workbench.sqlite3"
    repository = WorkbenchRepository(db_path)
    project = Project(title="长项目", config={"mediaWidth": 1080})
    scenes = [
        Scene(project.project_id, 0, "第一段", "第一画面"),
        Scene(project.project_id, 1, "第二段", "第二画面"),
    ]

    repository.create_project(project, scenes)
    repository.close()

    reopened = WorkbenchRepository(db_path)
    loaded_project = reopened.get_project(project.project_id)
    loaded_scenes = reopened.list_project_scenes(project.project_id)

    assert loaded_project is not None
    assert loaded_project.title == "长项目"
    assert loaded_project.config == {"mediaWidth": 1080}
    assert [scene.narration for scene in loaded_scenes] == ["第一段", "第二段"]


def test_candidate_versions_do_not_replace_current_until_selected(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    project = Project(title="版本项目", config={})
    scene = Scene(project.project_id, 0, "旁白", "画面")
    repository.create_project(project, [scene])
    first = AssetVersion(project.project_id, scene.scene_id, AssetSource.AI, "assets/v1.png")
    second = AssetVersion(project.project_id, scene.scene_id, AssetSource.AI, "assets/v2.png")

    repository.create_asset_version(first)
    repository.select_asset_version(project.project_id, scene.scene_id, first.version_id)
    repository.create_asset_version(second)

    assert repository.get_scene(scene.scene_id).current_version_id == first.version_id
    repository.select_asset_version(project.project_id, scene.scene_id, second.version_id)
    assert repository.get_scene(scene.scene_id).current_version_id == second.version_id
    assert len(repository.list_asset_versions(project.project_id, scene.scene_id)) == 2


def test_reorder_scenes_rewrites_contiguous_positions(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    project = Project(title="排序项目", config={})
    scenes = [Scene(project.project_id, i, str(i), str(i)) for i in range(3)]
    repository.create_project(project, scenes)

    repository.reorder_scenes(project.project_id, [scenes[2].scene_id, scenes[0].scene_id, scenes[1].scene_id])

    assert [scene.scene_id for scene in repository.list_project_scenes(project.project_id)] == [
        scenes[2].scene_id, scenes[0].scene_id, scenes[1].scene_id
    ]
    assert [scene.position for scene in repository.list_project_scenes(project.project_id)] == [0, 1, 2]


def test_generation_job_round_trip_and_update(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    project = Project(title="任务项目", config={})
    repository.create_project(project, [])
    job = GenerationJob(project.project_id, GenerationKind.IMAGE, "task-1", {"prompt": "x"})

    repository.create_generation_job(job)
    repository.update_generation_job(
        job.job_id,
        status=GenerationStatus.COMPLETED,
        progress=100,
    )

    loaded = repository.get_generation_job(job.job_id)
    assert loaded.status == GenerationStatus.COMPLETED
    assert loaded.progress == 100
    assert [item.job_id for item in repository.list_generation_jobs(project.project_id)] == [
        job.job_id
    ]
    assert repository.list_generation_jobs(
        project.project_id,
        include_terminal=False,
    ) == []


def test_active_export_revisions_exclude_terminal_statuses(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    project = Project(title="导出项目", config={})
    repository.create_project(project, [])
    revisions = [
        ExportRevision(project.project_id, {}, status=status)
        for status in GenerationStatus
    ]
    for revision in revisions:
        repository.create_export_revision(revision)

    active = repository.list_active_export_revisions()

    assert {revision.export_id for revision in active} == {
        revision.export_id
        for revision in revisions
        if revision.status in {GenerationStatus.PENDING, GenerationStatus.RUNNING}
    }
