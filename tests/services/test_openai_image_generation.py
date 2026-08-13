from pathlib import Path

import httpx
import pytest

from pixelle_video.services.media import MediaService


class DummyCore:
    pass


@pytest.fixture(autouse=True)
def enable_mocked_image_provider(monkeypatch):
    monkeypatch.setenv("PIXELLE_USE_REAL_IMAGE_API", "1")


@pytest.mark.asyncio
async def test_media_service_uses_existing_local_image_by_default(monkeypatch):
    monkeypatch.delenv("PIXELLE_USE_REAL_IMAGE_API")
    monkeypatch.delenv("PIXELLE_TEST_IMAGE_PATH", raising=False)
    monkeypatch.setattr(
        "pixelle_video.services.media.config_manager.get_image_generation_config",
        lambda: {"api_key": "must-not-run", "base_url": "https://api.example.com", "model": "test"},
    )

    service = MediaService({}, core=DummyCore())
    result = await service(prompt="must stay offline", width=2560, height=1440, scene_id="scene-1")

    assert result.media_type == "image"
    parent = Path(result.url).parent
    library = (Path(__file__).parents[2] / "素材库").resolve()
    # Windows installs typically use 16x9; macOS/Linux often keep 16:9.
    assert parent in {library / name for name in ("16x9", "16:9", "16-9")}
    assert Path(result.url).is_file()


@pytest.mark.asyncio
async def test_use_api_image_false_overrides_env_and_uses_material_library(monkeypatch):
    """Product toggle off must force 素材库 even when PIXELLE_USE_REAL_IMAGE_API is set."""
    monkeypatch.setenv("PIXELLE_USE_REAL_IMAGE_API", "1")
    monkeypatch.delenv("PIXELLE_TEST_IMAGE_PATH", raising=False)
    monkeypatch.setattr(
        "pixelle_video.services.media.config_manager.get_image_generation_config",
        lambda: {"api_key": "must-not-run", "base_url": "https://api.example.com", "model": "test"},
    )

    service = MediaService({}, core=DummyCore())
    result = await service(
        prompt="offline library",
        width=1080,
        height=1920,
        scene_id="scene-lib",
        use_api_image=False,
    )

    parent = Path(result.url).parent
    library = (Path(__file__).parents[2] / "素材库").resolve()
    assert parent in {library / name for name in ("9x16", "9:16", "9-16")}
    assert Path(result.url).is_file()


