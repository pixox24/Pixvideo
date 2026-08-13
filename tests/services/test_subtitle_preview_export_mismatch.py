"""Workbench preview vs export subtitle timing (hold must not stretch cues)."""

from __future__ import annotations

from pixelle_video.services.subtitle_renderer import SubtitleRenderer


def test_legacy_bug_stretching_all_cues_when_hold_folded_into_duration():
    """Document the OLD bug: scheduling on speech+hold stretches every cue."""
    renderer = SubtitleRenderer()
    text = "受够了996和一眼望到头的生活。其实普通人不用卷，也能换个活法。"
    style = {"segmentMode": "sentence", "maxCharsPerLine": 14, "maxLines": 2}
    speech_seconds = 10.0
    hold_seconds = 3.0

    preview_like = renderer.plan_segments(text, speech_seconds, style, alignment=None)
    buggy_export = renderer.plan_segments(
        text, speech_seconds + hold_seconds, style, alignment=None
    )

    assert len(preview_like) == len(buggy_export) >= 2
    p_mid = (preview_like[-1].start + preview_like[-1].end) / 2
    e_mid = (buggy_export[-1].start + buggy_export[-1].end) / 2
    assert e_mid - p_mid > 1.0


def test_hold_seconds_only_extends_last_cue_not_earlier_ones():
    """Fixed export path: speech-only plan + hold_seconds freezes last line."""
    renderer = SubtitleRenderer()
    text = "受够了996和一眼望到头的生活。其实普通人不用卷，也能换个活法。"
    style = {"segmentMode": "sentence", "maxCharsPerLine": 14, "maxLines": 2}
    speech_seconds = 10.0
    hold_seconds = 3.0

    preview_like = renderer.plan_segments(text, speech_seconds, style, alignment=None)
    export_like = renderer.plan_segments(
        text,
        speech_seconds,
        style,
        alignment=None,
        hold_seconds=hold_seconds,
    )

    assert len(preview_like) == len(export_like) >= 2
    # Earlier cues stay speech-locked (match preview).
    for a, b in zip(preview_like[:-1], export_like[:-1]):
        assert abs(a.start - b.start) < 1e-6
        assert abs(a.end - b.end) < 1e-6
    # Last cue starts at the same speech boundary, ends after hold.
    assert abs(export_like[-1].start - preview_like[-1].start) < 1e-6
    assert export_like[-1].end == speech_seconds + hold_seconds
    assert preview_like[-1].end == speech_seconds


def test_speech_only_duration_keeps_last_cue_within_audio():
    renderer = SubtitleRenderer()
    text = "第一句。第二句。第三句。"
    style = {"segmentMode": "sentence", "maxCharsPerLine": 20, "maxLines": 2}
    speech = 6.0
    segs = renderer.plan_segments(text, speech, style, alignment=None)
    assert segs[-1].end == speech
    assert all(seg.end <= speech + 1e-6 for seg in segs)
