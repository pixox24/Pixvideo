from types import SimpleNamespace

from pixelle_video.services.video import VideoService


def test_video_compositor_resolves_selected_custom_bgm_folder(tmp_path, monkeypatch):
    selected_folder = tmp_path / "selected"
    selected_folder.mkdir()
    audio_file = selected_folder / "track.mp3"
    audio_file.write_bytes(b"audio")

    monkeypatch.setattr(
        "pixelle_video.services.video.config_manager",
        SimpleNamespace(get=lambda key, default=None: {"custom_bgm_folder": str(selected_folder)} if key == "quick_create" else default),
    )

    assert VideoService()._resolve_bgm_path("custom-bgm/track.mp3") == str(audio_file.resolve())
