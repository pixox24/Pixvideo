from pathlib import Path
from types import SimpleNamespace

import pytest

from api.routers import resources


@pytest.mark.asyncio
async def test_open_custom_bgm_folder_creates_and_opens_data_bgm(tmp_path, monkeypatch):
    opened = []

    monkeypatch.setattr(resources, "get_data_path", lambda *parts: str(tmp_path.joinpath(*parts)))
    monkeypatch.setattr(resources.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(resources.subprocess, "Popen", lambda args: opened.append(args))

    result = await resources.open_custom_bgm_folder()

    expected_path = tmp_path / "bgm"
    assert Path(result["path"]) == expected_path
    assert expected_path.exists()
    assert opened == [["open", str(expected_path)]]


@pytest.mark.asyncio
async def test_select_custom_bgm_folder_saves_confirmed_folder(tmp_path, monkeypatch):
    updates = []
    saves = []
    selected_folder = tmp_path / "selected"
    selected_folder.mkdir()

    monkeypatch.setattr(resources.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        resources.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout=f"{selected_folder}\n"),
    )
    monkeypatch.setattr(
        resources,
        "config_manager",
        SimpleNamespace(
            update=lambda data: updates.append(data),
            save=lambda: saves.append(True),
        ),
    )

    result = await resources.select_custom_bgm_folder()

    assert result["path"] == str(selected_folder)
    assert updates == [{"quick_create": {"custom_bgm_folder": str(selected_folder)}}]
    assert saves == [True]


@pytest.mark.asyncio
async def test_list_bgm_includes_selected_custom_folder(tmp_path, monkeypatch):
    selected_folder = tmp_path / "selected"
    selected_folder.mkdir()
    (selected_folder / "track.mp3").write_bytes(b"audio")

    monkeypatch.setattr(resources, "get_root_path", lambda *parts: str(tmp_path / "root" / Path(*parts)))
    monkeypatch.setattr(resources, "get_data_path", lambda *parts: str(tmp_path / "data" / Path(*parts)))
    monkeypatch.setattr(
        resources,
        "config_manager",
        SimpleNamespace(get=lambda key, default=None: {"custom_bgm_folder": str(selected_folder)} if key == "quick_create" else default),
    )

    result = await resources.list_bgm()

    assert result.bgm_files[0].name == "track.mp3"
    assert result.bgm_files[0].path == "custom-bgm/track.mp3"
    assert result.bgm_files[0].source == "custom-folder"
