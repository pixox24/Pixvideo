from pathlib import Path

import pytest
from PIL import Image

from pixelle_video.services.workbench_media import WorkbenchMediaStore


def _image(path: Path) -> None:
    Image.new("RGB", (640, 480), "red").save(path, format="PNG")


def test_upload_is_copied_inside_project_root(tmp_path):
    source = tmp_path / "input.png"
    _image(source)
    store = WorkbenchMediaStore(tmp_path / "projects")

    relative_path = store.copy_upload("p1", "s1", source, "nested/my-image.png")

    assert relative_path == "assets/scenes/s1/uploads/my-image.png"
    assert (tmp_path / "projects" / "p1" / relative_path).is_file()


def test_relative_path_cannot_escape_project_root(tmp_path):
    store = WorkbenchMediaStore(tmp_path / "projects")

    with pytest.raises(ValueError, match="outside project"):
        store.resolve("p1", "../../secret.txt")


def test_thumbnail_is_project_local_and_bounded(tmp_path):
    source = tmp_path / "projects" / "p1" / "assets" / "scenes" / "s1" / "generated"
    source.mkdir(parents=True)
    image_path = source / "v1.png"
    _image(image_path)
    store = WorkbenchMediaStore(tmp_path / "projects")

    thumbnail = store.create_thumbnail(image_path, "assets/scenes/s1/generated/v1.png")

    result = store.resolve("p1", thumbnail)
    assert result.is_file()
    with Image.open(result) as image:
        assert max(image.size) <= 320

