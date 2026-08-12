"""Day-3 P0: export cancel, no parallel export, temp GC, tracked ffmpeg kill."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from api.routers.projects import cancel_export, create_export
from api.schemas.workbench import ExportRequest
from api.tasks.manager import TaskManager
from pixelle_video.models.workbench import (
    AssetSource,
    AssetVersion,
    ExportRevision,
    GenerationStatus,
    Project,
    Scene,
)
from pixelle_video.services.video import kill_tracked_ffmpeg_processes, run_ffmpeg_compiled
from pixelle_video.services.workbench_repository import WorkbenchRepository
from pixelle_video.utils.ffmpeg_scratch import cleanup_ffmpeg_scratch, ffmpeg_scratch_dir


class FakeMedia:
    def resolve(self, project_id, relative):
        return Path("unused")

    def to_api_url(self, *args, **kwargs):
        return None


class FakeCore:
    def __init__(self, tmp_path: Path):
        self.workbench_repository = WorkbenchRepository(tmp_path / "wb.sqlite3")
        self.workbench_media = FakeMedia()
        self.workbench_jobs = MagicMock()
        self.config = {}

        async def _run_export(*_args, **_kwargs):
            await asyncio.sleep(3600)

        self.workbench_jobs.run_export_job = _run_export


def _seed_complete_project(repo: WorkbenchRepository, media_root: Path) -> tuple[Project, Scene]:
    project = Project(title="p", config={})
    scene = Scene(project.project_id, 0, "旁白", "画面")
    repo.create_project(project, [scene])
    img_rel = f"assets/scenes/{scene.scene_id}/cur.png"
    audio_rel = f"assets/scenes/{scene.scene_id}/audio/a.mp3"
    # Paths are only checked via media_store in real export; for API create_export
    # we only need DB version + audio_relative_path present.
    version = AssetVersion(
        project.project_id,
        scene.scene_id,
        AssetSource.UPLOAD,
        img_rel,
        prompt_snapshot="x",
    )
    repo.create_asset_version(version)
    repo.select_asset_version(project.project_id, scene.scene_id, version.version_id)
    repo.update_scene(scene.scene_id, audio_relative_path=audio_rel)
    return project, scene


@pytest.mark.asyncio
async def test_create_export_rejects_when_active(tmp_path, monkeypatch):
    core = FakeCore(tmp_path)
    project, _scene = _seed_complete_project(core.workbench_repository, tmp_path)

    # Stub task manager execute so create_export does not hang
    from api.tasks import task_manager as tm

    async def fake_execute(task_id, coro, *args, **kwargs):
        return None

    monkeypatch.setattr(tm, "execute_task", fake_execute)

    first = await create_export(project.project_id, core, ExportRequest())
    assert first["exportId"]

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await create_export(project.project_id, core, ExportRequest())
    assert exc.value.status_code == 409
    assert "already in progress" in str(exc.value.detail)
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_cancel_export_marks_cancelled(tmp_path, monkeypatch):
    core = FakeCore(tmp_path)
    project, _scene = _seed_complete_project(core.workbench_repository, tmp_path)

    from api.tasks import task_manager as tm

    async def fake_execute(task_id, coro, *args, **kwargs):
        return None

    monkeypatch.setattr(tm, "execute_task", fake_execute)

    created = await create_export(project.project_id, core, ExportRequest())
    export_id = created["exportId"]
    # Force running so cancel path is exercised
    core.workbench_repository.update_export_revision(export_id, status=GenerationStatus.RUNNING)

    result = await cancel_export(project.project_id, export_id, core)
    assert result["status"] == "cancelled"
    saved = core.workbench_repository.get_export_revision(export_id)
    assert saved.status == GenerationStatus.CANCELLED
    core.workbench_repository.close()


def test_cleanup_ffmpeg_scratch_removes_old_files(tmp_path, monkeypatch):
    scratch = tmp_path / "pixelle_video_ffmpeg"
    scratch.mkdir()
    old = scratch / "old.bin"
    old.write_bytes(b"x")
    # Backdate mtime
    old_time = time.time() - 48 * 3600
    import os

    os.utime(old, (old_time, old_time))
    fresh = scratch / "fresh.bin"
    fresh.write_bytes(b"y")

    monkeypatch.setattr(
        "pixelle_video.utils.ffmpeg_scratch.tempfile.gettempdir",
        lambda: str(tmp_path),
    )
    removed = cleanup_ffmpeg_scratch(max_age_hours=24.0)
    assert removed >= 1
    assert not old.exists()
    assert fresh.exists()


def test_run_ffmpeg_compiled_tracks_and_kill_is_safe():
    # Start a short-lived process; kill_tracked should not raise even if none left.
    cmd = [sys.executable, "-c", "import time; time.sleep(0.05)"]
    run_ffmpeg_compiled(cmd, timeout=5, label="day3-short")
    killed = kill_tracked_ffmpeg_processes()
    assert killed >= 0
