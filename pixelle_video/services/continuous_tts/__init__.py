"""Continuous multi-scene TTS: assemble once, synthesize once, split by alignment."""

from pixelle_video.services.continuous_tts.assemble import (
    assemble_continuous_script,
    normalize_tts_delivery,
    should_use_continuous_tts,
)
from pixelle_video.services.continuous_tts.models import (
    AssembledScript,
    ContinuousSceneSegment,
    ContinuousSplitResult,
    SceneAudioSlice,
)
from pixelle_video.services.continuous_tts.split import (
    detect_silence_islands,
    extract_audio_segment,
    extract_audio_segments,
    plan_scene_slices,
    proportional_slices,
    snap_proportional_cuts_to_silence,
)

__all__ = [
    "AssembledScript",
    "ContinuousSceneSegment",
    "ContinuousSplitResult",
    "SceneAudioSlice",
    "assemble_continuous_script",
    "detect_silence_islands",
    "extract_audio_segment",
    "extract_audio_segments",
    "normalize_tts_delivery",
    "plan_scene_slices",
    "proportional_slices",
    "should_use_continuous_tts",
    "snap_proportional_cuts_to_silence",
]