@pytest.mark.asyncio
async def test_use_api_image_true_calls_openai_compatible_api(monkeypatch):
    captured = {}

    async def fake_post(self, url, *, headers=None, json=None):
        captured["url"] = url
        captured["json"] = json
        return httpx.Response(
            200,
            json={"data": [{"url": "https://cdn.example.com/api-on.png"}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.delenv("PIXELLE_USE_REAL_IMAGE_API", raising=False)
    monkeypatch.setattr(
        "pixelle_video.services.media.config_manager.get_image_generation_config",
        lambda: {
            "api_key": "img-key",
            "base_url": "https://img-cn.65535.space/v1",
            "model": "gpt-image-2",
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    service = MediaService({}, core=DummyCore())
    result = await service(
        prompt="api toggle on",
        width=1280,
        height=720,
        use_api_image=True,
    )

    assert result.url == "https://cdn.example.com/api-on.png"
    assert captured["url"] == "https://img-cn.65535.space/v1/images/generations"
    assert captured["json"]["prompt"] == "api toggle on"


@pytest.mark.asyncio
async def test_media_service_selects_portrait_storyboard_material(monkeypatch):
    monkeypatch.delenv("PIXELLE_USE_REAL_IMAGE_API")
    monkeypatch.delenv("PIXELLE_TEST_IMAGE_PATH", raising=False)

    service = MediaService({}, core=DummyCore())
    result = await service(prompt="portrait", width=1440, height=2560, scene_id="scene-2")

    parent = Path(result.url).parent
    library = (Path(__file__).parents[2] / "素材库").resolve()
    assert parent in {library / name for name in ("9x16", "9:16", "9-16")}
    assert Path(result.url).is_file()


def test_resolve_storyboard_ratio_dir_accepts_windows_and_macos_names(tmp_path):
    """Windows forbids ':' so folders are 16x9; macOS often keeps 16:9."""
    win_lib = tmp_path / "win"
    (win_lib / "16x9").mkdir(parents=True)
    (win_lib / "9x16").mkdir(parents=True)
    assert MediaService._resolve_storyboard_ratio_dir(win_lib, landscape=True).name == "16x9"
    assert MediaService._resolve_storyboard_ratio_dir(win_lib, landscape=False).name == "9x16"

    mac_lib = tmp_path / "mac"
    (mac_lib / "16:9").mkdir(parents=True)
    (mac_lib / "9:16").mkdir(parents=True)
    assert MediaService._resolve_storyboard_ratio_dir(mac_lib, landscape=True).name == "16:9"
    assert MediaService._resolve_storyboard_ratio_dir(mac_lib, landscape=False).name == "9:16"

    mixed = tmp_path / "mixed"
    (mixed / "16-9").mkdir(parents=True)
    (mixed / "portrait").mkdir(parents=True)
    assert MediaService._resolve_storyboard_ratio_dir(mixed, landscape=True).name == "16-9"
    assert MediaService._resolve_storyboard_ratio_dir(mixed, landscape=False).name == "portrait"


@pytest.mark.asyncio
async def test_media_service_uses_configured_openai_compatible_image_api(monkeypatch):
    captured = {}

    async def fake_post(self, url, *, headers=None, json=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(
            200,
            json={"data": [{"url": "https://cdn.example.com/generated.png"}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(
        "pixelle_video.services.media.config_manager.get_image_generation_config",
        lambda: {
            "api_key": "img-key",
            "base_url": "https://img-cn.65535.space/v1",
            "model": "gpt-image-2",
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    service = MediaService({}, core=DummyCore())
    result = await service(prompt="a cinematic robot", width=1280, height=720)

    assert result.media_type == "image"
    assert result.url == "https://cdn.example.com/generated.png"
    assert captured["url"] == "https://img-cn.65535.space/v1/images/generations"
    assert captured["headers"]["Authorization"] == "Bearer img-key"
    assert captured["json"]["model"] == "gpt-image-2"
    assert captured["json"]["prompt"] == "a cinematic robot"
    assert captured["json"]["n"] == 1
    assert captured["json"]["size"] == "1280x720"


@pytest.mark.asyncio
async def test_media_service_adds_https_to_schemeless_image_base_url(monkeypatch):
    captured = {}

    async def fake_post(self, url, *, headers=None, json=None):
        captured["url"] = url
        return httpx.Response(
            200,
            json={"data": [{"url": "https://cdn.example.com/generated.png"}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(
        "pixelle_video.services.media.config_manager.get_image_generation_config",
        lambda: {
            "api_key": "img-key",
            "base_url": "img-cn.65535.space/v1",
            "model": "gpt-image-2",
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    service = MediaService({}, core=DummyCore())
    result = await service(prompt="a cinematic robot", width=1280, height=720)

    assert result.url == "https://cdn.example.com/generated.png"
    assert captured["url"] == "https://img-cn.65535.space/v1/images/generations"


@pytest.mark.asyncio
async def test_media_service_normalizes_schemeless_openai_image_status_url(monkeypatch):
    captured = {}

    async def fake_post(self, url, *, headers=None, json=None):
        return httpx.Response(
            202,
            json={
                "data": {
                    "job_id": "job-123",
                    "status_url": "img-cn.65535.space/v1/images/async-generations/job-123",
                }
            },
            request=httpx.Request("POST", url),
        )

    async def fake_poll(self, client, poll_url, headers):
        captured["poll_url"] = poll_url
        return "https://cdn.example.com/generated.png"

    monkeypatch.setattr(
        "pixelle_video.services.media.config_manager.get_image_generation_config",
        lambda: {
            "api_key": "img-key",
            "base_url": "https://img-cn.65535.space/v1",
            "model": "gpt-image-2",
        },
    )
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(MediaService, "_poll_openai_image_job", fake_poll)

    service = MediaService({}, core=DummyCore())
    result = await service(prompt="a cinematic robot", width=1024, height=1536)

    assert result.url == "https://cdn.example.com/generated.png"
    assert captured["poll_url"] == "https://img-cn.65535.space/v1/images/async-generations/job-123"


def test_media_service_normalizes_relative_openai_image_status_urls():
    service = MediaService({}, core=DummyCore())

    assert (
        service._normalize_openai_image_status_url(
            base_url="https://img-cn.65535.space/v1",
            status_url="images/async-generations/job-123",
            job_id="job-123",
        )
        == "https://img-cn.65535.space/v1/images/async-generations/job-123"
    )
    assert (
        service._normalize_openai_image_status_url(
            base_url="https://img-cn.65535.space/v1",
            status_url="/v1/images/async-generations/job-123",
            job_id="job-123",
        )
        == "https://img-cn.65535.space/v1/images/async-generations/job-123"
    )
