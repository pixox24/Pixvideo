from pathlib import Path

import pytest

from pixelle_video.models.workbench import ExportRevision
from pixelle_video.services.workbench_jobs import WorkbenchJobService


class FakeCore:
    config = {}

    async def generate_video(self, **kwargs):
        self.kwargs = kwargs
        return {"video_path": "output/final.mp4"}


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


@pytest.mark.asyncio
async def test_export_uses_frozen_existing_assets(tmp_path):
    root = tmp_path / "projects" / "p1"
    image = root / "assets" / "old.png"
    audio = root / "assets" / "audio.mp3"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    audio.write_bytes(b"audio")
    revision = ExportRevision("p1", {"config": {}, "scenes": [{"sceneId": "s1", "imagePath": "assets/old.png", "audioPath": "assets/audio.mp3"}]}, export_id="e1")
    core = FakeCore()
    await WorkbenchJobService(core, Repo(revision), Store(tmp_path / "projects")).run_export_job("p1", "e1", "t1")
    assert core.kwargs["existing_scene_assets"]["s1"]["image_path"].endswith("old.png")
