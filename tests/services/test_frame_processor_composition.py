import pytest

from pixelle_video.models.storyboard import Storyboard, StoryboardConfig, StoryboardFrame
from pixelle_video.services.frame_processor import FrameProcessor


class DummyCore:
    pass


def make_config(**overrides):
    values = {
        "task_id": "task-1",
        "media_width": 1080,
        "media_height": 1920,
        "composition_mode": "plain_image",
        "image_motion_enabled": True,
        "subtitle_enabled": True,
    }
    values.update(overrides)
    return StoryboardConfig(**values)


@pytest.mark.asyncio
async def test_plain_image_mode_skips_html_composition(monkeypatch):
    processor = FrameProcessor(DummyCore())
    frame = StoryboardFrame(
        index=0,
        narration="旁白",
        image_prompt="prompt",
        image_path="/tmp/image.png",
    )
    frame.media_type = "image"

    async def fail_compose(*args, **kwargs):
        raise AssertionError("HTML composition should be skipped in plain image mode")

    monkeypatch.setattr(processor, "_compose_frame_html", fail_compose)

    await processor._step_compose_frame(frame, None, make_config())

    assert frame.composed_image_path is None


@pytest.mark.asyncio
async def test_plain_image_segment_uses_original_image(monkeypatch, tmp_path):
    calls = {}
    processor = FrameProcessor(DummyCore())
    frame = StoryboardFrame(index=0, narration="旁白", image_prompt="prompt")
    frame.media_type = "image"
    frame.image_path = str(tmp_path / "source.png")
    frame.audio_path = str(tmp_path / "audio.mp3")

    class FakeVideoService:
        def create_video_from_image_with_motion(self, **kwargs):
            calls.update(kwargs)
            return kwargs["output"]

    monkeypatch.setattr("pixelle_video.services.video.VideoService", FakeVideoService)

    await processor._step_create_video_segment(
        frame,
        make_config(
            task_id="task-plain",
            subtitle_style={"mode": "ass", "fontSize": 48},
        ),
    )

    assert calls["image"] == frame.image_path
    assert calls["audio"] == frame.audio_path
    assert calls["width"] == 1080
    assert calls["height"] == 1920
    assert calls["subtitle_text"] == "旁白"
    assert calls["subtitle_style"]["mode"] == "ass"
    assert calls["subtitle_style"]["fontSize"] == 48
    assert calls["motion_enabled"] is True
    assert calls["subtitle_enabled"] is True
    assert frame.video_segment_path == calls["output"]


@pytest.mark.asyncio
async def test_plain_image_mode_rejects_video_media():
    processor = FrameProcessor(DummyCore())
    frame = StoryboardFrame(index=0, narration="旁白", image_prompt="prompt")
    frame.media_type = "video"
    frame.video_path = "/tmp/video.mp4"
    frame.audio_path = "/tmp/audio.mp3"

    with pytest.raises(ValueError, match="Pure image mode only supports image media"):
        await processor._step_create_video_segment(frame, make_config())


@pytest.mark.asyncio
async def test_rerender_frame_reuses_existing_audio_and_image(monkeypatch, tmp_path):
    processor = FrameProcessor(DummyCore())
    audio = tmp_path / "source.mp3"
    image = tmp_path / "source.png"
    audio.write_bytes(b"audio")
    image.write_bytes(b"image")
    frame = StoryboardFrame(
        index=0,
        narration="旁白",
        image_prompt="prompt",
        audio_path=str(audio),
        image_path=str(image),
        media_type="image",
        duration=1.0,
    )
    storyboard = Storyboard(title="Title", config=make_config(), frames=[frame])

    async def fail_generation(*_args, **_kwargs):
        raise AssertionError("rerender must not regenerate source assets")

    async def no_op_compose(*_args, **_kwargs):
        return None

    async def create_segment(current_frame, _config):
        current_frame.video_segment_path = str(tmp_path / "rerendered.mp4")

    monkeypatch.setattr(processor, "_step_generate_audio", fail_generation)
    monkeypatch.setattr(processor, "_step_generate_media", fail_generation)
    monkeypatch.setattr(processor, "_step_compose_frame", no_op_compose)
    monkeypatch.setattr(processor, "_step_create_video_segment", create_segment)

    result = await processor(frame, storyboard, make_config(), total_frames=1)

    assert result.audio_path == str(audio)
    assert result.image_path == str(image)
    assert result.video_segment_path == str(tmp_path / "rerendered.mp4")
