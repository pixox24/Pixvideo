from pathlib import Path

import pytest
from PIL import Image

from api.routers.projects import create_project_from_history
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


class Frame:
    def __init__(self, index, image_path, audio_path):
        self.narration = f"scene {index}"
        self.image_prompt = f"prompt {index}"
        self.image_path = str(image_path)
        self.audio_path = str(audio_path)
        self.duration = 2.0
        self.status = "completed"


class History:
    def __init__(self, storyboard):
        self.storyboard = storyboard

    async def get_task_detail(self, task_id):
        return {"metadata": {"input": {"mediaWidth": 1080}}, "storyboard": self.storyboard}


class Core:
    def __init__(self, tmp_path, storyboard):
        self.workbench_repository = WorkbenchRepository(tmp_path / "db.sqlite3")
        self.workbench_media = WorkbenchMediaStore(tmp_path / "projects")
        self.history = History(storyboard)


@pytest.mark.asyncio
async def test_history_task_materializes_once_without_deleting_original(tmp_path):
    frames = []
    for index in range(2):
        image = tmp_path / f"image-{index}.png"
        Image.new("RGB", (8, 8), "red").save(image)
        audio = tmp_path / f"audio-{index}.mp3"
        audio.write_bytes(b"audio")
        frames.append(Frame(index, image, audio))
    storyboard = type("Storyboard", (), {"title": "legacy", "frames": frames})()
    core = Core(tmp_path, storyboard)

    first = await create_project_from_history("legacy-task", core, None)
    second = await create_project_from_history("legacy-task", core, None)

    assert first.project_id == second.project_id
    assert len(first.scenes) == 2
    assert (tmp_path / "image-0.png").is_file()
    core.workbench_repository.close()

