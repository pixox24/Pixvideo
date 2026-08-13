from pathlib import Path

from pixelle_video.services.subtitle_alignment import (
    AlignmentCue,
    load_alignment,
    map_segments_to_alignment,
    parse_alignment_payload,
    save_alignment,
    slice_alignment_cues,
    write_sliced_alignment_sidecar,
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


def test_slice_alignment_cues_rezeros_to_local_window():
    cues = [
        AlignmentCue("甲", 0, 1000),
        AlignmentCue("乙", 1000, 2500),
        AlignmentCue("丙", 2500, 4000),
    ]
    # Second scene window [1.0s, 2.5s)
    sliced = slice_alignment_cues(cues, 1.0, 2.5)
    assert len(sliced) == 1
    assert sliced[0].text == "乙"
    assert sliced[0].start_ms == 0
    assert sliced[0].end_ms == 1500


def test_slice_alignment_clips_partial_overlap_at_boundaries():
    cues = [
        AlignmentCue("跨界", 800, 1500),
        AlignmentCue("镜内", 1500, 2200),
    ]
    sliced = slice_alignment_cues(cues, 1.0, 2.0)
    assert len(sliced) == 2
    assert sliced[0].start_ms == 0  # 800→1000 clipped
    assert sliced[0].end_ms == 500  # 1500-1000
    assert sliced[1].start_ms == 500
    assert sliced[1].end_ms == 1000  # window is 1.0s


def test_write_sliced_alignment_sidecar(tmp_path):
    continuous = tmp_path / "continuous.mp3"
    scene = tmp_path / "scene.mp3"
    continuous.write_bytes(b"c")
    scene.write_bytes(b"s")
    save_alignment(
        continuous,
        [
            AlignmentCue("一", 0, 1000),
            AlignmentCue("二", 1000, 3000),
            AlignmentCue("三", 3000, 4500),
        ],
    )
    written = write_sliced_alignment_sidecar(continuous, scene, 1.0, 3.0)
    assert written is not None
    loaded = load_alignment(scene)
    assert [c.text for c in loaded] == ["二"]
    assert loaded[0].start_ms == 0
    assert loaded[0].end_ms == 2000
