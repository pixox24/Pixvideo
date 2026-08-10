import base64
from pathlib import Path

import httpx
import pytest

from pixelle_video.config.manager import ConfigManager
from pixelle_video.services.tts_service import TTSService


class DummyCore:
    pass


@pytest.mark.asyncio
async def test_mimo_tts_decodes_base64_audio_and_writes_output(tmp_path, monkeypatch):
    captured = {}

    async def fake_post(self, url, *, json=None, headers=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "audio": {"data": base64.b64encode(b"fake wav").decode("utf-8")}
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    service = TTSService(
        {
            "mimo": {
                "api_key": "sk-test",
                "model": "mimo-v2.5-tts",
                "voice_id": "Chloe",
                "style": "Bright and cheerful",
            }
        },
        core=DummyCore(),
    )
    output_path = tmp_path / "audio.wav"

    result = await service(
        text="大家好",
        inference_mode="mimo",
        output_path=str(output_path),
        voice="Dean",
        mimo_model="mimo-v2.5-tts-voicedesign",
        mimo_style="Deep male narrator",
    )

    assert result == str(output_path)
    assert output_path.read_bytes() == b"fake wav"
    assert captured["url"] == "https://api.xiaomimimo.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == "mimo-v2.5-tts-voicedesign"
    # Voice design model must NOT send audio.voice (API 400 otherwise).
    assert captured["json"]["audio"] == {"format": "wav"}
    assert "voice" not in captured["json"]["audio"]
    assert captured["json"]["messages"] == [
        {"role": "user", "content": "Deep male narrator"},
        {"role": "assistant", "content": "大家好"},
    ]


@pytest.mark.asyncio
async def test_mimo_voice_design_requires_style_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("MIMO_API_KEY", "sk-test")
    service = TTSService({"mimo": {"api_key": "sk-test"}}, core=DummyCore())

    with pytest.raises(ValueError, match="voice design"):
        await service(
            text="大家好",
            inference_mode="mimo",
            output_path=str(tmp_path / "audio.wav"),
            mimo_model="mimo-v2.5-tts-voicedesign",
            mimo_style="",
        )


@pytest.mark.asyncio
async def test_mimo_standard_model_still_sends_voice(tmp_path, monkeypatch):
    captured = {}

    async def fake_post(self, url, *, json=None, headers=None):
        captured["json"] = json
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "audio": {"data": base64.b64encode(b"fake wav").decode("utf-8")}
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    service = TTSService(
        {"mimo": {"api_key": "sk-test", "model": "mimo-v2.5-tts", "voice_id": "冰糖"}},
        core=DummyCore(),
    )
    await service(
        text="大家好",
        inference_mode="mimo",
        output_path=str(tmp_path / "audio.wav"),
        voice="冰糖",
        mimo_model="mimo-v2.5-tts",
    )
    assert captured["json"]["audio"]["voice"] == "冰糖"


@pytest.mark.asyncio
async def test_mimo_tts_uses_environment_api_key_and_config_voice(tmp_path, monkeypatch):
    async def fake_post(self, url, *, json=None, headers=None):
        assert headers["Authorization"] == "Bearer env-key"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "audio": {"data": base64.b64encode(b"ok").decode("utf-8")}
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setenv("MIMO_API_KEY", "env-key")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    service = TTSService(
        {"mimo": {"api_key": "", "voice_id": "冰糖"}},
        core=DummyCore(),
    )

    result = await service(
        text="hello",
        inference_mode="mimo",
        output_path=str(tmp_path / "audio.wav"),
    )

    assert Path(result).exists()


@pytest.mark.asyncio
async def test_mimo_tts_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    service = TTSService({"mimo": {"api_key": ""}}, core=DummyCore())

    with pytest.raises(ValueError, match="Mimo API key is not configured"):
        await service(
            text="hello",
            inference_mode="mimo",
            output_path=str(tmp_path / "audio.wav"),
        )


@pytest.mark.asyncio
async def test_mimo_tts_rejects_missing_audio(tmp_path, monkeypatch):
    async def fake_post(self, url, *, json=None, headers=None):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "nothing to see here"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    service = TTSService({"mimo": {"api_key": "sk-test"}}, core=DummyCore())

    with pytest.raises(Exception, match="Mimo TTS response did not include audio data"):
        await service(
            text="hello",
            inference_mode="mimo",
            output_path=str(tmp_path / "audio.wav"),
        )


@pytest.mark.asyncio
async def test_mimo_tts_reports_http_error(tmp_path, monkeypatch):
    async def fake_post(self, url, *, json=None, headers=None):
        return httpx.Response(
            401,
            text="unauthorized",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    service = TTSService({"mimo": {"api_key": "bad-key"}}, core=DummyCore())

    with pytest.raises(Exception, match="Mimo TTS HTTP error: 401"):
        await service(
            text="hello",
            inference_mode="mimo",
            output_path=str(tmp_path / "audio.wav"),
        )


def test_config_manager_accepts_mimo_api_key(tmp_path):
    config_path = tmp_path / "config.yaml"
    original_instance = ConfigManager._instance
    ConfigManager._instance = None
    try:
        manager = ConfigManager(str(config_path))
        manager.set_comfyui_config(mimo_api_key="mimo-key")
        assert manager.get_comfyui_config()["tts"]["mimo"]["api_key"] == "mimo-key"
    finally:
        ConfigManager._instance = original_instance
