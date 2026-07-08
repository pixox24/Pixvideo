from types import SimpleNamespace

import pytest
from fastapi.responses import FileResponse

from api.routers import files


@pytest.mark.asyncio
async def test_files_router_serves_selected_custom_bgm_folder(tmp_path, monkeypatch):
    selected_folder = tmp_path / "selected"
    selected_folder.mkdir()
    audio_file = selected_folder / "track.mp3"
    audio_file.write_bytes(b"audio")

    monkeypatch.setattr(
        files,
        "config_manager",
        SimpleNamespace(get=lambda key, default=None: {"custom_bgm_folder": str(selected_folder)} if key == "quick_create" else default),
    )

    response = await files.get_file("custom-bgm/track.mp3")

    assert isinstance(response, FileResponse)
    assert response.path == str(audio_file.resolve())


@pytest.mark.asyncio
async def test_files_router_serves_unicode_custom_bgm_filename(tmp_path, monkeypatch):
    selected_folder = tmp_path / "selected"
    selected_folder.mkdir()
    audio_file = selected_folder / "晚安.mp3"
    audio_file.write_bytes(b"audio")

    monkeypatch.setattr(
        files,
        "config_manager",
        SimpleNamespace(get=lambda key, default=None: {"custom_bgm_folder": str(selected_folder)} if key == "quick_create" else default),
    )

    response = await files.get_file("custom-bgm/晚安.mp3")

    assert isinstance(response, FileResponse)
    assert response.path == str(audio_file.resolve())
