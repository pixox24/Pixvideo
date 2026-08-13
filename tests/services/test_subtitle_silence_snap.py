"""Silence-snap + short-cue fade caps for coarse MiniMax alignment."""

from __future__ import annotations

from pathlib import Path

import pytest

from pixelle_video.services.subtitle_renderer import SubtitleRenderer

POWER_TEXT = (
    "小时候最怕数学老师拖堂，如今自己成了那个在会议结束后，"
    "又微笑着补一句“再耽误大家两分钟”的人。"
    "原来权力的滋味，是这么让人上瘾又心虚。"
)

REAL_CLIP = Path(
    "data/workbench/projects/8c90c929012641158c63454b0cb6ee42/assets/scenes/"
    "54d38daff6904f6db48f142af951be7c/audio/"
    "a98ca3e7abb34cdea9599add3119077b-continuous.mp3"
)


def test_alignment_is_coarse_helper():
    from pixelle_video.services.subtitle_alignment import AlignmentCue

    segs = ["a", "b", "c", "d", "e"]
    assert SubtitleRenderer._alignment_is_coarse([], segs) is True
    assert SubtitleRenderer._alignment_is_coarse(
        [AlignmentCue(POWER_TEXT, 0, 12000)], segs
    ) is True
    fine = [
        AlignmentCue("a", 0, 1000),
        AlignmentCue("b", 1000, 2000),
        AlignmentCue("c", 2000, 3000),
        AlignmentCue("d", 3000, 4000),
        AlignmentCue("e", 4000, 5000),
    ]
    assert SubtitleRenderer._alignment_is_coarse(fine, segs) is False


def test_short_cue_fade_capped_to_30_percent():
    renderer = SubtitleRenderer()
    # 1.4s cue with style fad 400/400 would dominate without cap.
    style = {"animation": "fade", "fadeInMs": 400, "fadeOutMs": 400}
    tag = renderer._fade_tag(style, 1.4)
    assert tag.startswith(r"{\fad(")
    inner = tag[len(r"{\fad(") : -2]
    fade_in, fade_out = [int(x) for x in inner.split(",")]
    # 30% of 1400ms = 420; each side max 15% = 210
    assert fade_in <= 210
    assert fade_out <= 210
    assert fade_in + fade_out <= 420


@pytest.mark.skipif(not REAL_CLIP.is_file(), reason="local workbench fixture not present")
def test_silence_snap_moves_power_phrase_near_real_onset():
    """
    On the real MiniMax continuous cut for the 权力的滋味 scene, silence snap
    should end the previous cue near ~8.0–8.7s so 权力 starts close to real speech.
    """
    renderer = SubtitleRenderer()
    style = {
        "segmentMode": "sentence",
        "maxCharsPerLine": 30,
        "maxLines": 2,
        "mode": "ass",
        "animation": "fade",
        "fadeInMs": 400,
        "fadeOutMs": 400,
    }
    # Coarse whole-scene cue (as stored on continuous slice sidecars).
    alignment = [{"text": POWER_TEXT, "start_ms": 0, "end_ms": 12253}]
    timed = renderer.plan_segments(
        POWER_TEXT,
        12.253,
        style,
        alignment=alignment,
        audio_path=REAL_CLIP,
    )
    power = next(t for t in timed if "权力" in t.text)
    prev = next(t for t in timed if "两分钟" in t.text)
    # Real speech: 两分钟 ends ~8.0, 权力 starts ~8.69
    assert prev.end <= 8.95, f"prev still ends too late: {prev.end}"
    assert 8.2 <= power.start <= 9.2, f"权力 onset not snapped: {power.start}"
    # Previous cue should not still cover deep into 权力 speech.
    assert power.start - prev.end <= 0.35 or abs(power.start - prev.end) < 1e-6
