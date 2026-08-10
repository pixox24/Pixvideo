"""Unit tests for continuous multi-scene TTS assemble/split helpers."""

from pathlib import Path

from pixelle_video.services.continuous_tts import (
    ContinuousSceneSegment,
    assemble_continuous_script,
    extract_audio_segment,
    normalize_tts_delivery,
    plan_scene_slices,
    proportional_slices,
    should_use_continuous_tts,
)
from pixelle_video.services.subtitle_alignment import AlignmentCue, save_alignment


def test_normalize_tts_delivery_defaults_continuous():
    assert normalize_tts_delivery(None) == "continuous"
    assert normalize_tts_delivery("continuous") == "continuous"
    assert normalize_tts_delivery("per_scene") == "per_scene"
    assert normalize_tts_delivery("per-scene") == "per_scene"
    assert normalize_tts_delivery("legacy") == "per_scene"


def test_should_use_continuous_requires_multi_pending():
    assert should_use_continuous_tts(
        delivery="continuous",
        scene_count=3,
        pending_tts_count=2,
    )
    assert not should_use_continuous_tts(
        delivery="continuous",
        scene_count=3,
        pending_tts_count=1,
    )
    assert not should_use_continuous_tts(
        delivery="per_scene",
        scene_count=3,
        pending_tts_count=3,
    )


def test_assemble_joins_with_terminal_punct():
    segments = [
        ContinuousSceneSegment("s0", "i0", 0, "第一镜旁白", "fp0"),
        ContinuousSceneSegment("s1", "i1", 1, "第二镜旁白！", "fp1"),
    ]
    assembled = assemble_continuous_script(segments)
    assert "第一镜旁白。" in assembled.full_text
    assert "第二镜旁白！" in assembled.full_text
    assert assembled.scene_texts == ("第一镜旁白", "第二镜旁白！")


def test_proportional_slices_cover_full_duration():
    slices = proportional_slices(["a", "b"], ["甲乙丙", "丁"], 4.0)
    assert len(slices) == 2
    assert slices[0].start == 0.0
    assert abs(slices[-1].end - 4.0) < 1e-6
    assert slices[0].end <= slices[1].start + 1e-6
    assert slices[0].method == "proportional"


def test_plan_scene_slices_prefers_alignment(tmp_path):
    audio = tmp_path / "full.mp3"
    audio.write_bytes(b"fake-audio-bytes-for-test")
    save_alignment(
        audio,
        [
            AlignmentCue("第一镜旁白", 0, 1000),
            AlignmentCue("第二镜旁白", 1000, 2500),
        ],
    )
    slices = plan_scene_slices(
        ["s0", "s1"],
        ["第一镜旁白", "第二镜旁白"],
        continuous_audio_path=audio,
        total_duration=2.5,
    )
    assert len(slices) == 2
    assert slices[0].method == "alignment"
    assert slices[0].start == 0.0
    assert slices[-1].end == 2.5


def test_extract_audio_segment_fallback_without_media(tmp_path):
    source = tmp_path / "src.mp3"
    source.write_bytes(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    dest = tmp_path / "cut.mp3"
    extract_audio_segment(source, dest, 0.0, 0.5)
    assert dest.is_file()
    assert dest.stat().st_size > 0


def test_extract_audio_segments_batch_fallback_without_media(tmp_path):
    from pixelle_video.services.continuous_tts import extract_audio_segments

    source = tmp_path / "src.mp3"
    source.write_bytes(b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" * 4)
    dests = [tmp_path / f"s{i}.mp3" for i in range(3)]
    extract_audio_segments(
        source,
        [(dests[0], 0.0, 0.3), (dests[1], 0.3, 0.6), (dests[2], 0.6, 1.0)],
        batch_size=2,
    )
    assert all(path.is_file() and path.stat().st_size > 0 for path in dests)
