# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Video Processing Service

High-performance video composition service built on ffmpeg-python.

Features:
- Video concatenation
- Audio/video merging
- Background music addition
- Image to video conversion

Note: Requires FFmpeg to be installed on the system.
"""

import math
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import List, Literal, Optional

import ffmpeg
from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.services.hyperframes_caption_renderer import HyperframesCaptionRenderer
from pixelle_video.services.pillow_caption_renderer import (
    PillowCaptionRenderer,
    should_use_pillow_captions,
)
from pixelle_video.services.subtitle_renderer import SubtitleRenderer
from pixelle_video.utils.os_util import get_resource_path, list_resource_files, resource_exists


def check_ffmpeg() -> None:
    """
    Check if FFmpeg is installed on the system

    Raises:
        RuntimeError: If FFmpeg is not found
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "FFmpeg not found. Please install it:\n"
            "  macOS: brew install ffmpeg\n"
            "  Ubuntu/Debian: apt-get install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html"
        )


def decode_ffmpeg_output(data: bytes | str | None) -> str:
    """
    Decode FFmpeg stdout/stderr safely.

    On Chinese Windows, FFmpeg often emits GBK/CP936 console text. Using the
    default UTF-8 decode turns a real FFmpeg failure into a misleading
    UnicodeDecodeError and hides the original message.
    """
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    if not data:
        return ""
    for encoding in ("utf-8", "gbk", "cp936", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def segment_encode_timeout_seconds(duration: float | None, *, width: int = 0, height: int = 0) -> float:
    """
    Bound wall-clock time for one segment encode.

    Short clips should finish in seconds; high-res + caption overlays can take
    longer, but must never hang the workbench forever (historical failure mode:
    frozen ffmpeg, 0-byte output, FastAPI event loop blocked).
    """
    base = 45.0
    dur = max(0.0, float(duration or 0.0))
    # ~8s budget per second of media, with a floor for filter-graph startup.
    scaled = base + dur * 8.0
    pixels = max(0, int(width)) * max(0, int(height))
    if pixels >= 1440 * 2560:
        scaled *= 1.5
    elif pixels >= 1080 * 1920:
        scaled *= 1.25
    # Hard cap 15 min: long holds + motion + captions can legitimately exceed 3 min.
    return min(900.0, max(45.0, scaled))


def post_mux_timeout_seconds(
    duration: float | None = None,
    *,
    reencode: bool = False,
    segment_count: int = 1,
) -> float:
    """
    Bound wall-clock time for concat / gapless mux / BGM post-production steps.

    Stream-copy demuxer is usually fast; filter re-encode and gapless remux scale
    with timeline length. Never unbounded (export used to hang at ~90% forever).
    """
    dur = max(0.0, float(duration or 0.0))
    n = max(1, int(segment_count or 1))
    if reencode:
        # ~6s budget per second of output + per-segment overhead
        scaled = 90.0 + dur * 6.0 + n * 8.0
        return min(900.0, max(90.0, scaled))
    # stream copy / strip audio
    scaled = 45.0 + dur * 1.5 + n * 3.0
    return min(300.0, max(45.0, scaled))


# Track in-flight ffmpeg children so export cancel/retry can kill *our* processes
# without a global `taskkill /IM ffmpeg.exe` (which nukes unrelated jobs).
_active_ffmpeg_lock = threading.Lock()
_active_ffmpeg_procs: set[subprocess.Popen] = set()


def _kill_popen(proc: subprocess.Popen) -> bool:
    try:
        if proc.poll() is None:
            proc.kill()
            try:
                proc.communicate(timeout=5)
            except Exception:
                pass
            return True
    except Exception:
        return False
    return False


def kill_tracked_ffmpeg_processes() -> int:
    """Kill ffmpeg processes started by this API process (export cancel / retry)."""
    with _active_ffmpeg_lock:
        procs = list(_active_ffmpeg_procs)
    killed = 0
    for proc in procs:
        if _kill_popen(proc):
            killed += 1
        with _active_ffmpeg_lock:
            _active_ffmpeg_procs.discard(proc)
    return killed


def run_ffmpeg_compiled(
    cmd: list[str],
    *,
    timeout: float,
    label: str = "ffmpeg",
) -> None:
    """
    Run a compiled ffmpeg command with a hard timeout.

    Uses Popen + communicate(timeout=...) so that:
    1) hung encodes are killed
    2) capture pipes cannot deadlock forever on a stuck child
    3) live PIDs are tracked for cooperative export cancel
    """
    if timeout <= 0:
        timeout = 45.0
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    with _active_ffmpeg_lock:
        _active_ffmpeg_procs.add(proc)
    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_popen(proc)
            stderr_tail = ""
            try:
                if proc.stderr:
                    leftover = proc.stderr.read() if hasattr(proc.stderr, "read") else b""
                    stderr_tail = decode_ffmpeg_output(leftover)[-800:]
            except Exception:
                pass
            raise TimeoutError(
                f"{label} timed out after {timeout:.0f}s"
                + (f": {stderr_tail}" if stderr_tail else "")
            )
        if proc.returncode != 0:
            err = decode_ffmpeg_output(stderr)[-1200:]
            raise RuntimeError(
                f"{label} failed (code={proc.returncode}): {err or '(no stderr)'}"
            )
    finally:
        with _active_ffmpeg_lock:
            _active_ffmpeg_procs.discard(proc)


def run_ffmpeg_stream(
    stream,
    *,
    timeout: float,
    label: str = "ffmpeg",
) -> None:
    """Compile an ffmpeg-python stream and run it with timeout."""
    cmd = stream.overwrite_output().compile()
    run_ffmpeg_compiled(cmd, timeout=timeout, label=label)


class VideoService:
    """
    Video compositor for common video processing tasks

    Uses ffmpeg-python for high-performance video processing.
    All operations preserve video quality when possible (stream copy).

    Examples:
        >>> compositor = VideoCompositor()
        >>>
        >>> # Concatenate videos
        >>> compositor.concat_videos(
        ...     ["intro.mp4", "main.mp4", "outro.mp4"],
        ...     "final.mp4"
        ... )
        >>>
        >>> # Add voiceover
        >>> compositor.merge_audio_video(
        ...     "visual.mp4",
        ...     "voiceover.mp3",
        ...     "final.mp4"
        ... )
        >>>
        >>> # Add background music
        >>> compositor.add_bgm(
        ...     "video.mp4",
        ...     "music.mp3",
        ...     "final.mp4",
        ...     bgm_volume=0.3
        ... )
        >>>
        >>> # Create video from image + audio
        >>> compositor.create_video_from_image(
        ...     "frame.png",
        ...     "narration.mp3",
        ...     "segment.mp4"
        ... )
    """

    _ffmpeg_filters: Optional[set[str]] = None

    def __init__(self):
        self._ffmpeg_checked = False

    def _ensure_ffmpeg(self):
        """Lazily check FFmpeg availability on first use, not at import time"""
        if not self._ffmpeg_checked:
            check_ffmpeg()
            self._ffmpeg_checked = True

    def concat_videos_gapless_speech(
        self,
        video_segments: List[str],
        speech_audios: List[str],
        output: str,
        bgm_path: Optional[str] = None,
        bgm_volume: float = 0.2,
        bgm_mode: Literal["once", "loop"] = "loop",
        bookend: Optional[dict] = None,
    ) -> str:
        """
        Concatenate video segments with gapless speech mux (音画分离).

        Visual tracks keep per-scene freeze holds (segments are already longer
        than pure speech when manual hold is set). Speech is taken from the
        original narration clips and concatenated without inter-scene silence,
        then muxed under the full picture timeline.

        Effect:
            - Hold freezes the picture only
            - Narration does not insert mid-sentence silence between scenes
            - When holds exist, speech may continue over the freeze of the
              previous scene (intentional A/V split for continuous delivery)

        Args:
            video_segments: Ordered video segment paths (with embedded holds)
            speech_audios: Ordered pure speech audio paths (no hold silence)
            output: Final output video path
            bgm_path: Optional background music path/preset
            bgm_volume: BGM volume (0.0-1.0)
            bgm_mode: "once" or "loop"

        Returns:
            Path to the output video
        """
        self._ensure_ffmpeg()

        if not video_segments:
            raise ValueError("video_segments list cannot be empty")
        if len(video_segments) != len(speech_audios):
            raise ValueError(
                f"video_segments ({len(video_segments)}) and speech_audios "
                f"({len(speech_audios)}) length mismatch"
            )
        for path in video_segments:
            if not path or not Path(path).is_file():
                raise FileNotFoundError(f"Video segment not found: {path}")
        for path in speech_audios:
            if not path or not Path(path).is_file():
                raise FileNotFoundError(f"Speech audio not found: {path}")

        logger.info(
            "Gapless speech mux (音画分离): {} segments, bgm={}",
            len(video_segments),
            bool(bgm_path),
        )

        temp_paths: List[str] = []
        try:
            # 1) Strip padded segment audio (holds pad silence into speech tracks)
            silent_segments: List[str] = []
            for index, segment in enumerate(video_segments):
                silent_path = self._get_unique_temp_path(
                    "silent_seg",
                    f"{index:02d}_{Path(segment).name}",
                )
                self._strip_audio_copy(segment, silent_path)
                silent_segments.append(silent_path)
                temp_paths.append(silent_path)

            # 2) Concatenate picture-only timeline (holds preserved)
            video_only = self._get_unique_temp_path("gapless_video", Path(output).name)
            temp_paths.append(video_only)
            if len(silent_segments) == 1:
                shutil.copy(silent_segments[0], video_only)
            else:
                try:
                    self._concat_demuxer(silent_segments, video_only)
                except Exception as demuxer_exc:
                    logger.warning(
                        "Video-only demuxer concat failed, falling back to filter: {}",
                        demuxer_exc,
                    )
                    self._concat_video_only_filter(silent_segments, video_only)

            # 3) Concatenate pure speech without inter-scene silence
            speech_path = self._get_unique_temp_path("gapless_speech", "speech.m4a")
            temp_paths.append(speech_path)
            self._concat_audio_files(speech_audios, speech_path)

            # 4) Mux gapless speech under full visual timeline
            muxed = self._get_unique_temp_path("gapless_mux", Path(output).name)
            temp_paths.append(muxed)

            self._mux_gapless_speech_onto_video(
                video=video_only,
                speech=speech_path,
                output=muxed,
            )

            # 5) Project-level intro/outro packaging (before BGM so music covers pads)
            packed = muxed
            bookend = bookend or {}
            if bookend.get("enabled") or (
                float(bookend.get("intro_seconds") or 0) > 0
                or float(bookend.get("outro_seconds") or 0) > 0
            ):
                packed = self._get_unique_temp_path("bookend", Path(output).name)
                temp_paths.append(packed)
                self.apply_bookend_packaging(
                    video=muxed,
                    output=packed,
                    intro_seconds=float(bookend.get("intro_seconds") or 0),
                    outro_seconds=float(bookend.get("outro_seconds") or 0),
                    intro_fade_seconds=float(bookend.get("intro_fade_seconds") or 0),
                    outro_fade_seconds=float(bookend.get("outro_fade_seconds") or 0),
                )

            # 6) Optional BGM mix with matching edge fades
            if bgm_path:
                return self._add_bgm_to_video(
                    video=packed,
                    bgm_path=bgm_path,
                    output=output,
                    volume=bgm_volume,
                    mode=bgm_mode,
                    fade_in=float(bookend.get("intro_fade_seconds") or 0),
                    fade_out=float(bookend.get("outro_fade_seconds") or 0),
                )

            if os.path.abspath(packed) != os.path.abspath(output):
                shutil.copy(packed, output)
            logger.success(f"Gapless speech video created: {output}")
            return output
        finally:
            for path in temp_paths:
                try:
                    if path and os.path.exists(path) and os.path.abspath(path) != os.path.abspath(output):
                        os.unlink(path)
                except OSError:
                    pass

    def _strip_audio_copy(self, video: str, output: str) -> str:
        """Copy video stream only (drop audio, keep holds/visual length)."""
        self._ensure_ffmpeg()
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        timeout = post_mux_timeout_seconds(reencode=False)
        # Prefer CLI: ffmpeg-python maps -an / -map awkwardly on some builds.
        cmd = [
            "ffmpeg", "-y",
            "-i", video,
            "-map", "0:v:0",
            "-c:v", "copy",
            "-an",
            output,
        ]
        try:
            run_ffmpeg_compiled(cmd, timeout=timeout, label="strip-audio")
            return output
        except Exception as primary_exc:
            logger.debug("strip_audio primary failed, trying ffmpeg-python: {}", primary_exc)
            try:
                stream = (
                    ffmpeg
                    .input(video)
                    .output(output, vcodec="copy", an=None, map="0:v:0")
                )
                run_ffmpeg_stream(stream, timeout=timeout, label="strip-audio-py")
                return output
            except Exception as secondary_exc:
                raise RuntimeError(
                    f"Failed to strip audio from video: {primary_exc}; {secondary_exc}"
                ) from secondary_exc

    def _concat_video_only_filter(self, videos: List[str], output: str) -> str:
        """Concatenate video streams only (no audio) via filter concat."""
        self._ensure_ffmpeg()
        n = len(videos)
        if n == 0:
            raise ValueError("videos list cannot be empty")
        if n == 1:
            shutil.copy(videos[0], output)
            return output

        stream_spec = "".join([f"[{i}:v]" for i in range(n)])
        filter_complex = f"{stream_spec}concat=n={n}:v=1:a=0[v]"
        cmd = ["ffmpeg"]
        for video in videos:
            cmd.extend(["-i", video])
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-an",
            "-y",
            output,
        ])
        timeout = post_mux_timeout_seconds(reencode=True, segment_count=n)
        try:
            run_ffmpeg_compiled(cmd, timeout=timeout, label="concat-video-only")
        except Exception as exc:
            raise RuntimeError(f"Failed to concatenate video-only segments: {exc}") from exc
        return output

    def _concat_audio_files(self, audios: List[str], output: str) -> str:
        """Concatenate pure speech clips gaplessly into one audio file."""
        self._ensure_ffmpeg()
        if not audios:
            raise ValueError("audios list cannot be empty")
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        n = len(audios)
        timeout = post_mux_timeout_seconds(reencode=True, segment_count=n)

        if n == 1:
            cmd = [
                "ffmpeg", "-y", "-i", audios[0],
                "-vn", "-c:a", "aac", "-b:a", "192k", output,
            ]
            try:
                run_ffmpeg_compiled(cmd, timeout=timeout, label="encode-speech")
            except Exception as exc:
                raise RuntimeError(f"Failed to encode speech audio: {exc}") from exc
            return output

        stream_spec = "".join([f"[{i}:a]" for i in range(n)])
        filter_complex = f"{stream_spec}concat=n={n}:v=0:a=1[a]"
        cmd = ["ffmpeg"]
        for audio in audios:
            cmd.extend(["-i", audio])
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[a]",
            "-c:a", "aac",
            "-b:a", "192k",
            "-y",
            output,
        ])
        try:
            run_ffmpeg_compiled(cmd, timeout=timeout, label="concat-speech")
        except Exception as exc:
            raise RuntimeError(f"Failed to concatenate speech audio: {exc}") from exc
        return output

    def _mux_gapless_speech_onto_video(
        self,
        video: str,
        speech: str,
        output: str,
    ) -> str:
        """
        Mux gapless speech under a (possibly longer) visual timeline.

        When holds make video longer than speech, pad speech with trailing silence
        so duration matches the picture (holds at end stay silent on the speech track).
        Speech itself has no inter-scene gaps.
        """
        self._ensure_ffmpeg()
        Path(output).parent.mkdir(parents=True, exist_ok=True)

        video_duration = self._get_video_duration(video)
        speech_duration = self._get_audio_duration(speech)
        target_duration = max(video_duration, speech_duration, 0.1)
        timeout = post_mux_timeout_seconds(target_duration, reencode=True)

        # Pad speech to video length when holds extend the picture timeline.
        # Do not insert silence between scenes — only trailing pad if needed.
        cmd = [
            "ffmpeg", "-y",
            "-i", video,
            "-i", speech,
            "-filter_complex",
            (
                f"[1:a]apad=whole_dur={target_duration:.6f}[a];"
                f"[0:v]setpts=PTS-STARTPTS[v]"
            ),
            "-map", "[v]",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", f"{target_duration:.6f}",
            output,
        ]
        try:
            run_ffmpeg_compiled(cmd, timeout=timeout, label="gapless-mux")
        except Exception as primary_exc:
            # Stream-copy video when re-encode fails (geometry already compatible)
            logger.warning("Gapless mux re-encode failed, trying copy video: {}", primary_exc)
            cmd_copy = [
                "ffmpeg", "-y",
                "-i", video,
                "-i", speech,
                "-filter_complex",
                f"[1:a]apad=whole_dur={target_duration:.6f}[a]",
                "-map", "0:v:0",
                "-map", "[a]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{target_duration:.6f}",
                output,
            ]
            try:
                run_ffmpeg_compiled(
                    cmd_copy,
                    timeout=post_mux_timeout_seconds(target_duration, reencode=False),
                    label="gapless-mux-copy",
                )
            except Exception as secondary_exc:
                raise RuntimeError(
                    f"Failed to mux gapless speech onto video: {primary_exc}; {secondary_exc}"
                ) from secondary_exc
        logger.success(
            "Muxed gapless speech (video={:.2f}s speech={:.2f}s target={:.2f}s): {}",
            video_duration,
            speech_duration,
            target_duration,
            output,
        )
        return output

    def concat_videos(
        self,
        videos: List[str],
        output: str,
        method: Literal["demuxer", "filter"] = "demuxer",
        bgm_path: Optional[str] = None,
        bgm_volume: float = 0.2,
        bgm_mode: Literal["once", "loop"] = "loop",
        bookend: Optional[dict] = None,
    ) -> str:
        """
        Concatenate multiple videos into one

        Args:
            videos: List of video file paths to concatenate
            output: Output video file path
            method: Concatenation method
                - "demuxer": Fast, no re-encoding (requires identical formats)
                - "filter": Slower but handles different formats
            bgm_path: Background music file path (optional)
                - None: No BGM
        """
        self._ensure_ffmpeg()

        if not videos:
            raise ValueError("Videos list cannot be empty")

        bookend = bookend or {}
        needs_bookend = bool(
            bookend.get("enabled")
            or float(bookend.get("intro_seconds") or 0) > 0
            or float(bookend.get("outro_seconds") or 0) > 0
        )

        logger.info(f"Concatenating {len(videos)} videos using {method} method")

        # Step 1: Concatenate videos (single clip is a no-op copy)
        temp_concat = output.replace(".mp4", "_concat_tmp.mp4")
        if len(videos) == 1:
            logger.info(f"Only one video provided, using as base: {videos[0]}")
            shutil.copy(videos[0], temp_concat)
            concat_result = temp_concat
        elif method == "demuxer":
            concat_result = self._concat_demuxer(videos, temp_concat)
        else:
            concat_result = self._concat_filter(videos, temp_concat)

        temp_paths = [temp_concat]
        try:
            packed = concat_result
            if needs_bookend:
                packed = output.replace(".mp4", "_bookend_tmp.mp4")
                temp_paths.append(packed)
                self.apply_bookend_packaging(
                    video=concat_result,
                    output=packed,
                    intro_seconds=float(bookend.get("intro_seconds") or 0),
                    outro_seconds=float(bookend.get("outro_seconds") or 0),
                    intro_fade_seconds=float(bookend.get("intro_fade_seconds") or 0),
                    outro_fade_seconds=float(bookend.get("outro_fade_seconds") or 0),
                )

            if bgm_path:
                logger.info(f"Adding BGM: {bgm_path} (volume={bgm_volume}, mode={bgm_mode})")
                return self._add_bgm_to_video(
                    video=packed,
                    bgm_path=bgm_path,
                    output=output,
                    volume=bgm_volume,
                    mode=bgm_mode,
                    fade_in=float(bookend.get("intro_fade_seconds") or 0),
                    fade_out=float(bookend.get("outro_fade_seconds") or 0),
                )

            if os.path.abspath(packed) != os.path.abspath(output):
                shutil.copy(packed, output)
            return output
        finally:
            for path in temp_paths:
                try:
                    if path and os.path.exists(path) and os.path.abspath(path) != os.path.abspath(output):
                        os.unlink(path)
                except OSError:
                    pass

    def _concat_demuxer(self, videos: List[str], output: str) -> str:
        """
        Concatenate using concat demuxer (fast, no re-encoding)

        FFmpeg equivalent:
            ffmpeg -f concat -safe 0 -i filelist.txt -c copy output.mp4
        """
        # Write the concat list next to the output (not system TEMP).
        # On some Windows environments, TEMP files are rewritten by transparent
        # encryption / DLP and FFmpeg then sees garbage like "%TSD-Header-###%".
        output_path = Path(output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Use .ffconcat (not .txt): some Windows DLP/transparent-encryption
        # products rewrite *.txt in TEMP/workspace and FFmpeg then sees "%TSD-Header-###%".
        filelist_path = output_path.with_name(output_path.stem + ".ffconcat")
        lines = []
        for video in videos:
            abs_path = Path(video).resolve().as_posix()
            escaped_path = abs_path.replace("'", r"'\''")
            lines.append(f"file '{escaped_path}'")
        filelist_path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        filelist = str(filelist_path)

        try:
            logger.debug(f"Created filelist: {filelist}")
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", filelist,
                "-c", "copy",
                str(output_path),
            ]
            timeout = post_mux_timeout_seconds(reencode=False, segment_count=len(videos))
            try:
                run_ffmpeg_compiled(cmd, timeout=timeout, label="concat-demuxer")
            except Exception as demuxer_exc:
                error_msg = str(demuxer_exc)
                logger.error(f"FFmpeg concat error: {error_msg}")
                # Fall back to filter concat when stream-copy demuxer fails.
                logger.warning("Concat demuxer failed; retrying with filter method (re-encode)")
                try:
                    return self._concat_filter(videos, str(output_path))
                except Exception as filter_exc:
                    raise RuntimeError(
                        f"Failed to concatenate videos (demuxer and filter): {error_msg}; {filter_exc}"
                    ) from filter_exc
            logger.success(f"Videos concatenated successfully: {output}")
            return str(output_path)
        finally:
            if filelist_path.exists():
                try:
                    filelist_path.unlink()
                except OSError:
                    pass

    def _concat_filter(self, videos: List[str], output: str) -> str:
        """
        Concatenate using concat filter (slower but handles different formats)

        FFmpeg equivalent:
            ffmpeg -i v1.mp4 -i v2.mp4 -filter_complex "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]"
                   -map "[v]" -map "[a]" output.mp4
        """
        try:
            n = len(videos)
            stream_spec = "".join([f"[{i}:v][{i}:a]" for i in range(n)])
            filter_complex = f"{stream_spec}concat=n={n}:v=1:a=1[v][a]"

            cmd = ["ffmpeg"]
            for video in videos:
                cmd.extend(["-i", video])
            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-map", "[a]",
                "-y",
                output,
            ])

            timeout = post_mux_timeout_seconds(reencode=True, segment_count=n)
            run_ffmpeg_compiled(cmd, timeout=timeout, label="concat-filter")

            logger.success(f"Videos concatenated successfully: {output}")
            return output
        except Exception as e:
            logger.error(f"Concatenation error: {e}")
            raise RuntimeError(f"Failed to concatenate videos: {e}") from e

    def _get_video_duration(self, video: str) -> float:
        """Get video duration in seconds"""
        try:
            probe = ffmpeg.probe(video)
            duration = float(probe['format']['duration'])
            return duration
        except Exception as e:
            logger.warning(f"Failed to get video duration: {e}")
            return 0.0

    def _get_audio_duration(self, audio: str) -> float:
        """Get audio duration in seconds"""
        try:
            probe = ffmpeg.probe(audio)
            duration = float(probe['format']['duration'])
            return duration
        except Exception as e:
            logger.warning(f"Failed to get audio duration: {e}, using estimate")
            # Fallback: estimate based on file size (very rough)
            import os
            file_size = os.path.getsize(audio)
            # Assume ~16kbps for MP3, so 2KB per second
            estimated_duration = file_size / 2000
            return max(1.0, estimated_duration)  # At least 1 second

    def _probe_video_geometry(self, video: str) -> tuple[int, int]:
        """Return video width and height."""
        probe = ffmpeg.probe(video)
        video_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
        return int(video_stream["width"]), int(video_stream["height"])

    def _find_subtitle_font(self) -> str:
        """Find a local font that can render Chinese subtitles."""
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/NotoSansSC-VF.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/simsun.ttc",
            "C:/Windows/Fonts/Deng.ttf",
            "C:/Windows/Fonts/msjh.ttc",
        ]

        for candidate in candidates:
            if os.path.exists(candidate):
                return Path(candidate).as_posix()

        raise RuntimeError(
            "No usable subtitle font found. Install a Chinese-capable font or disable subtitles."
        )

    def _wrap_subtitle_text(
        self,
        text: str,
        max_chars: int = 18,
        max_lines: int = 2,
    ) -> str:
        """Wrap subtitle text into a compact bottom caption block."""
        normalized = " ".join(str(text or "").split())
        if not normalized:
            return ""

        lines: list[str] = []
        current = ""
        for char in normalized:
            if len(current) >= max_chars:
                lines.append(current)
                current = char
                if len(lines) >= max_lines:
                    break
            else:
                current += char

        if len(lines) < max_lines and current:
            lines.append(current)

        return "\n".join(lines[:max_lines])

    def _escape_drawtext_text(self, text: str) -> str:
        """Escape text for FFmpeg drawtext filter arguments."""
        return (
            str(text)
            .replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
            .replace("%", "\\%")
            .replace("\n", "\\n")
        )

    def _ffmpeg_filter_available(self, filter_name: str) -> bool:
        """Return whether the installed FFmpeg exposes a filter."""
        if VideoService._ffmpeg_filters is None:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-filters"],
                capture_output=True,
                text=True,
                check=True,
            )
            filters: set[str] = set()
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and "." in parts[0]:
                    filters.add(parts[1])
            VideoService._ffmpeg_filters = filters

        return filter_name in VideoService._ffmpeg_filters

    def _create_subtitle_overlay_image(
        self,
        text: str,
        width: int,
        height: int,
        font_size: int,
        bottom_margin: int,
    ) -> str:
        """Create a transparent subtitle PNG for FFmpeg overlay fallback."""
        from PIL import Image, ImageDraw, ImageFont

        font_path = self._find_subtitle_font()
        font = ImageFont.truetype(font_path, font_size)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=max(4, font_size // 6))
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = max(0, (width - text_width) // 2)
        y = max(0, height - text_height - bottom_margin)

        draw.multiline_text(
            (x, y),
            text,
            font=font,
            fill=(255, 255, 255, 255),
            spacing=max(4, font_size // 6),
            align="center",
            stroke_width=max(2, width // 360),
            stroke_fill=(0, 0, 0, 255),
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            overlay.save(tmp.name)
            return tmp.name

    def _plain_image_motion_expressions(
        self,
        frame_index: int,
        frame_count: int,
    ) -> tuple[str, str, str]:
        """Return zoompan expressions for the automatic subtle motion variants."""
        last_frame = max(frame_count - 1, 1)
        progress = f"(on/{last_frame})"
        eased_progress = f"({progress})*({progress})*(3-2*({progress}))"
        variant = frame_index % 4

        if variant == 0:
            zoom = f"min(1.08,1+0.08*{eased_progress})"
            x = "iw/2-(iw/zoom/2)"
            y = "ih/2-(ih/zoom/2)"
        elif variant == 1:
            zoom = f"max(1,1.08-0.08*{eased_progress})"
            x = "iw/2-(iw/zoom/2)"
            y = "ih/2-(ih/zoom/2)"
        elif variant == 2:
            zoom = "1.04"
            x = f"(iw-iw/zoom)*{eased_progress}"
            y = "ih/2-(ih/zoom/2)"
        else:
            zoom = "1.04"
            x = f"(iw-iw/zoom)*(1-{eased_progress})"
            y = "ih/2-(ih/zoom/2)"

        return zoom, x, y

    def _cover_scale_expressions(self, width: int, height: int, overscale: float = 1.0) -> tuple[str, str]:
        """Build scale expressions that cover the target canvas while preserving aspect ratio."""
        return (
            f"ceil(iw*max({width}/iw,{height}/ih)*{overscale}/2)*2",
            f"ceil(ih*max({width}/iw,{height}/ih)*{overscale}/2)*2",
        )

    def create_video_from_image_with_motion(
        self,
        image: str,
        audio: str,
        output: str,
        fps: int = 30,
        width: int = 1080,
        height: int = 1920,
        subtitle_text: Optional[str] = None,
        subtitle_enabled: bool = True,
        motion_enabled: bool = True,
        motion_mode: str = "auto",
        motion_strength: str = "subtle",
        image_fit_mode: str = "cover",
        frame_index: int = 0,
        subtitle_style: Optional[dict] = None,
        subtitle_alignment: Optional[list] = None,
        duration: Optional[float] = None,
    ) -> str:
        """
        Create a video segment directly from a generated image and narration audio.

        The image is cover-fitted to the output canvas. Optional automatic motion applies
        restrained zoom or pan movement, and optional subtitles are drawn near the bottom.
        """
        if image_fit_mode != "cover":
            raise ValueError(f"Unsupported image fit mode: {image_fit_mode}")
        if motion_mode != "auto":
            raise ValueError(f"Unsupported image motion mode: {motion_mode}")
        if motion_strength != "subtle":
            raise ValueError(f"Unsupported image motion strength: {motion_strength}")
        if width <= 0 or height <= 0:
            raise ValueError("media_width and media_height must be positive integers")
        if fps <= 0:
            raise ValueError("fps must be a positive integer")

        self._ensure_ffmpeg()
        logger.info("Creating pure image video segment")
        subtitle_overlay_path: Optional[str] = None
        subtitle_workspace: Optional[str] = None

        try:
            audio_duration = self._get_audio_duration(audio)
            target_duration = max(audio_duration, float(duration or 0))
            frame_count = max(1, math.ceil(target_duration * fps))
            input_audio = ffmpeg.input(audio)

            if motion_enabled:
                render_scale = 2
                render_width = width * render_scale
                render_height = height * render_scale
                scale_w, scale_h = self._cover_scale_expressions(
                    render_width,
                    render_height,
                    overscale=1.08,
                )
                zoom, x, y = self._plain_image_motion_expressions(frame_index, frame_count)
                video_stream = (
                    ffmpeg
                    .input(image)
                    .filter("scale", scale_w, scale_h)
                    .filter("setsar", "1")
                    .filter(
                        "zoompan",
                        z=zoom,
                        x=x,
                        y=y,
                        d=frame_count,
                        s=f"{render_width}x{render_height}",
                        fps=fps,
                    )
                    .filter("scale", width, height, flags="lanczos")
                    .filter("trim", duration=target_duration)
                    .filter("setpts", "PTS-STARTPTS")
                )
            else:
                scale_w, scale_h = self._cover_scale_expressions(width, height)
                video_stream = (
                    ffmpeg
                    .input(image, loop=1, framerate=fps)
                    .filter("scale", scale_w, scale_h)
                    .filter("crop", width, height, "(iw-ow)/2", "(ih-oh)/2")
                    .filter("setsar", "1")
                    .filter("trim", duration=target_duration)
                    .filter("setpts", "PTS-STARTPTS")
                )

            encode_timeout = segment_encode_timeout_seconds(
                target_duration, width=width, height=height
            )

            if subtitle_enabled and subtitle_text and str(subtitle_text).strip():
                renderer = SubtitleRenderer()
                normalized_style = renderer.normalize_style(subtitle_style)
                subtitle_burned = False

                # 1) Hyperframes dynamic path (rounded box + animations when available).
                # High-res VP9 overlay has been observed to hang ffmpeg indefinitely
                # (0-byte output, frozen CPU, blocked API). Skip unless forced.
                force_hyperframes = str(
                    os.getenv("PIXELLE_FORCE_HYPERFRAMES") or ""
                ).strip().lower() in {"1", "true", "yes", "on"}
                high_res = width * height >= 1080 * 1080
                if (
                    normalized_style["mode"] == "hyperframes"
                    and high_res
                    and not force_hyperframes
                ):
                    logger.info(
                        "Skipping hyperframes for {}x{} segment (hang risk); using Pillow/ASS",
                        width,
                        height,
                    )
                    normalized_style["mode"] = "ass"

                if normalized_style["mode"] == "hyperframes":
                    try:
                        subtitle_workspace = tempfile.mkdtemp(prefix="pixelle-hyperframes-")
                        subtitle_config = config_manager.get("subtitle", {})
                        npx_command = str(
                            os.getenv("PIXELLE_NPX_COMMAND")
                            or subtitle_config.get("npx_command")
                            or "npx"
                        ).strip()
                        dynamic_renderer = HyperframesCaptionRenderer(
                            npx_command=npx_command or "npx"
                        )
                        caption_plan = dynamic_renderer.build_caption_plan(
                            text=subtitle_text,
                            duration=target_duration,
                            width=width,
                            height=height,
                            fps=fps,
                            style=normalized_style,
                            alignment=subtitle_alignment,
                        )
                        subtitle_overlay_path = dynamic_renderer.render_overlay(
                            caption_plan,
                            subtitle_workspace,
                        )
                        overlay_stream = ffmpeg.input(
                            subtitle_overlay_path,
                            **{"c:v": "libvpx-vp9"},
                        ).video.filter("setpts", "PTS-STARTPTS")
                        video_stream = ffmpeg.overlay(
                            video_stream,
                            overlay_stream,
                            eof_action="pass",
                        )
                        subtitle_burned = True
                    except (OSError, RuntimeError, ValueError) as exc:
                        logger.warning(
                            "Dynamic subtitle rendering failed; trying Pillow/ASS fallback: {}",
                            exc,
                        )
                        normalized_style["mode"] = "ass"
                        if subtitle_workspace and os.path.exists(subtitle_workspace):
                            shutil.rmtree(subtitle_workspace, ignore_errors=True)
                        subtitle_workspace = None
                        subtitle_overlay_path = None

                # 2) Pillow rounded-box path (no Node; supports radius ASS cannot draw).
                if (
                    not subtitle_burned
                    and should_use_pillow_captions(normalized_style)
                ):
                    try:
                        subtitle_workspace = tempfile.mkdtemp(prefix="pixelle-pillow-captions-")
                        custom_font_path = str(normalized_style.get("fontPath") or "").strip()
                        if not custom_font_path:
                            try:
                                custom_font_path = self._find_subtitle_font()
                            except RuntimeError:
                                custom_font_path = ""
                        pillow_renderer = PillowCaptionRenderer(subtitle_renderer=renderer)
                        pillow_overlays = pillow_renderer.render_overlays(
                            text=subtitle_text,
                            duration=target_duration,
                            width=width,
                            height=height,
                            style=normalized_style,
                            alignment=subtitle_alignment,
                            output_dir=subtitle_workspace,
                            font_path=custom_font_path or None,
                        )
                        for item in pillow_overlays:
                            # Still PNGs need loop+duration so enable=between can hold them on screen.
                            cue = (
                                ffmpeg
                                .input(item.path, loop=1, framerate=fps, t=target_duration)
                                .filter("setpts", "PTS-STARTPTS")
                            )
                            video_stream = ffmpeg.overlay(
                                video_stream,
                                cue,
                                enable=f"between(t,{item.start:.3f},{item.end:.3f})",
                                eof_action="pass",
                            )
                        subtitle_burned = True
                        logger.info(
                            "Pillow caption overlays applied ({} cues, rounded box fallback)",
                            len(pillow_overlays),
                        )
                    except (OSError, RuntimeError, ValueError) as exc:
                        logger.warning(
                            "Pillow caption rendering failed; falling back to ASS: {}",
                            exc,
                        )
                        if subtitle_workspace and os.path.exists(subtitle_workspace):
                            shutil.rmtree(subtitle_workspace, ignore_errors=True)
                        subtitle_workspace = None

                # 3) ASS / drawtext / legacy static PIL.
                if not subtitle_burned:
                    font_path = self._find_subtitle_font()
                    max_chars = max(8, min(22, width // 54))
                    wrapped_text = self._wrap_subtitle_text(
                        subtitle_text,
                        max_chars=max_chars,
                        max_lines=2,
                    )
                    if not wrapped_text:
                        wrapped_text = ""
                    font_size = max(24, min(120, int(normalized_style.get("fontSize", width // 22))))
                    bottom_margin = max(48, height // 14)
                    if (
                        wrapped_text
                        and self._ffmpeg_filter_available("subtitles")
                    ):
                        # Prefer user font; otherwise discover a local Chinese-capable font.
                        custom_font_path = str(normalized_style.get("fontPath") or "").strip()
                        if not custom_font_path:
                            try:
                                custom_font_path = self._find_subtitle_font()
                                normalized_style = {
                                    **normalized_style,
                                    "fontPath": custom_font_path,
                                }
                            except RuntimeError:
                                custom_font_path = ""
                        subtitle_overlay_path = renderer.create_ass_file(
                            text=subtitle_text,
                            duration=target_duration,
                            width=width,
                            height=height,
                            style=normalized_style,
                            alignment=subtitle_alignment,
                        )
                        subtitle_filter_kwargs = {
                            "filename": Path(subtitle_overlay_path).as_posix(),
                        }
                        if custom_font_path:
                            font_file = Path(custom_font_path).expanduser()
                            if font_file.is_file():
                                subtitle_filter_kwargs["fontsdir"] = font_file.parent.as_posix()
                                # Force libass to pick the selected family even if system
                                # fonts would otherwise win the name match.
                                family = renderer._font_name(normalized_style)
                                if family:
                                    subtitle_filter_kwargs["force_style"] = (
                                        f"Fontname={family}"
                                    )
                        video_stream = video_stream.filter("subtitles", **subtitle_filter_kwargs)
                    elif wrapped_text and self._ffmpeg_filter_available("drawtext"):
                        custom_font_path = Path(
                            str(normalized_style.get("fontPath") or "")
                        ).expanduser()
                        drawtext_font_path = (
                            custom_font_path.as_posix()
                            if custom_font_path.is_file()
                            else font_path
                        )
                        video_stream = video_stream.filter(
                            "drawtext",
                            fontfile=drawtext_font_path,
                            text=self._escape_drawtext_text(wrapped_text),
                            fontsize=font_size,
                            fontcolor=str(normalized_style.get("primaryColor") or "#FFFFFF"),
                            bordercolor=str(normalized_style.get("outlineColor") or "#000000"),
                            borderw=max(0, int(normalized_style.get("outlineWidth", 3))),
                            shadowx=max(0, int(normalized_style.get("shadow", 0))),
                            shadowy=max(0, int(normalized_style.get("shadow", 0))),
                            shadowcolor=str(normalized_style.get("outlineColor") or "#000000"),
                            box=1 if (
                                normalized_style.get("boxEnabled")
                                or normalized_style.get("preset") == "caption-box"
                            ) else 0,
                            boxcolor=(
                                f"{str(normalized_style.get('boxColor') or normalized_style.get('backColor') or '#000000')}@"
                                f"{max(0, min(100, int(normalized_style.get('boxOpacity', normalized_style.get('backgroundOpacity', 72))))) / 100:.2f}"
                            ),
                            boxborderw=(
                                max(
                                    4,
                                    int(
                                        normalized_style.get(
                                            "boxPadding",
                                            normalized_style.get("outlineWidth", 0),
                                        )
                                        or 0
                                    )
                                    * 2,
                                )
                                if (
                                    normalized_style.get("boxEnabled")
                                    or normalized_style.get("preset") == "caption-box"
                                )
                                else 0
                            ),
                            line_spacing=max(4, font_size // 6),
                            x="(w-text_w)/2",
                            y=f"h-text_h-{bottom_margin}",
                        )
                    elif wrapped_text:
                        subtitle_overlay_path = self._create_subtitle_overlay_image(
                            wrapped_text,
                            width=width,
                            height=height,
                            font_size=font_size,
                            bottom_margin=bottom_margin,
                        )
                        video_stream = ffmpeg.overlay(
                            video_stream,
                            ffmpeg.input(subtitle_overlay_path),
                        )

            out_stream = (
                ffmpeg
                .output(
                    video_stream,
                    input_audio.audio.filter("apad"),
                    output,
                    t=target_duration,
                    vcodec="libx264",
                    acodec="aac",
                    pix_fmt="yuv420p",
                    audio_bitrate="192k",
                    # faster preset: less CPU hang surface on caption overlays
                    preset="veryfast",
                    crf=23,
                    r=fps,
                    **{"b:v": "2M"},
                )
            )
            try:
                run_ffmpeg_stream(
                    out_stream,
                    timeout=encode_timeout,
                    label=f"pure-image-segment({Path(output).name})",
                )
            except TimeoutError:
                # If hyperframes VP9 overlay hung, wipe partial file and re-raise
                # with a clear message so callers/UI can retry without a dead API.
                try:
                    if output and os.path.exists(output) and os.path.getsize(output) < 1024:
                        os.unlink(output)
                except OSError:
                    pass
                logger.error(
                    "Pure image segment encode timed out after {:.0f}s: {}",
                    encode_timeout,
                    output,
                )
                raise

            if not output or not os.path.exists(output) or os.path.getsize(output) < 1024:
                raise RuntimeError(
                    f"Pure image segment produced empty/missing output: {output}"
                )

            logger.success(f"Pure image video segment created: {output}")
            return output
        except ffmpeg.Error as e:
            error_msg = decode_ffmpeg_output(e.stderr) if e.stderr else str(e)
            logger.error(f"FFmpeg error creating pure image segment: {error_msg}")
            raise RuntimeError(f"Failed to create pure image video segment: {error_msg}")
        finally:
            if subtitle_overlay_path and os.path.exists(subtitle_overlay_path):
                os.unlink(subtitle_overlay_path)
            if subtitle_workspace and os.path.exists(subtitle_workspace):
                shutil.rmtree(subtitle_workspace, ignore_errors=True)

    def has_audio_stream(self, video: str) -> bool:
        """
        Check if video has audio stream

        Args:
            video: Video file path

        Returns:
            True if video has audio stream, False otherwise
        """
        try:
            probe = ffmpeg.probe(video)
            audio_streams = [s for s in probe.get('streams', []) if s['codec_type'] == 'audio']
            has_audio = len(audio_streams) > 0
            logger.debug(f"Video {video} has_audio={has_audio}")
            return has_audio
        except Exception as e:
            logger.warning(f"Failed to probe video audio streams: {e}, assuming no audio")
            return False

    def merge_audio_video(
        self,
        video: str,
        audio: str,
        output: str,
        replace_audio: bool = True,
        audio_volume: float = 1.0,
        video_volume: float = 0.0,
        pad_strategy: str = "freeze",  # "freeze" (freeze last frame) or "black" (black screen)
        auto_adjust_duration: bool = True,  # Automatically adjust video duration to match audio
        duration_tolerance: float = 0.3,  # Tolerance for video being longer than audio (seconds)
    ) -> str:
        """
        Merge audio with video with intelligent duration adjustment

        Automatically handles duration mismatches between video and audio:
        - If video < audio: Pad video to match audio (avoid black screen)
        - If video > audio (within tolerance): Keep as-is (acceptable)
        - If video > audio (exceeds tolerance): Trim video to match audio

        Automatically handles videos with or without audio streams.
        - If video has no audio: adds the audio track
        - If video has audio and replace_audio=True: replaces with new audio
        - If video has audio and replace_audio=False: mixes both audio tracks

        Args:
            video: Video file path
            audio: Audio file path
            output: Output video file path
            replace_audio: If True, replace video's audio; if False, mix with original
            audio_volume: Volume of the new audio (0.0 to 1.0+)
            video_volume: Volume of original video audio (0.0 to 1.0+)
                         Only used when replace_audio=False
            pad_strategy: Strategy to pad video if audio is longer
                         - "freeze": Freeze last frame (default)
                         - "black": Fill with black screen
            auto_adjust_duration: Enable intelligent duration adjustment (default: True)
            duration_tolerance: Tolerance for video being longer than audio in seconds (default: 0.3)
                              Videos within this tolerance won't be trimmed

        Returns:
            Path to the output video file

        Raises:
            RuntimeError: If FFmpeg execution fails

        Note:
            - Uses the longer duration between video and audio
            - When audio is longer, video is padded using pad_strategy
            - When video is longer, audio is looped or extended
            - Automatically detects if video has audio
            - When video is silent, audio is added regardless of replace_audio
            - When replace_audio=True and video has audio, original audio is removed
            - When replace_audio=False and video has audio, original and new audio are mixed
        """
        self._ensure_ffmpeg()

        # Get durations of video and audio
        video_duration = self._get_video_duration(video)
        audio_duration = self._get_audio_duration(audio)

        logger.info(f"Video duration: {video_duration:.2f}s, Audio duration: {audio_duration:.2f}s")

        # Intelligent duration adjustment (if enabled)
        if auto_adjust_duration:
            diff = video_duration - audio_duration

            if diff < 0:
                # Video shorter than audio → Must pad to avoid black screen
                logger.warning(f"⚠️ Video shorter than audio by {abs(diff):.2f}s, padding required")
                video = self._pad_video_to_duration(video, audio_duration, pad_strategy)
                video_duration = audio_duration  # Update duration after padding
                logger.info(f"📌 Padded video to {audio_duration:.2f}s")

            elif diff > duration_tolerance:
                # Video significantly longer than audio → Trim
                logger.info(f"⚠️ Video longer than audio by {diff:.2f}s (tolerance: {duration_tolerance}s)")
                video = self._trim_video_to_duration(video, audio_duration)
                video_duration = audio_duration  # Update duration after trimming
                logger.info(f"✂️ Trimmed video to {audio_duration:.2f}s")

            else:  # 0 <= diff <= duration_tolerance
                # Video slightly longer but within tolerance → Keep as-is
                logger.info(f"✅ Duration acceptable: video={video_duration:.2f}s, audio={audio_duration:.2f}s (diff={diff:.2f}s)")

        # Determine target duration (max of both)
        target_duration = max(video_duration, audio_duration)
        logger.info(f"Target output duration: {target_duration:.2f}s")

        # Check if video has audio stream
        video_has_audio = self.has_audio_stream(video)

        # Prepare video stream (potentially with padding)
        input_video = ffmpeg.input(video)
        video_stream = input_video.video

        # Pad video if audio is longer
        if audio_duration > video_duration:
            pad_duration = audio_duration - video_duration
            logger.info(f"Audio is longer, padding video by {pad_duration:.2f}s using '{pad_strategy}' strategy")

            if pad_strategy == "freeze":
                # Freeze last frame: tpad filter
                video_stream = video_stream.filter('tpad', stop_mode='clone', stop_duration=pad_duration)
            else:  # black
                # Generate black frames for padding duration
                # Get video properties
                probe = ffmpeg.probe(video)
                video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
                width = int(video_info['width'])
                height = int(video_info['height'])
                fps_str = video_info['r_frame_rate']
                fps_num, fps_den = map(int, fps_str.split('/'))
                fps = fps_num / fps_den if fps_den != 0 else 30

                black_input = ffmpeg.input(
                    f'color=c=black:s={width}x{height}:r={fps}',
                    f='lavfi',
                    t=pad_duration
                )

                # Concatenate original video with black padding
                video_stream = ffmpeg.concat(video_stream, black_input.video, v=1, a=0)

        # Prepare audio stream (pad if needed to match target duration)
        input_audio = ffmpeg.input(audio)
        audio_stream = input_audio.audio.filter('volume', audio_volume)

        # Pad audio with silence if video is longer
        if video_duration > audio_duration:
            pad_duration = video_duration - audio_duration
            logger.info(f"Video is longer, padding audio with {pad_duration:.2f}s silence")
            # Use apad to add silence at the end
            audio_stream = audio_stream.filter('apad', whole_dur=target_duration)

        merge_timeout = post_mux_timeout_seconds(target_duration, reencode=True)

        if not video_has_audio:
            logger.info("Video has no audio stream, adding audio track")
            try:
                stream = (
                    ffmpeg
                    .output(
                        video_stream,
                        audio_stream,
                        output,
                        vcodec='libx264',
                        acodec='aac',
                        audio_bitrate='192k'
                    )
                )
                run_ffmpeg_stream(stream, timeout=merge_timeout, label="merge-audio-silent")
                logger.success(f"Audio added to silent video: {output}")
                return output
            except Exception as e:
                logger.error(f"FFmpeg error adding audio to silent video: {e}")
                raise RuntimeError(f"Failed to add audio to video: {e}") from e

        # Video has audio, proceed with merging
        logger.info(f"Merging audio with video (replace={replace_audio})")

        try:
            if replace_audio:
                stream = (
                    ffmpeg
                    .output(
                        video_stream,
                        audio_stream,
                        output,
                        vcodec='libx264',
                        acodec='aac',
                        audio_bitrate='192k'
                    )
                )
                run_ffmpeg_stream(stream, timeout=merge_timeout, label="merge-audio-replace")
            else:
                mixed_audio = ffmpeg.filter(
                    [
                        input_video.audio.filter('volume', video_volume),
                        audio_stream
                    ],
                    'amix',
                    inputs=2,
                    duration='longest'
                )
                stream = (
                    ffmpeg
                    .output(
                        video_stream,
                        mixed_audio,
                        output,
                        vcodec='libx264',
                        acodec='aac',
                        audio_bitrate='192k'
                    )
                )
                run_ffmpeg_stream(stream, timeout=merge_timeout, label="merge-audio-mix")

            logger.success(f"Audio merged successfully: {output}")
            return output
        except Exception as e:
            logger.error(f"FFmpeg merge error: {e}")
            raise RuntimeError(f"Failed to merge audio and video: {e}") from e

    def overlay_image_on_video(
        self,
        video: str,
        overlay_image: str,
        output: str,
        scale_mode: str = "contain"
    ) -> str:
        """
        Overlay a transparent image on top of video

        Args:
            video: Base video file path
            overlay_image: Transparent overlay image path (e.g., rendered HTML with transparent background)
            output: Output video file path
            scale_mode: How to scale the base video to fit the overlay size
                - "contain": Scale video to fit within overlay dimensions (letterbox/pillarbox)
                - "cover": Scale video to cover overlay dimensions (may crop)
                - "stretch": Stretch video to exact overlay dimensions

        Returns:
            Path to the output video file

        Raises:
            RuntimeError: If FFmpeg execution fails

        Note:
            - Overlay image should have transparent background
            - Video is scaled to match overlay dimensions based on scale_mode
            - Final video size matches overlay image size
            - Video codec is re-encoded to support overlay
        """
        self._ensure_ffmpeg()
        logger.info(f"Overlaying image on video (scale_mode={scale_mode})")

        try:
            # Get overlay image dimensions
            overlay_probe = ffmpeg.probe(overlay_image)
            overlay_stream = next(s for s in overlay_probe['streams'] if s['codec_type'] == 'video')
            overlay_width = int(overlay_stream['width'])
            overlay_height = int(overlay_stream['height'])

            logger.debug(f"Overlay dimensions: {overlay_width}x{overlay_height}")

            input_video = ffmpeg.input(video)
            input_overlay = ffmpeg.input(overlay_image)

            # Scale video to fit overlay size using scale_mode
            if scale_mode == "contain":
                # Scale to fit (letterbox/pillarbox if aspect ratio differs)
                # Use scale filter with force_original_aspect_ratio=decrease and pad to center
                scaled_video = (
                    input_video
                    .filter('scale', overlay_width, overlay_height, force_original_aspect_ratio='decrease')
                    .filter('pad', overlay_width, overlay_height, '(ow-iw)/2', '(oh-ih)/2', color='black')
                )
            elif scale_mode == "cover":
                # Scale to cover (crop if aspect ratio differs)
                scaled_video = (
                    input_video
                    .filter('scale', overlay_width, overlay_height, force_original_aspect_ratio='increase')
                    .filter('crop', overlay_width, overlay_height)
                )
            else:  # stretch
                # Stretch to exact dimensions
                scaled_video = input_video.filter('scale', overlay_width, overlay_height)

            # Overlay the transparent image on top of the scaled video
            output_stream = ffmpeg.overlay(scaled_video, input_overlay)

            (
                ffmpeg
                .output(output_stream, output,
                        vcodec='libx264',
                        pix_fmt='yuv420p',
                        preset='medium',
                        crf=23)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )

            logger.success(f"Image overlaid on video: {output}")
            return output
        except ffmpeg.Error as e:
            error_msg = decode_ffmpeg_output(e.stderr) if e.stderr else str(e)
            logger.error(f"FFmpeg overlay error: {error_msg}")
            raise RuntimeError(f"Failed to overlay image on video: {error_msg}")

    def create_video_from_image(
        self,
        image: str,
        audio: str,
        output: str,
        fps: int = 30,
        duration: Optional[float] = None,
    ) -> str:
        """
        Create video from static image and audio

        Args:
            image: Image file path
            audio: Audio file path
            output: Output video path
            fps: Frames per second

        Returns:
            Path to the output video

        Raises:
            RuntimeError: If FFmpeg execution fails

        Note:
            - Image is displayed as static frame for the duration of audio
            - Video duration matches audio duration
            - Useful for creating video segments from storyboard frames

        Example:
            >>> compositor.create_video_from_image(
            ...     "frame.png",
            ...     "narration.mp3",
            ...     "segment.mp4"
            ... )
        """
        self._ensure_ffmpeg()
        logger.info("Creating video from image and audio")

        try:
            # Get audio duration to ensure exact video duration match
            probe = ffmpeg.probe(audio)
            audio_duration = float(probe['format']['duration'])
            target_duration = max(audio_duration, float(duration or 0))
            logger.debug(f"Video duration: {target_duration:.3f}s")

            # Input image with loop (loop=1 means loop indefinitely)
            # Use framerate to set input framerate
            input_image = ffmpeg.input(image, loop=1, framerate=fps)
            input_audio = ffmpeg.input(audio)

            # Combine image and audio
            # Use -t to explicitly set video duration = audio duration
            out_stream = (
                ffmpeg
                .output(
                    input_image,
                    input_audio.audio.filter("apad"),
                    output,
                    t=target_duration,
                    vcodec='libx264',
                    acodec='aac',
                    pix_fmt='yuv420p',
                    audio_bitrate='192k',
                    preset='veryfast',
                    crf=23,
                    **{'b:v': '2M'}  # Video bitrate
                )
            )
            run_ffmpeg_stream(
                out_stream,
                timeout=segment_encode_timeout_seconds(target_duration),
                label=f"image-segment({Path(output).name})",
            )

            logger.success(f"Video created from image: {output} (duration: {audio_duration:.3f}s)")
            return output
        except ffmpeg.Error as e:
            error_msg = decode_ffmpeg_output(e.stderr) if e.stderr else str(e)
            logger.error(f"FFmpeg error creating video from image: {error_msg}")
            raise RuntimeError(f"Failed to create video from image: {error_msg}")

    def apply_bookend_packaging(
        self,
        video: str,
        output: str,
        *,
        intro_seconds: float = 1.2,
        outro_seconds: float = 2.0,
        intro_fade_seconds: float = 0.6,
        outro_fade_seconds: float = 1.0,
    ) -> str:
        """
        Add project-level intro/outro packaging to a finished picture+speech video.

        - Intro: clone first frame pad + leading silence on speech, video fade-in
        - Outro: clone last frame pad + trailing silence, video fade-out
        - Speech is delayed by intro (no mid-sentence silence inserted in content)

        Outro is additive with per-scene manual holds already baked into segments.
        """
        self._ensure_ffmpeg()
        intro = max(0.0, float(intro_seconds or 0.0))
        outro = max(0.0, float(outro_seconds or 0.0))
        fade_in = max(0.0, min(float(intro_fade_seconds or 0.0), intro if intro > 0 else 0.0))
        fade_out = max(0.0, min(float(outro_fade_seconds or 0.0), outro if outro > 0 else 0.0))

        if intro <= 0 and outro <= 0 and fade_in <= 0 and fade_out <= 0:
            if os.path.abspath(video) != os.path.abspath(output):
                shutil.copy(video, output)
            return output

        content_duration = max(0.1, self._get_video_duration(video))
        total_duration = content_duration + intro + outro
        fade_out_start = max(0.0, total_duration - fade_out)

        Path(output).parent.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Applying bookend packaging: intro={:.2f}s outro={:.2f}s fade_in={:.2f}s fade_out={:.2f}s",
            intro,
            outro,
            fade_in,
            fade_out,
        )

        # Video: pad clone frames, then fades on the extended timeline.
        v_filters: list[str] = []
        if intro > 0 or outro > 0:
            v_filters.append(
                f"tpad=start_mode=clone:start_duration={intro:.6f}"
                f":stop_mode=clone:stop_duration={outro:.6f}"
            )
        if fade_in > 0:
            v_filters.append(f"fade=t=in:st=0:d={fade_in:.6f}")
        if fade_out > 0:
            v_filters.append(f"fade=t=out:st={fade_out_start:.6f}:d={fade_out:.6f}")
        v_filters.append("setpts=PTS-STARTPTS")
        v_chain = ",".join(v_filters)

        # Audio: delay for intro (silence), pad for outro, light afade on edges.
        # Content speech starts after intro_seconds (delayed narration entry).
        a_filters: list[str] = []
        if intro > 0:
            delay_ms = int(round(intro * 1000))
            a_filters.append(f"adelay={delay_ms}|{delay_ms}")
        a_filters.append(f"apad=whole_dur={total_duration:.6f}")
        if fade_in > 0:
            a_filters.append(f"afade=t=in:st=0:d={fade_in:.6f}")
        if fade_out > 0:
            a_filters.append(f"afade=t=out:st={fade_out_start:.6f}:d={fade_out:.6f}")
        a_chain = ",".join(a_filters)

        # Some inputs may lack audio (silent video-only); generate silent track then.
        has_audio = self.has_audio_stream(video)
        if has_audio:
            filter_complex = (
                f"[0:v]{v_chain}[v];"
                f"[0:a]{a_chain}[a]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-i", video,
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-map", "[a]",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{total_duration:.6f}",
                output,
            ]
        else:
            filter_complex = f"[0:v]{v_chain}[v]"
            cmd = [
                "ffmpeg", "-y",
                "-i", video,
                "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-map", "1:a",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-t", f"{total_duration:.6f}",
                "-shortest",
                output,
            ]

        try:
            run_ffmpeg_compiled(
                cmd,
                timeout=segment_encode_timeout_seconds(total_duration) + 60,
                label="bookend-packaging",
            )
        except Exception as exc:
            logger.error("Bookend packaging failed: {}", exc)
            raise RuntimeError(f"Failed to apply intro/outro packaging: {exc}") from exc

        if not Path(output).is_file() or Path(output).stat().st_size < 1024:
            raise RuntimeError(f"Bookend packaging produced empty output: {output}")

        logger.success(
            "Bookend packaging applied ({:.2f}s → {:.2f}s): {}",
            content_duration,
            total_duration,
            output,
        )
        return output

    def add_bgm(
        self,
        video: str,
        bgm: str,
        output: str,
        bgm_volume: float = 0.3,
        loop: bool = True,
        fade_in: float = 0.0,
        fade_out: float = 0.0,
    ) -> str:
        """
        Add background music to video

        Args:
            video: Video file path
            bgm: Background music file path
            output: Output video file path
            bgm_volume: BGM volume relative to original (0.0 to 1.0+)
            loop: If True, loop BGM to match video duration
            fade_in: BGM fade-in duration in seconds
            fade_out: BGM fade-out duration in seconds (from end of video)

        Returns:
            Path to the output video file
        """
        self._ensure_ffmpeg()
        logger.info(
            "Adding BGM to video (volume={}, loop={}, fade_in={:.2f}, fade_out={:.2f})",
            bgm_volume,
            loop,
            fade_in,
            fade_out,
        )

        try:
            video_duration = max(0.1, self._get_video_duration(video))
            fade_in = max(0.0, float(fade_in or 0.0))
            fade_out = max(0.0, float(fade_out or 0.0))
            fade_out_start = max(0.0, video_duration - fade_out)

            input_video = ffmpeg.input(video)
            bgm_input = ffmpeg.input(bgm, stream_loop=-1 if loop else 0)
            bgm_audio = bgm_input.audio.filter("volume", bgm_volume)
            if fade_in > 0:
                bgm_audio = bgm_audio.filter("afade", type="in", start_time=0, duration=fade_in)
            if fade_out > 0:
                bgm_audio = bgm_audio.filter(
                    "afade",
                    type="out",
                    start_time=fade_out_start,
                    duration=fade_out,
                )
            # Match video length exactly
            bgm_audio = bgm_audio.filter("atrim", duration=video_duration).filter(
                "asetpts", "PTS-STARTPTS"
            )

            if self.has_audio_stream(video):
                mixed_audio = ffmpeg.filter(
                    [input_video.audio, bgm_audio],
                    "amix",
                    inputs=2,
                    duration="first",
                    dropout_transition=0,
                )
            else:
                mixed_audio = bgm_audio

            stream = (
                ffmpeg
                .output(
                    input_video.video,
                    mixed_audio,
                    output,
                    vcodec="copy",
                    acodec="aac",
                    audio_bitrate="192k",
                    t=video_duration,
                )
            )
            run_ffmpeg_stream(
                stream,
                timeout=post_mux_timeout_seconds(video_duration, reencode=False),
                label="add-bgm",
            )

            logger.success(f"BGM added successfully: {output}")
            return output
        except Exception as e:
            logger.error(f"FFmpeg BGM error: {e}")
            raise RuntimeError(f"Failed to add BGM: {e}") from e

    def _add_bgm_to_video(
        self,
        video: str,
        bgm_path: str,
        output: str,
        volume: float = 0.2,
        mode: Literal["once", "loop"] = "loop",
        fade_in: float = 0.0,
        fade_out: float = 0.0,
    ) -> str:
        """
        Internal helper to add BGM to video with path resolution
        """
        resolved_bgm = self._resolve_bgm_path(bgm_path)
        loop = mode == "loop"
        return self.add_bgm(
            video=video,
            bgm=resolved_bgm,
            output=output,
            bgm_volume=volume,
            loop=loop,
            fade_in=fade_in,
            fade_out=fade_out,
        )

    def _get_unique_temp_path(self, prefix: str, original_filename: str) -> str:
        """
        Generate unique temporary file path to avoid concurrent conflicts

        Args:
            prefix: Prefix for the temp file (e.g., "trimmed", "padded", "black_pad")
            original_filename: Original filename to preserve in temp path

        Returns:
            Unique temporary file path with format: temp/{prefix}_{uuid}_{original_filename}

        Example:
            >>> self._get_unique_temp_path("trimmed", "video.mp4")
            >>> # Returns: "temp/trimmed_a3f2d8c1_video.mp4"
        """
        from pixelle_video.utils.os_util import get_temp_path

        unique_id = uuid.uuid4().hex[:8]
        return get_temp_path(f"{prefix}_{unique_id}_{original_filename}")

    def _resolve_bgm_path(self, bgm_path: str) -> str:
        """
        Resolve BGM path (filename or custom path) with custom override support

        Search priority:
            1. Direct path (absolute or relative)
            2. data/bgm/{filename} (custom)
            3. bgm/{filename} (default)

        Args:
            bgm_path: Can be:
                - Filename with extension (e.g., "default.mp3", "happy.mp3"): auto-resolved from bgm/ or data/bgm/
                - Custom file path (absolute or relative)

        Returns:
            Resolved absolute path

        Raises:
            FileNotFoundError: If BGM file not found
        """
        # Try direct path first (absolute or relative)
        if os.path.exists(bgm_path):
            return os.path.abspath(bgm_path)

        if bgm_path.startswith("custom-bgm/"):
            custom_bgm_folder = str(config_manager.get("quick_create", {}).get("custom_bgm_folder") or "").strip()
            if custom_bgm_folder:
                custom_base = Path(custom_bgm_folder).expanduser().resolve()
                candidate = (custom_base / bgm_path.removeprefix("custom-bgm/")).resolve()
                try:
                    candidate.relative_to(custom_base)
                except ValueError:
                    candidate = None
                if candidate and candidate.is_file():
                    return str(candidate)

        # Try as filename in resource directories (custom > default)
        if resource_exists("bgm", bgm_path):
            return get_resource_path("bgm", bgm_path)

        # Not found - provide helpful error message
        tried_paths = [
            os.path.abspath(bgm_path),
            f"data/bgm/{bgm_path} or bgm/{bgm_path}"
        ]

        # List available BGM files
        available_bgm = self._list_available_bgm()
        available_msg = f"\n  Available BGM files: {', '.join(available_bgm)}" if available_bgm else ""

        raise FileNotFoundError(
            f"BGM file not found: '{bgm_path}'\n"
            f"  Tried paths:\n"
            f"    1. {tried_paths[0]}\n"
            f"    2. {tried_paths[1]}"
            f"{available_msg}"
        )

    def _list_available_bgm(self) -> list[str]:
        """
        List available BGM files (merged from bgm/ and data/bgm/)

        Returns:
            List of filenames (with extensions), sorted
        """
        try:
            # Use resource API to get merged list
            all_files = list_resource_files("bgm")

            # Filter to audio files only
            audio_extensions = ('.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac')
            return sorted([f for f in all_files if f.lower().endswith(audio_extensions)])
        except Exception as e:
            logger.warning(f"Failed to list BGM files: {e}")
            return []

    def _trim_video_to_duration(self, video: str, target_duration: float) -> str:
        """
        Trim video to specified duration

        Args:
            video: Input video file path
            target_duration: Target duration in seconds

        Returns:
            Path to trimmed video (temp file)

        Raises:
            RuntimeError: If FFmpeg execution fails
        """
        output = self._get_unique_temp_path("trimmed", os.path.basename(video))

        try:
            # Use stream copy when possible for fast trimming
            input_stream = ffmpeg.input(video, t=target_duration)
            output_kwargs = {"vcodec": "copy"}
            if self.has_audio_stream(video):
                output_kwargs["acodec"] = "copy"
            (
                input_stream
                .output(output, **output_kwargs)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True, quiet=True)
            )
            return output
        except ffmpeg.Error as e:
            error_msg = decode_ffmpeg_output(e.stderr) if e.stderr else str(e)
            logger.error(f"FFmpeg error trimming video: {error_msg}")
            raise RuntimeError(f"Failed to trim video: {error_msg}")

    def _pad_video_to_duration(self, video: str, target_duration: float, pad_strategy: str = "freeze") -> str:
        """
        Pad video to specified duration by extending the last frame or adding black frames

        Args:
            video: Input video file path
            target_duration: Target duration in seconds
            pad_strategy: Padding strategy - "freeze" (freeze last frame) or "black" (black screen)

        Returns:
            Path to padded video (temp file)

        Raises:
            RuntimeError: If FFmpeg execution fails
        """
        output = self._get_unique_temp_path("padded", os.path.basename(video))

        video_duration = self._get_video_duration(video)
        pad_duration = target_duration - video_duration

        if pad_duration <= 0:
            # No padding needed, return original
            return video

        try:
            input_video = ffmpeg.input(video)
            video_stream = input_video.video

            if pad_strategy == "freeze":
                # Freeze last frame using tpad filter
                video_stream = video_stream.filter('tpad', stop_mode='clone', stop_duration=pad_duration)

                # Output with re-encoding (tpad requires it)
                (
                    ffmpeg
                    .output(
                        video_stream,
                        output,
                        vcodec='libx264',
                        preset='fast',
                        crf=23
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True, quiet=True)
                )
            else:  # black
                # Generate black frames for padding duration
                # Get video properties
                probe = ffmpeg.probe(video)
                video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
                width = int(video_info['width'])
                height = int(video_info['height'])
                fps_str = video_info['r_frame_rate']
                fps_num, fps_den = map(int, fps_str.split('/'))
                fps = fps_num / fps_den if fps_den != 0 else 30

                # Create black video for padding
                black_input = ffmpeg.input(
                    f'color=c=black:s={width}x{height}:r={fps}',
                    f='lavfi',
                    t=pad_duration
                )

                # Concatenate original video with black padding
                video_stream = ffmpeg.concat(video_stream, black_input.video, v=1, a=0)

                (
                    ffmpeg
                    .output(
                        video_stream,
                        output,
                        vcodec='libx264',
                        preset='fast',
                        crf=23
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True, quiet=True)
                )

            return output
        except ffmpeg.Error as e:
            error_msg = decode_ffmpeg_output(e.stderr) if e.stderr else str(e)
            logger.error(f"FFmpeg error padding video: {error_msg}")
            raise RuntimeError(f"Failed to pad video: {error_msg}")
