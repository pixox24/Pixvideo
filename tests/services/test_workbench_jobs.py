from pathlib import Path

import pytest
from PIL import Image

from pixelle_video.models.workbench import Project, Scene
from pixelle_video.services.workbench_jobs import WorkbenchJobService
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


class FakeCore:
    config = {"comfyui": {"image": {"default_workflow": "test"}, "tts": {"inference_mode": "comfyui"}}}
    frame_processor = None

    def __init__(self):
        self.tts_kwargs = None

    async def tts(self, text, output_path=None, **kwargs):
        self.tts_kwargs = kwargs
        Path(output_path).write_bytes(b"audio")
        return output_path

    async def media(self, **kwargs):
        return type("Result", (), {"url": "local-result.png"})()


class CapturingCore(FakeCore):
    def __init__(self):
        self.media_kwargs = None

    async def media(self, **kwargs):
        self.media_kwargs = kwargs
        return await super().media(**kwargs)


class LocalImageCore(FakeCore):
    def __init__(self, image_path: Path):
        self.image_path = image_path

    async def media(self, **kwargs):
        return type("Result", (), {"url": str(self.image_path)})()


class FakeMediaStore(WorkbenchMediaStore):
    async def download_result(self, project_id, scene_id, source_url, version_id):
        relative = f"assets/scenes/{scene_id}/generated/{version_id}.png"
        path = self.resolve(project_id, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (32, 32), "blue").save(path)
        return relative


