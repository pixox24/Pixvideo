import httpx
import pytest

from pixelle_video.services.media import MediaService


class DummyCore:
    pass


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
