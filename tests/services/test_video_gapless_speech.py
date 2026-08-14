"""Tests for continuous A/V hold-aligned export path (preview parity)."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

import pytest

from pixelle_video.services.video import VideoService
from pixelle_video.services.workbench_jobs import WorkbenchJobService


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _make_tone_wav(path: Path, duration: float, freq: float = 440.0) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency={freq}:duration={duration}",
        "-c:a",
        "pcm_s16le",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _make_color_video_with_padded_audio(
    path: Path,
    color: str,
    speech_wav: Path,
    total_duration: float,
) -> None:
    """Segment like production: picture held for total_duration, speech apad'd with silence."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=320x240:d={total_duration}",
        "-i",
        str(speech_wav),
        "-filter_complex",
        f"[1:a]apad=whole_dur={total_duration}[a]",
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-t",
        str(total_duration),
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _probe_duration(path: Path) -> float:
    import ffmpeg

    probe = ffmpeg.probe(str(path))
    return float(probe["format"]["duration"])


def _probe_has_audio(path: Path) -> bool:
    import ffmpeg

    probe = ffmpeg.probe(str(path))
    return any(s.get("codec_type") == "audio" for s in probe.get("streams", []))


def _extract_mono_wav(video: Path, wav: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "8000",
            str(wav),
        ],
        check=True,
        capture_output=True,
    )


def _rms_at(samples: tuple[int, ...], framerate: int, t: float, win: float = 0.05) -> float:
    start = int(t * framerate)
    end = int((t + win) * framerate)
    chunk = samples[start:end]
    if not chunk:
        return 0.0
    return math.sqrt(sum(x * x for x in chunk) / len(chunk))


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not installed")
def test_concat_videos_gapless_speech_keeps_holds_with_mid_silence(tmp_path: Path):
    """
    Two scenes: speech 1.0s + hold 0.5s each.
    Export must match preview: silence during each hold window (≈1.0–1.5s),
    not only trailing silence at the end.
    """
    speech1 = tmp_path / "s1.wav"
    speech2 = tmp_path / "s2.wav"
    _make_tone_wav(speech1, 1.0, 440.0)
    _make_tone_wav(speech2, 1.0, 660.0)

    seg1 = tmp_path / "seg1.mp4"
    seg2 = tmp_path / "seg2.mp4"
    _make_color_video_with_padded_audio(seg1, "red", speech1, total_duration=1.5)
    _make_color_video_with_padded_audio(seg2, "blue", speech2, total_duration=1.5)

    out = tmp_path / "aligned.mp4"
    service = VideoService()
    result = service.concat_videos_gapless_speech(
        video_segments=[str(seg1), str(seg2)],
        speech_audios=[str(speech1), str(speech2)],
        output=str(out),
    )

    assert Path(result).is_file()
    assert out.is_file()
    assert _probe_has_audio(out)

    video_duration = _probe_duration(out)
    # Visual timeline keeps both holds: ~3.0s
    assert 2.85 <= video_duration <= 3.25

    wav = tmp_path / "out.wav"
    _extract_mono_wav(out, wav)
    with wave.open(str(wav), "rb") as handle:
        framerate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())
        samples = struct.unpack("<" + "h" * (len(raw) // 2), raw)

    # Narration playing early; hold silence around t=1.25; next speech after 1.5s
    assert _rms_at(samples, framerate, 0.2) > 300
    assert _rms_at(samples, framerate, 1.25) < 300
    assert _rms_at(samples, framerate, 1.7) > 300


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not installed")
def test_concat_videos_gapless_speech_single_segment(tmp_path: Path):
    speech = tmp_path / "s.wav"
    _make_tone_wav(speech, 0.8, 500.0)
    seg = tmp_path / "seg.mp4"
    _make_color_video_with_padded_audio(seg, "green", speech, total_duration=1.2)

    out = tmp_path / "single.mp4"
    result = VideoService().concat_videos_gapless_speech(
        video_segments=[str(seg)],
        speech_audios=[str(speech)],
        output=str(out),
    )
    assert Path(result).is_file()
    duration = _probe_duration(out)
    assert 1.05 <= duration <= 1.4


def test_export_pipeline_params_default_continuous_av_hold_split():
    params = WorkbenchJobService._export_pipeline_params(
        project_id="p1",
        task_id="t1",
        snapshot={"config": {}, "scenes": [{"sceneId": "s1", "narration": "hi"}]},
        existing_assets={},
    )
    assert params["continuous_av_hold_split"] is True
    assert params["tts_delivery"] == "continuous"


def test_export_pipeline_params_per_scene_disables_gapless():
    params = WorkbenchJobService._export_pipeline_params(
        project_id="p1",
        task_id="t1",
        snapshot={
            "config": {"ttsDelivery": "per_scene"},
            "scenes": [{"sceneId": "s1", "narration": "hi"}],
        },
        existing_assets={},
    )
    assert params["continuous_av_hold_split"] is False
    assert params["tts_delivery"] == "per_scene"


@pytest.mark.asyncio
async def test_export_job_passes_continuous_av_hold_split(tmp_path: Path):
    from pixelle_video.models.workbench import ExportRevision

    root = tmp_path / "projects" / "p1"
    image = root / "assets" / "old.png"
    audio = root / "assets" / "audio.mp3"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    audio.write_bytes(b"audio")

    class FakeCore:
        config = {}

        def __init__(self):
            self.kwargs = None
            self.output_path = tmp_path / "pipeline-output" / "final.mp4"

        async def generate_video(self, **kwargs):
            self.kwargs = kwargs
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.output_path.write_bytes(b"fake-mp4")
            return {"video_path": str(self.output_path)}

    class Store:
        def __init__(self, root_path):
            self.root = Path(root_path)

        def resolve(self, project_id, relative):
            return self.root / project_id / relative

    class Repo:
        def __init__(self, revision):
            self.revision = revision
            self.updated = []

        def get_export_revision(self, export_id):
            return self.revision

        def update_export_revision(self, export_id, **changes):
            self.updated.append(changes)

    revision = ExportRevision(
        "p1",
        {
            "config": {},
            "scenes": [
                {
                    "sceneId": "s1",
                    "imagePath": "assets/old.png",
                    "audioPath": "assets/audio.mp3",
                    "durationSeconds": 3.5,
                    "manualHoldSeconds": 1.5,
                }
            ],
        },
        export_id="e1",
    )
    core = FakeCore()
    await WorkbenchJobService(core, Repo(revision), Store(tmp_path / "projects")).run_export_job(
        "p1", "e1", "t1"
    )
    assert core.kwargs["continuous_av_hold_split"] is True
    assert core.kwargs["existing_scene_assets"]["s1"]["manual_hold_seconds"] == 1.5
    assert core.kwargs["existing_scene_assets"]["s1"]["duration_seconds"] == 2.0
