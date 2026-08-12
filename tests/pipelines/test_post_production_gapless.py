"""Day2: continuous gapless fail-hard + post_production off event loop contract."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pixelle_video.pipelines.standard import StandardPipeline


def _core_stub():
    core = MagicMock()
    core.llm = MagicMock()
    core.tts = MagicMock()
    core.media = MagicMock()
    core.video = MagicMock()
    return core


@pytest.mark.asyncio
async def test_post_production_gapless_fails_when_speech_missing(tmp_path):
    pipeline = StandardPipeline(_core_stub())
    frames = [
        SimpleNamespace(
            video_segment_path=str(tmp_path / "s0.mp4"),
            audio_path=str(tmp_path / "a0.mp3"),
        ),
        SimpleNamespace(
            video_segment_path=str(tmp_path / "s1.mp4"),
            audio_path=None,  # missing
        ),
    ]
    # Create only first audio so second is missing.
    Path(frames[0].audio_path).write_bytes(b"x")
    for frame in frames:
        Path(frame.video_segment_path).write_bytes(b"v")

    ctx = SimpleNamespace(
        storyboard=SimpleNamespace(frames=frames, final_video_path=None, completed_at=None),
        params={"continuous_av_hold_split": True},
        final_video_path=str(tmp_path / "out.mp4"),
        progress_callback=None,
    )

    with pytest.raises(ValueError, match="requires speech audio"):
        await pipeline.post_production(ctx)


@pytest.mark.asyncio
async def test_post_production_legacy_concat_when_not_gapless(tmp_path, monkeypatch):
    pipeline = StandardPipeline(_core_stub())
    seg = tmp_path / "s0.mp4"
    seg.write_bytes(b"v")
    frames = [
        SimpleNamespace(video_segment_path=str(seg), audio_path=None),
    ]
    called = {}

    class FakeVideoService:
        def concat_videos(self, **kwargs):
            called["concat"] = kwargs
            out = kwargs["output"]
            Path(out).write_bytes(b"mp4")
            return out

        def concat_videos_gapless_speech(self, **kwargs):
            raise AssertionError("gapless path must not run")

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.VideoService",
        FakeVideoService,
    )

    ctx = SimpleNamespace(
        storyboard=SimpleNamespace(frames=frames, final_video_path=None, completed_at=None),
        params={"continuous_av_hold_split": False},
        final_video_path=str(tmp_path / "out.mp4"),
        progress_callback=None,
    )
    await pipeline.post_production(ctx)
    assert "concat" in called
    assert ctx.storyboard.final_video_path == str(tmp_path / "out.mp4")