@pytest.mark.asyncio
async def test_scene_job_creates_audio_and_first_image_as_current_version(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    project = Project(title="p", config={})
    scene = Scene(project.project_id, 0, "旁白", "画面")
    repository.create_project(project, [scene])
    service = WorkbenchJobService(FakeCore(), repository, media_store)

    await service.run_scene_job(project.project_id, scene.scene_id, "t1")

    saved = repository.get_scene(scene.scene_id)
    assert saved.current_version_id is not None
    assert saved.audio_relative_path.endswith(".mp3")
    assert saved.status == "completed"
    assert len(repository.list_asset_versions(project.project_id, scene.scene_id)) == 1
    repository.close()


@pytest.mark.asyncio
async def test_generate_tts_uses_project_edge_mode_not_global_comfyui(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    project = Project(title="p", config={"ttsMode": "edge", "voice": "zh-CN-XiaoxiaoNeural", "speed": 1.0})
    scene = Scene(project.project_id, 0, "旁白文本", "画面")
    repository.create_project(project, [scene])
    core = FakeCore()
    service = WorkbenchJobService(core, repository, media_store)

    await service.generate_tts_asset(project.project_id, scene.scene_id, "tts-task", "旁白文本")

    assert core.tts_kwargs is not None
    assert core.tts_kwargs.get("inference_mode") == "local"
    assert core.tts_kwargs.get("voice") == "zh-CN-XiaoxiaoNeural"
    repository.close()


@pytest.mark.asyncio
async def test_generate_tts_mimo_ignores_minimax_model_in_payload(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    project = Project(
        title="p",
        config={
            "ttsMode": "mimo",
            "voice": "冰糖",
            "minimaxModel": "speech-2.8-turbo",
            "mimoModel": "mimo-v2.5-tts",
            "mimoStyle": "自然",
        },
    )
    scene = Scene(project.project_id, 0, "旁白文本", "画面")
    repository.create_project(project, [scene])
    core = FakeCore()
    service = WorkbenchJobService(core, repository, media_store)

    await service.generate_tts_asset(project.project_id, scene.scene_id, "tts-task", "旁白文本")

    assert core.tts_kwargs.get("inference_mode") == "mimo"
    assert core.tts_kwargs.get("mimo_model") == "mimo-v2.5-tts"
    assert core.tts_kwargs.get("mimo_style") == "自然"
    assert core.tts_kwargs.get("minimax_model") is None
    repository.close()


@pytest.mark.asyncio
async def test_generate_tts_falls_back_to_edge_when_comfyui_unavailable(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    project = Project(title="p", config={"ttsMode": "comfyui"})
    scene = Scene(project.project_id, 0, "旁白文本", "画面")
    repository.create_project(project, [scene])

    class ComfyFailCore(FakeCore):
        async def tts(self, text, output_path=None, **kwargs):
            self.tts_kwargs = kwargs
            if kwargs.get("inference_mode") == "comfyui":
                raise ConnectionError("Cannot connect to host 127.0.0.1:8188")
            Path(output_path).write_bytes(b"audio")
            return output_path

    core = ComfyFailCore()
    service = WorkbenchJobService(core, repository, media_store)
    await service.generate_tts_asset(project.project_id, scene.scene_id, "tts-task", "旁白文本")
    assert core.tts_kwargs.get("inference_mode") == "local"
    repository.close()


@pytest.mark.asyncio
async def test_image_job_appends_candidate_without_replacing_current(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    project = Project(title="p", config={})
    scene = Scene(project.project_id, 0, "旁白", "旧")
    repository.create_project(project, [scene])
    service = WorkbenchJobService(FakeCore(), repository, media_store)

    await service.run_image_job(project.project_id, scene.scene_id, "t1", "旧")
    first = repository.get_scene(scene.scene_id).current_version_id
    await service.run_image_job(project.project_id, scene.scene_id, "t2", "新")

    assert repository.get_scene(scene.scene_id).current_version_id == first
    assert len(repository.list_asset_versions(project.project_id, scene.scene_id)) == 2
    repository.close()


@pytest.mark.asyncio
async def test_image_job_uses_project_canvas_size_and_persists_workbench_asset(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    # Advanced canvas 2560×1440 → image gen maps to API whitelist (1920×1080)
    project = Project(title="landscape", config={"mediaWidth": 2560, "mediaHeight": 1440})
    scene = Scene(project.project_id, 0, "Narration", "Visual prompt")
    repository.create_project(project, [scene])
    core = CapturingCore()
    service = WorkbenchJobService(core, repository, media_store)

    await service.run_image_job(project.project_id, scene.scene_id, "t1", scene.visual_prompt)

    assert core.media_kwargs["width"] == 1920
    assert core.media_kwargs["height"] == 1080
    saved = repository.get_scene(scene.scene_id)
    version = repository.get_asset_version(saved.current_version_id)
    assert media_store.resolve(project.project_id, version.relative_path).is_file()
    assert media_store.resolve(project.project_id, version.thumbnail_relative_path).is_file()
    repository.close()


@pytest.mark.asyncio
async def test_image_job_default_canvas_maps_to_portrait_whitelist(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = FakeMediaStore(tmp_path / "projects")
    project = Project(title="default-portrait", config={})
    scene = Scene(project.project_id, 0, "Narration", "Visual prompt")
    repository.create_project(project, [scene])
    core = CapturingCore()
    service = WorkbenchJobService(core, repository, media_store)

    await service.run_image_job(project.project_id, scene.scene_id, "t1", scene.visual_prompt)

    # Default 1080×1920 is itself on the whitelist
    assert core.media_kwargs["width"] == 1080
    assert core.media_kwargs["height"] == 1920
    repository.close()


@pytest.mark.asyncio
async def test_image_job_imports_a_local_material_into_project_assets(tmp_path):
    source = tmp_path / "local-material.png"
    Image.new("RGB", (64, 64), "green").save(source)
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = WorkbenchMediaStore(tmp_path / "projects")
    project = Project(title="p", config={})
    scene = Scene(project.project_id, 0, "Narration", "Visual prompt")
    repository.create_project(project, [scene])
    service = WorkbenchJobService(LocalImageCore(source), repository, media_store)

    await service.run_image_job(project.project_id, scene.scene_id, "t1", scene.visual_prompt)

    saved = repository.get_scene(scene.scene_id)
    version = repository.get_asset_version(saved.current_version_id)
    assert version is not None
    assert media_store.resolve(project.project_id, version.relative_path).is_file()
    assert media_store.resolve(project.project_id, version.thumbnail_relative_path).is_file()
    repository.close()

