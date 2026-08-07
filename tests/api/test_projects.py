import pytest
from pydantic import ValidationError

from api.routers.projects import create_project, get_project
from api.schemas.workbench import CreateProjectRequest
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


class FakeCore:
    def __init__(self, tmp_path):
        self.workbench_repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
        self.workbench_media = WorkbenchMediaStore(tmp_path / "projects")


def test_create_project_accepts_100_explicit_scenes():
    request = CreateProjectRequest(
        title="长项目",
        scenes=[{"narration": f"旁白 {index}", "visualPrompt": f"画面 {index}"} for index in range(100)],
        config={"mediaWidth": 1080, "mediaHeight": 1920},
    )
    assert len(request.scenes) == 100


def test_create_project_rejects_blank_scene_narration():
    with pytest.raises(ValidationError):
        CreateProjectRequest(title="x", scenes=[{"narration": "  "}])


@pytest.mark.asyncio
async def test_create_and_read_project_response(tmp_path):
    core = FakeCore(tmp_path)
    body = CreateProjectRequest(title="项目", scenes=[{"narration": "第一段", "visualPrompt": "画面"}])

    created = await create_project(body, core, None)
    loaded = await get_project(created.project_id, core, None)

    assert created.project_id
    assert len(created.scenes) == 1
    assert created.scenes[0].narration == "第一段"
    assert loaded.project_id == created.project_id
    assert loaded.jobs == []
    core.workbench_repository.close()

