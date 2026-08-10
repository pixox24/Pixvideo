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
    assert Path(result.url).parent == (Path(__file__).parents[2] / "素材库" / "16x9").resolve()


@pytest.mark.asyncio
async def test_media_service_selects_portrait_storyboard_material(monkeypatch):
    monkeypatch.delenv("PIXELLE_USE_REAL_IMAGE_API")
    monkeypatch.delenv("PIXELLE_TEST_IMAGE_PATH", raising=False)

    service = MediaService({}, core=DummyCore())
    result = await service(prompt="portrait", width=1440, height=2560, scene_id="scene-2")

    assert Path(result.url).parent == (Path(__file__).parents[2] / "素材库" / "9x16").resolve()


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
