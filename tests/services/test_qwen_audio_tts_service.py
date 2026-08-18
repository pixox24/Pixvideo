import base64

import httpx
import pytest

from pixelle_video.services.tts_service import TTSService


class _Core:
    config = {}


@pytest.mark.asyncio
async def test_qwen_audio_tts_posts_dashscope_payload_and_decodes_audio(tmp_path, monkeypatch):
    captured = {}

    async def fake_post(self, url, *, json=None, headers=None):
        captured.update(url=url, json=json, headers=headers)
        return httpx.Response(
            200,
            json={"output": {"audio": {"data": base64.b64encode(b"fake audio").decode()} }},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setenv("DASHSCOPE_API_KEY", "env-key")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    output = tmp_path / "qwen.mp3"
    service = TTSService({"qwen_audio": {}}, core=_Core())

    result = await service(
        text="你好",
        inference_mode="qwen_audio",
        voice="Cherry",
        speed=1.1,
        output_path=str(output),
    )

    assert result == str(output)
    assert output.read_bytes() == b"fake audio"
    assert captured["headers"]["Authorization"] == "Bearer env-key"
    assert captured["json"]["model"] == "qwen3-tts-flash"
    assert captured["json"]["input"] == {"text": "你好"}
    assert captured["json"]["parameters"]["voice"] == "Cherry"
    assert captured["json"]["parameters"]["rate"] == 1.1


@pytest.mark.asyncio
async def test_qwen_audio_requires_dashscope_key(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    service = TTSService({"qwen_audio": {"api_key": ""}}, core=_Core())

    with pytest.raises(ValueError, match="DashScope API key is not configured"):
        await service("hello", inference_mode="qwen_audio")
