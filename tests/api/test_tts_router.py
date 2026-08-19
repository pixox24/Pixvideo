import pytest

from api.routers.tts import tts_synthesize
from api.schemas.tts import TTSSynthesizeRequest


class DummyTTS:
    def __init__(self):
        self.params = None

    async def __call__(self, **params):
        self.params = params
        return "output/preview.mp3"


class DummyPixelleVideo:
    def __init__(self):
        self.tts = DummyTTS()


@pytest.mark.asyncio
async def test_tts_synthesize_passes_local_voice_and_speed(monkeypatch):
    monkeypatch.setattr("api.routers.tts.get_audio_duration", lambda path: 1.25)
    pixelle_video = DummyPixelleVideo()

    response = await tts_synthesize(
        TTSSynthesizeRequest(
            text="这是一段试听文案",
            inference_mode="local",
            voice_id="zh-CN-XiaoxiaoNeural",
            speed=1.1,
        ),
        pixelle_video=pixelle_video,
    )

    assert pixelle_video.tts.params == {
        "text": "这是一段试听文案",
        "inference_mode": "local",
        "voice": "zh-CN-XiaoxiaoNeural",
        "speed": 1.1,
    }
    assert response.audio_path == "output/preview.mp3"
    assert response.duration == 1.25


@pytest.mark.asyncio
async def test_tts_synthesize_passes_minimax_model_voice_speed_and_emotion(monkeypatch):
    monkeypatch.setattr("api.routers.tts.get_audio_duration", lambda path: 2.0)
    pixelle_video = DummyPixelleVideo()

    response = await tts_synthesize(
        TTSSynthesizeRequest(
            text="这是一段 MiniMax 试听文案",
            inference_mode="minimax",
            voice_id="male-qn-qingse",
            speed=1.0,
            minimax_model="speech-2.8-turbo",
            minimax_emotion="happy",
        ),
        pixelle_video=pixelle_video,
    )

    assert pixelle_video.tts.params == {
        "text": "这是一段 MiniMax 试听文案",
        "inference_mode": "minimax",
        "voice": "male-qn-qingse",
        "speed": 1.0,
        "minimax_model": "speech-2.8-turbo",
        "minimax_emotion": "happy",
    }
    assert response.audio_path == "output/preview.mp3"
    assert response.duration == 2.0


@pytest.mark.asyncio
async def test_tts_synthesize_passes_mimo_model_voice_speed_and_style(monkeypatch):
    monkeypatch.setattr("api.routers.tts.get_audio_duration", lambda path: 1.5)
    pixelle_video = DummyPixelleVideo()

    response = await tts_synthesize(
        TTSSynthesizeRequest(
            text="这是一段 MiMo 试听文案",
            inference_mode="mimo",
            voice_id="Chloe",
            speed=1.0,
            mimo_model="mimo-v2.5-tts",
            mimo_style="Bright and cheerful",
        ),
        pixelle_video=pixelle_video,
    )

    assert pixelle_video.tts.params == {
        "text": "这是一段 MiMo 试听文案",
        "inference_mode": "mimo",
        "voice": "Chloe",
        "speed": 1.0,
        "mimo_model": "mimo-v2.5-tts",
        "mimo_style": "Bright and cheerful",
    }
    assert response.audio_path == "output/preview.mp3"
    assert response.duration == 1.5


@pytest.mark.asyncio
async def test_tts_synthesize_passes_qwen_model_mode_and_instruction(monkeypatch):
    monkeypatch.setattr("api.routers.tts.get_audio_duration", lambda path: 1.5)
    pixelle_video = DummyPixelleVideo()

    await tts_synthesize(
        TTSSynthesizeRequest(
            text="这是一段 Qwen 试听文案",
            inference_mode="qwen_audio",
            voice_id="Cherry",
            qwen_audio_model="qwen3-tts-instruct-flash",
            qwen_audio_mode="instruct",
            qwen_audio_instruction="温柔地说，语速稍慢",
        ),
        pixelle_video=pixelle_video,
    )

    assert pixelle_video.tts.params == {
        "text": "这是一段 Qwen 试听文案",
        "inference_mode": "qwen_audio",
        "voice": "Cherry",
        "qwen_audio_model": "qwen3-tts-instruct-flash",
        "qwen_audio_mode": "instruct",
        "qwen_audio_instruction": "温柔地说，语速稍慢",
    }
