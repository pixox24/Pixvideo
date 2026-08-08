from pathlib import Path

import pytest

from pixelle_video.models.workbench import ExportRevision
from pixelle_video.services.workbench_jobs import WorkbenchJobService


class FakeCore:
    config = {}

    def __init__(self, output_path):
        self.output_path = Path(output_path)

    async def generate_video(self, **kwargs):
        self.kwargs = kwargs
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_bytes(b"fake-mp4")
        return {"video_path": str(self.output_path)}


class Store:
    def __init__(self, root):
        self.root = Path(root)

    def resolve(self, project_id, relative):
        return self.root / project_id / relative


class Repo:
    def __init__(self, revision):
        self.revision = revision
        self.updated = []

    def get_export_revision(self, export_id):
        return self.revision

    def update_export_revision(self, export_id, **changes):
        self.updated.append(changes)

    def list_active_export_revisions(self):
        return [self.revision]


@pytest.mark.asyncio
async def test_export_uses_frozen_existing_assets(tmp_path):
    root = tmp_path / "projects" / "p1"
    image = root / "assets" / "old.png"
    audio = root / "assets" / "audio.mp3"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    audio.write_bytes(b"audio")
    revision = ExportRevision("p1", {"config": {}, "scenes": [{"sceneId": "s1", "imagePath": "assets/old.png", "audioPath": "assets/audio.mp3", "durationSeconds": 3.5, "manualHoldSeconds": 1.5}]}, export_id="e1")
    core = FakeCore(tmp_path / "pipeline-output" / "final.mp4")
    repo = Repo(revision)
    await WorkbenchJobService(core, repo, Store(tmp_path / "projects")).run_export_job("p1", "e1", "t1")
    assert core.kwargs["existing_scene_assets"]["s1"]["image_path"].endswith("old.png")
    assert core.kwargs["existing_scene_assets"]["s1"]["audio_path"].endswith("audio.mp3")
    assert core.kwargs["existing_scene_assets"]["s1"]["duration_seconds"] == 2.0
    assert core.kwargs["existing_scene_assets"]["s1"]["manual_hold_seconds"] == 1.5
    assert (root / "exports" / "e1.mp4").read_bytes() == b"fake-mp4"
    assert repo.updated[-1]["output_relative_path"] == "exports/e1.mp4"


@pytest.mark.asyncio
async def test_export_rejects_incomplete_snapshot_without_calling_pipeline(tmp_path):
    revision = ExportRevision(
        "p1",
        {"config": {}, "scenes": [{"sceneId": "s1", "imagePath": "assets/old.png", "audioPath": None}]},
        export_id="e1",
    )
    core = FakeCore(tmp_path / "pipeline-output" / "final.mp4")
    repo = Repo(revision)

    with pytest.raises(ValueError, match="incomplete scene"):
        await WorkbenchJobService(core, repo, Store(tmp_path / "projects")).run_export_job("p1", "e1", "t1")

    assert not hasattr(core, "kwargs")
    assert repo.updated[-1]["status"].value == "failed"


@pytest.mark.asyncio
async def test_export_rejects_legacy_local_bgm_path_without_calling_pipeline(tmp_path):
    root = tmp_path / "projects" / "p1"
    image = root / "assets" / "old.png"
    audio = root / "assets" / "audio.mp3"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    audio.write_bytes(b"audio")
    revision = ExportRevision(
        "p1",
        {
            "config": {"bgm": "/private/secret.mp3"},
            "scenes": [{"sceneId": "s1", "imagePath": "assets/old.png", "audioPath": "assets/audio.mp3"}],
        },
        export_id="e1",
    )
    core = FakeCore(tmp_path / "pipeline-output" / "final.mp4")
    repo = Repo(revision)

    with pytest.raises(ValueError, match="unsupported BGM reference"):
        await WorkbenchJobService(core, repo, Store(tmp_path / "projects")).run_export_job("p1", "e1", "t1")

    assert not hasattr(core, "kwargs")


@pytest.mark.asyncio
async def test_active_export_resumes_with_original_revision(tmp_path):
    root = tmp_path / "projects" / "p1"
    image = root / "assets" / "old.png"
    audio = root / "assets" / "audio.mp3"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    audio.write_bytes(b"audio")
    revision = ExportRevision(
        "p1",
        {"config": {}, "scenes": [{"sceneId": "s1", "imagePath": "assets/old.png", "audioPath": "assets/audio.mp3"}]},
        export_id="original-export",
    )
    core = FakeCore(tmp_path / "pipeline-output" / "final.mp4")
    repo = Repo(revision)

    class Manager:
        def create_task(self, *_args, **_kwargs):
            return type("Task", (), {"task_id": "resumed-task"})()

        async def execute_task(self, _task_id, func, *args):
            await func(*args)

    task_ids = await WorkbenchJobService(core, repo, Store(tmp_path / "projects")).resume_active_exports(Manager())

    assert task_ids == ["resumed-task"]
    assert (root / "exports" / "original-export.mp4").is_file()
    assert core.kwargs["existing_scene_assets"]["s1"]["image_path"].endswith("old.png")
