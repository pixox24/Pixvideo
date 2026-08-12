"""Day-1 P0 stability: cancel terminalization, orphan jobs, dual-key export, auto-select."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from api.tasks.manager import TaskManager
from api.tasks.models import TaskStatus, TaskType
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
from pixelle_video.services.workbench_jobs import WorkbenchJobService
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


class SlowMediaCore:
    config = {"comfyui": {"image": {"default_workflow": "test"}, "tts": {}}}

    def __init__(self, started: asyncio.Event, release: asyncio.Event):
        self.started = started
        self.release = release
        self.media_kwargs = None

    async def media(self, **kwargs):
        self.media_kwargs = kwargs
        self.started.set()
        await self.release.wait()
        return type("Result", (), {"url": "local-result.png"})()

    async def tts(self, text, output_path=None, **kwargs):
        Path(output_path).write_bytes(b"audio")
        return output_path


class LocalImageCore:
    config = {"comfyui": {"image": {"default_workflow": "test"}, "tts": {}}}

    def __init__(self, image_path: Path):
        self.image_path = image_path

    async def media(self, **kwargs):
        return type("Result", (), {"url": str(self.image_path)})()

    async def tts(self, text, output_path=None, **kwargs):
        Path(output_path).write_bytes(b"audio")
        return output_path


class FakeMediaStore(WorkbenchMediaStore):
    async def download_result(self, project_id, scene_id, source_url, version_id):
        relative = f"assets/scenes/{scene_id}/generated/{version_id}.png"
        path = self.resolve(project_id, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (32, 32), "blue").save(path)
        return relative


def test_export_params_prefer_camel_over_conflicting_snake():
    params = WorkbenchJobService._export_pipeline_params(
        project_id="p1",
        task_id="t1",
        snapshot={
            "config": {
                "enableSubtitles": False,
                "subtitle_enabled": True,
                "enableMotion": False,
                "image_motion_enabled": True,
                "bgmVolume": 10,
                "bgm_volume": 90,
            },
            "scenes": [{"sceneId": "s1", "narration": "hi"}],
        },
        existing_assets={},
    )
    assert params["subtitle_enabled"] is False
    assert params["image_motion_enabled"] is False
    assert params["bgm_volume"] == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_image_job_cancel_marks_scene_and_job_cancelled(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    project = Project(title="p", config={})
    scene = Scene(project.project_id, 0, "n", "v")
    repository.create_project(project, [scene])
    job = GenerationJob(
        project.project_id,
        GenerationKind.IMAGE,
        "task-cancel-1",
        {},
        scene_id=scene.scene_id,
    )
    repository.create_generation_job(job)

    started = asyncio.Event()
    release = asyncio.Event()
    service = WorkbenchJobService(SlowMediaCore(started, release), repository, media_store)

    task = asyncio.create_task(
        service.run_image_job(project.project_id, scene.scene_id, job.task_id, "prompt")
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    saved_scene = repository.get_scene(scene.scene_id)
    saved_job = repository.get_generation_job_by_task_id(job.task_id)
    assert saved_scene.status == "cancelled"
    assert saved_job is not None
    assert saved_job.status == GenerationStatus.CANCELLED
    repository.close()


@pytest.mark.asyncio
async def test_export_cancel_marks_revision_cancelled(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    project = Project(title="p", config={})
    scene = Scene(project.project_id, 0, "n", "v")
    repository.create_project(project, [scene])

    image_rel = f"assets/scenes/{scene.scene_id}/current.png"
    audio_rel = f"assets/scenes/{scene.scene_id}/audio/a.mp3"
    image_path = media_store.resolve(project.project_id, image_rel)
    audio_path = media_store.resolve(project.project_id, audio_rel)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), "red").save(image_path)
    audio_path.write_bytes(b"audio")

    revision = ExportRevision(
        project.project_id,
        {
            "scenes": [
                {
                    "sceneId": scene.scene_id,
                    "position": 0,
                    "imagePath": image_rel,
                    "audioPath": audio_rel,
                    "durationSeconds": 1.0,
                    "manualHoldSeconds": 0,
                }
            ],
            "config": {},
        },
    )
    repository.create_export_revision(revision)

    started = asyncio.Event()
    release = asyncio.Event()

    class ExportCore:
        config = {}

        async def generate_video(self, **kwargs):
            started.set()
            await release.wait()
            return {"video_path": str(tmp_path / "out.mp4")}

    service = WorkbenchJobService(ExportCore(), repository, media_store)
    task = asyncio.create_task(
        service.run_export_job(project.project_id, revision.export_id, "export-task-1")
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    saved = repository.get_export_revision(revision.export_id)
    assert saved.status == GenerationStatus.CANCELLED
    repository.close()


def test_abandon_orphan_scene_jobs_on_startup(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    project = Project(title="p", config={})
    scene = Scene(project.project_id, 0, "n", "v", status="running")
    repository.create_project(project, [scene])
    job = GenerationJob(
        project.project_id,
        GenerationKind.IMAGE,
        "orphan-task",
        {},
        scene_id=scene.scene_id,
        status=GenerationStatus.RUNNING,
    )
    repository.create_generation_job(job)

    service = WorkbenchJobService(LocalImageCore(tmp_path / "x.png"), repository, media_store)
    count = service.abandon_orphan_scene_jobs()
    assert count >= 1
    assert repository.get_generation_job(job.job_id).status == GenerationStatus.FAILED
    assert repository.get_scene(scene.scene_id).status == "failed"
    repository.close()


@pytest.mark.asyncio
async def test_auto_select_only_when_still_no_current_version(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    project = Project(title="p", config={})
    scene = Scene(project.project_id, 0, "n", "v")
    repository.create_project(project, [scene])

    # Pre-select a user version while AI is "in flight"
    user_version = AssetVersion(
        project.project_id,
        scene.scene_id,
        AssetSource.UPLOAD,
        f"assets/scenes/{scene.scene_id}/user.png",
        prompt_snapshot="user",
    )
    repository.create_asset_version(user_version)
    repository.select_asset_version(project.project_id, scene.scene_id, user_version.version_id)

    local = tmp_path / "src.png"
    Image.new("RGB", (8, 8), "green").save(local)
    service = WorkbenchJobService(LocalImageCore(local), repository, media_store)
    result = await service.generate_image_asset(
        project.project_id, scene.scene_id, "t-ai", "ai prompt"
    )

    saved = repository.get_scene(scene.scene_id)
    assert saved.current_version_id == user_version.version_id
    assert result["candidate"] is True
    assert len(repository.list_asset_versions(project.project_id, scene.scene_id)) == 2
    repository.close()


@pytest.mark.asyncio
async def test_cancel_task_does_not_overwrite_completed():
    manager = TaskManager()
    await manager.start()
    task = manager.create_task(TaskType.WORKBENCH_EXPORT, request_params={})

    gate = asyncio.Event()

    async def work():
        await gate.wait()
        return "ok"

    await manager.execute_task(task.task_id, work)
    # Let task start
    await asyncio.sleep(0.01)
    gate.set()
    # Wait until completed
    for _ in range(50):
        current = manager.get_task(task.task_id)
        if current and current.status == TaskStatus.COMPLETED:
            break
        await asyncio.sleep(0.01)
    assert manager.get_task(task.task_id).status == TaskStatus.COMPLETED

    cancelled = await manager.cancel_task(task.task_id)
    assert cancelled is False
    assert manager.get_task(task.task_id).status == TaskStatus.COMPLETED
    await manager.stop()


@pytest.mark.asyncio
async def test_generation_run_hard_cancel_terminalizes(tmp_path):
    from pixelle_video.models.workbench import (
        GenerationPhase,
        GenerationRun,
        GenerationRunItem,
        GenerationRunItemStatus,
        GenerationRunStatus,
    )
    from pixelle_video.services.project_generation_service import ProjectGenerationService

    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    project = Project(title="p", config={})
    scene = Scene(project.project_id, 0, "n", "v")
    repository.create_project(project, [scene])
    run = GenerationRun(
        project.project_id,
        task_id="run-task",
        parameter_snapshot={},
        total_count=1,
        status=GenerationRunStatus.RUNNING,
    )
    item = GenerationRunItem(
        run.run_id,
        scene.scene_id,
        0,
        "n",
        "v",
        "nf",
        "if",
        status=GenerationRunItemStatus.RUNNING_IMAGE,
        tts_status=GenerationPhase.COMPLETED,
        image_status=GenerationPhase.RUNNING,
    )
    repository.create_generation_run(run, [item])

    class CoreStub:
        workbench_media = None

    service = ProjectGenerationService(
        core=CoreStub(),
        repository=repository,
        workbench_jobs=object(),
        task_manager=None,
    )
    service._terminalize_run_cancelled(run.run_id, error="generation cancelled")

    saved = repository.get_generation_run(run.run_id)
    assert saved.status == GenerationRunStatus.CANCELLED
    assert saved.current_scene_id is None
    items = repository.list_generation_run_items(run.run_id)
    assert all(i.is_terminal for i in items)
    repository.close()
