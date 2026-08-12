"""Guards against unbounded ffmpeg hangs freezing the workbench API."""

from __future__ import annotations

import sys

import pytest

from pixelle_video.services.video import (
    post_mux_timeout_seconds,
    run_ffmpeg_compiled,
    segment_encode_timeout_seconds,
)


def test_segment_encode_timeout_scales_and_caps():
    short = segment_encode_timeout_seconds(3.0, width=1080, height=1920)
    long = segment_encode_timeout_seconds(30.0, width=1440, height=2560)
    very_long = segment_encode_timeout_seconds(120.0, width=1080, height=1920)
    assert short >= 45.0
    assert long > short
    # Day2: hard cap raised so long hold + captions are not false-failed at 180s.
    assert long <= 900.0
    assert very_long > 180.0
    assert very_long <= 900.0


def test_post_mux_timeout_reencode_higher_than_copy():
    copy_t = post_mux_timeout_seconds(60.0, reencode=False, segment_count=6)
    re_t = post_mux_timeout_seconds(60.0, reencode=True, segment_count=6)
    assert re_t > copy_t
    assert copy_t <= 300.0
    assert re_t <= 900.0


def test_run_ffmpeg_compiled_times_out(tmp_path):
    # Sleep longer than timeout; must raise TimeoutError (not hang the suite).
    cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
    with pytest.raises(TimeoutError):
        run_ffmpeg_compiled(cmd, timeout=0.3, label="test-sleep")


def test_run_ffmpeg_compiled_nonzero_exit():
    cmd = [sys.executable, "-c", "import sys; sys.exit(7)"]
    with pytest.raises(RuntimeError, match="code=7"):
        run_ffmpeg_compiled(cmd, timeout=10, label="test-fail")


def test_run_ffmpeg_compiled_timeout_still_works_with_popen():
    cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
    with pytest.raises(TimeoutError):
        run_ffmpeg_compiled(cmd, timeout=0.2, label="popen-timeout")
