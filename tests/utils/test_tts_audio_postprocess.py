from pathlib import Path

from pixelle_video.utils.tts_audio_postprocess import SPEAKER_LOCK_PHRASE, with_speaker_lock


def test_speaker_lock_appended_for_multi_scene():
    result = with_speaker_lock("清亮女声，语速适中", multi_scene=True)
    assert result is not None
    assert "清亮女声" in result
    assert SPEAKER_LOCK_PHRASE in result


def test_speaker_lock_not_duplicated():
    first = with_speaker_lock("清亮女声", multi_scene=True)
    second = with_speaker_lock(first, multi_scene=True)
    assert first == second
    assert second.count(SPEAKER_LOCK_PHRASE) == 1


def test_speaker_lock_force_for_voice_design():
    assert SPEAKER_LOCK_PHRASE in (with_speaker_lock("", multi_scene=True, force=True) or "")


def test_postprocess_skips_missing_file(tmp_path):
    from pixelle_video.utils.tts_audio_postprocess import postprocess_tts_clip
    import pytest

    missing = tmp_path / "missing.mp3"
    with pytest.raises(FileNotFoundError):
        postprocess_tts_clip(missing)
