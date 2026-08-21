import pytest

from pixelle_video.services.generation_core import compose_image_prompt, synthesize_speech


def test_compose_image_prompt_joins_prefix():
    assert compose_image_prompt("a cat", "ink sketch") == "ink sketch, a cat"
    assert compose_image_prompt("a cat", "") == "a cat"
    assert compose_image_prompt("", "ink sketch") == "ink sketch"


@pytest.mark.asyncio
async def test_synthesize_speech_falls_back_from_comfyui(tmp_path):
    output = tmp_path / "speech.mp3"
    calls = []

    class FakeCore:
        async def tts(self, **kwargs):
            calls.append(kwargs)
            if kwargs.get("inference_mode") == "comfyui":
                raise RuntimeError("comfy down")
            output.write_bytes(b"audio")
            return str(output)

    path = await synthesize_speech(
        FakeCore(),
        text="hello",
        output_path=str(output),
        scene_id="s1",
        inference_mode="comfyui",
    )
    assert path == str(output)
    assert output.read_bytes() == b"audio"
    assert calls[0]["inference_mode"] == "comfyui"
    assert calls[1]["inference_mode"] == "local"
