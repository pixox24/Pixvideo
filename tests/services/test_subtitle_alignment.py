from pathlib import Path

from pixelle_video.services.subtitle_alignment import (
    AlignmentCue,
    load_alignment,
    map_segments_to_alignment,
    parse_alignment_payload,
    save_alignment,
)
from pixelle_video.services.subtitle_renderer import SubtitleRenderer


def test_parse_minimax_style_subtitle_payload():
    cues = parse_alignment_payload(
        [
            {"text": "第一句旁白。", "time_begin": 0, "time_end": 1200},
            {"text": "第二句旁白。", "time_begin": 1200, "time_end": 3600},
        ]
    )
    assert len(cues) == 2
    assert cues[0].start_ms == 0
    assert cues[1].end_ms == 3600


def test_map_segments_to_alignment_uses_tts_times():
    segments = ["第一句旁白", "第二句旁白"]
    cues = [
        AlignmentCue("第一句旁白。", 0, 1000),
        AlignmentCue("第二句旁白。", 1000, 4000),
    ]
    times = map_segments_to_alignment(segments, cues, duration=4.0)
    assert times is not None
    assert times[0][0] == 0.0
    assert times[0][1] <= times[1][0] + 0.05
    assert times[1][1] == 4.0
    # First sentence should get less time than the second.
    assert (times[0][1] - times[0][0]) < (times[1][1] - times[1][0])


def test_plan_segments_prefers_alignment_over_equal_split(tmp_path):
    renderer = SubtitleRenderer()
    alignment = [
        {"text": "短", "start_ms": 0, "end_ms": 400},
        {"text": "这是一句明显更长的旁白内容", "start_ms": 400, "end_ms": 4000},
    ]
    timed = renderer.plan_segments(
        "短。这是一句明显更长的旁白内容。",
        duration=4.0,
        style={"segmentMode": "sentence", "maxCharsPerLine": 20, "maxLines": 2},
        alignment=alignment,
    )
    assert len(timed) == 2
    assert timed[0].end <= 0.6
    assert timed[1].start >= 0.3
    assert timed[-1].end == 4.0


def test_alignment_sidecar_roundtrip(tmp_path):
    audio = tmp_path / "voice.mp3"
    audio.write_bytes(b"fake")
    cues = [AlignmentCue("你好", 0, 500), AlignmentCue("世界", 500, 1200)]
    path = save_alignment(audio, cues)
    assert Path(path).is_file()
    loaded = load_alignment(audio)
    assert [cue.text for cue in loaded] == ["你好", "世界"]
    assert loaded[1].end_ms == 1200
