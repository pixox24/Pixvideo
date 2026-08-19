import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.config import APIConfig
from api.routers.projects import create_project, get_project, get_project_media, update_project
from api.schemas.workbench import CreateProjectRequest, ProjectUpdateRequest
from pixelle_video.models.workbench import ExportRevision, GenerationRun, GenerationStatus
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


class FakeCore:
    def __init__(self, tmp_path):
        self.workbench_repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
        self.workbench_media = WorkbenchMediaStore(tmp_path / "projects")


def test_api_defaults_are_loopback_only():
    config = APIConfig()
    assert config.host == "127.0.0.1"
    assert "*" not in config.cors_origins


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


@pytest.mark.asyncio
async def test_project_persists_director_metadata_and_lock_state(tmp_path):
    core = FakeCore(tmp_path)
    body = CreateProjectRequest(
        title="导演台元数据",
        config={"directorMode": "custom", "density": "dense", "targetSceneCount": 4},
        scenes=[{
            "narration": "星期一开始执行",
            "visualPrompt": "日历特写",
            "visualFocus": "星期一日历",
            "textAnchors": ["星期一"],
            "lockedFields": ["visualPrompt"],
            "editedFields": ["visualPrompt"],
            "locked": True,
        }],
    )

    created = await create_project(body, core, None)
    loaded = await get_project(created.project_id, core, None)

    scene = loaded.scenes[0]
    assert loaded.config["directorMode"] == "custom"
    assert loaded.config["density"] == "dense"
    assert scene.visual_focus == "星期一日历"
    assert scene.text_anchors == ["星期一"]
    assert scene.locked_fields == ["visualPrompt"]
    assert scene.edited_fields == ["visualPrompt"]
    assert scene.locked is True
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_create_project_auto_expands_one_long_scene_with_validated_segments(tmp_path, monkeypatch):
    core = FakeCore(tmp_path)
    core.llm = object()
    source = "今天我们从日历开始规划发布会倒计时并把每一个任务安排到准确的时间线上同时检查人员物料场地和最终确认清单确保发布当天万无一失"
    calls = []

    async def fake_segment(*_args, **_kwargs):
        calls.append((_args, _kwargs))
        return [
            {"text": "今天我们从日历开始规划发布会倒计时", "boundary_reason": "时间锚点", "visual_focus": "日历"},
            {"text": "并把每一个任务安排到准确的时间线上同时检查人员物料场地和最终确认清单确保发布当天万无一失", "boundary_reason": "执行动作", "visual_focus": "时间线"},
        ]

    monkeypatch.setattr("api.routers.projects.segment_narration_semantically", fake_segment)
    async def skip_autofill(*_args, **_kwargs):
        return None

    monkeypatch.setattr("api.routers.projects._autofill_image_prompts", skip_autofill)
    created = await create_project(
        CreateProjectRequest(
            title="自动分镜",
            config={"splitType": "auto", "sceneCount": 3},
            scenes=[{"narration": source}],
        ),
        core,
        None,
    )

    assert len(created.scenes) == 2
    assert [scene.narration for scene in created.scenes] == [
        "今天我们从日历开始规划发布会倒计时",
        "并把每一个任务安排到准确的时间线上同时检查人员物料场地和最终确认清单确保发布当天万无一失",
    ]
    assert calls
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_create_project_rejects_missing_visual_prompts(tmp_path, monkeypatch):
    core = FakeCore(tmp_path)
    monkeypatch.setattr(
        "api.routers.projects.config_manager.get_llm_config",
        lambda: {"api_key": "", "base_url": "", "model": ""},
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_project(
            CreateProjectRequest(
                title="禁止空提示词",
                config={"useApiImage": True},
                scenes=[{"narration": "旁白内容"}],
            ),
            core,
            None,
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "visual_prompt_generation_failed"
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_create_project_manual_visual_prompt_disables_auto_resegmentation(tmp_path, monkeypatch):
    core = FakeCore(tmp_path)
    core.llm = object()
    calls = []

    async def fail_if_called(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("manual visual prompts must prevent auto resegmentation")

    monkeypatch.setattr("api.routers.projects.segment_narration_semantically", fail_if_called)
    source = "今天我们从日历开始规划发布会倒计时并把每一个任务安排到准确的时间线上同时检查人员物料场地和最终确认清单确保发布当天万无一失"
    created = await create_project(
        CreateProjectRequest(
            title="保留手工场景",
            config={"splitType": "auto", "sceneCount": 3},
            scenes=[{"narration": source, "visualPrompt": "手工指定的日历特写"}],
        ),
        core,
        None,
    )

    assert len(created.scenes) == 1
    assert created.scenes[0].visual_prompt == "手工指定的日历特写"
    assert calls == []
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_project_media_url_and_endpoint(tmp_path):
    core = FakeCore(tmp_path)
    body = CreateProjectRequest(title="媒体", scenes=[{"narration": "旁白", "visualPrompt": "画面"}])
    created = await create_project(body, core, None)
    scene = created.scenes[0]
    relative = f"assets/scenes/{scene.scene_id}/generated/test.png"
    file_path = core.workbench_media.resolve(created.project_id, relative)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"\x89PNG\r\n\x1a\nfake-image-content")

    image_url = core.workbench_media.to_api_url(created.project_id, relative, None)
    assert image_url.startswith(f"/api/projects/{created.project_id}/media/")

    response = await get_project_media(created.project_id, relative, core)
    assert response.status_code == 200
    assert response.media_type == "image/png"
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_project_media_missing_file_404(tmp_path):
    core = FakeCore(tmp_path)
    body = CreateProjectRequest(title="缺失", scenes=[{"narration": "旁白", "visualPrompt": "画面"}])
    created = await create_project(body, core, None)
    with pytest.raises(Exception) as exc_info:
        await get_project_media(created.project_id, "assets/scenes/nope/missing.png", core)
    assert exc_info.value.status_code == 404
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_update_project_merges_editor_config_and_preserves_server_config(tmp_path):
    core = FakeCore(tmp_path)
    created = await create_project(
        CreateProjectRequest(title="项目", config={"bgmVolume": 30, "serverSecret": "keep"}, scenes=[{"narration": "旁白"}]),
        core,
        None,
    )

    updated = await update_project(
        created.project_id,
        ProjectUpdateRequest(title="新标题", config={"bgmVolume": 50}),
        core,
        None,
    )

    assert updated.title == "新标题"
    assert updated.config["bgmVolume"] == 50
    assert updated.config["serverSecret"] == "keep"
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_update_project_config_only_allows_stale_occ_title_does_not(tmp_path):
    core = FakeCore(tmp_path)
    created = await create_project(CreateProjectRequest(title="项目", scenes=[{"narration": "旁白"}]), core, None)

    # Day3: config-only saves skip OCC (scene updates during generation bump updated_at).
    updated = await update_project(
        created.project_id,
        ProjectUpdateRequest(config={"bgmVolume": 50}, expectedUpdatedAt="stale"),
        core,
        None,
    )
    assert updated.config["bgmVolume"] == 50

    with pytest.raises(HTTPException) as stale_title:
        await update_project(
            created.project_id,
            ProjectUpdateRequest(title="新标题", expectedUpdatedAt="stale"),
            core,
            None,
        )
    assert stale_title.value.status_code == 409

    with pytest.raises(HTTPException) as unknown:
        await update_project(
            created.project_id,
            ProjectUpdateRequest(config={"notAnEditorKey": True}),
            core,
            None,
        )
    assert unknown.value.status_code == 422
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_project_bgm_rejects_local_paths_and_accepts_discovered_resources(tmp_path, monkeypatch):
    core = FakeCore(tmp_path)
    with pytest.raises(HTTPException) as error:
        await create_project(
            CreateProjectRequest(
                title="项目",
                config={"bgm": "/etc/passwd"},
                scenes=[{"narration": "旁白"}],
            ),
            core,
            None,
        )
    assert error.value.status_code == 422

    bgm_dir = tmp_path / "bgm"
    bgm_dir.mkdir()
    (bgm_dir / "approved.mp3").write_bytes(b"audio")
    monkeypatch.setattr("api.routers.projects.get_data_path", lambda *_parts: str(bgm_dir))
    created = await create_project(
        CreateProjectRequest(
            title="项目",
            config={"bgm": "data/bgm/approved.mp3"},
            scenes=[{"narration": "旁白"}],
        ),
        core,
        None,
    )
    assert created.config["bgm"] == "data/bgm/approved.mp3"
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_project_dirty_tracks_last_completed_export(tmp_path):
    core = FakeCore(tmp_path)
    created = await create_project(CreateProjectRequest(title="项目", scenes=[{"narration": "旁白"}]), core, None)
    assert created.dirty is True

    revision = ExportRevision(created.project_id, {"purpose": "manual"})
    core.workbench_repository.create_export_revision(revision)
    core.workbench_repository.update_export_revision(revision.export_id, status=GenerationStatus.COMPLETED)
    exported = await get_project(created.project_id, core, None)
    assert exported.dirty is False

    await update_project(created.project_id, ProjectUpdateRequest(config={"bgmVolume": 50}), core, None)
    edited = await get_project(created.project_id, core, None)
    assert edited.dirty is True
    core.workbench_repository.close()


@pytest.mark.asyncio
async def test_project_update_does_not_mutate_active_run_snapshot(tmp_path):
    core = FakeCore(tmp_path)
    created = await create_project(CreateProjectRequest(title="项目", scenes=[{"narration": "旁白"}]), core, None)
    run = GenerationRun(created.project_id, "task-1", {"bgmVolume": 30})
    core.workbench_repository.create_generation_run(run, [])

    await update_project(created.project_id, ProjectUpdateRequest(config={"bgmVolume": 50}), core, None)

    assert core.workbench_repository.get_generation_run(run.run_id).parameter_snapshot == {"bgmVolume": 30}
    core.workbench_repository.close()
