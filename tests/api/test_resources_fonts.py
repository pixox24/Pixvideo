from types import SimpleNamespace

import pytest

from api.routers import resources


@pytest.mark.asyncio
async def test_list_fonts_includes_custom_font_folder(monkeypatch, tmp_path):
    font_dir = tmp_path / "fonts"
    font_dir.mkdir()
    font_file = font_dir / "BrandFont.ttf"
    font_file.write_bytes(b"fake-font")

    monkeypatch.setattr(resources, "get_root_path", lambda *parts: str(tmp_path / "root" / "/".join(parts)))
    monkeypatch.setattr(resources, "get_data_path", lambda *parts: str(tmp_path / "data" / "/".join(parts)))
    monkeypatch.setattr(resources.Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(
        resources,
        "SYSTEM_FONT_DIRS",
        (),
        raising=False,
    )
    monkeypatch.setattr(
        resources,
        "config_manager",
        SimpleNamespace(
            get=lambda key, default=None: {"custom_font_folder": str(font_dir)}
            if key == "subtitle"
            else default,
        ),
    )

    response = await resources.list_fonts()

    matching_fonts = [font for font in response.fonts if font.path == str(font_file)]
    assert len(matching_fonts) == 1
    assert matching_fonts[0].name == "BrandFont"
    assert matching_fonts[0].source == "custom-folder"


@pytest.mark.asyncio
async def test_select_custom_font_folder_saves_confirmed_folder(tmp_path, monkeypatch):
    updates = []
    saves = []
    selected_folder = tmp_path / "selected-fonts"
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

    result = await resources.select_custom_font_folder()

    assert result["path"] == str(selected_folder)
    assert updates == [{"subtitle": {"custom_font_folder": str(selected_folder)}}]
    assert saves == [True]
