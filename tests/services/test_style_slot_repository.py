from io import BytesIO

from PIL import Image

from pixelle_video.services.style_slot_repository import StyleSlotRepository


def _image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 16), "red").save(output, format="PNG")
    return output.getvalue()


def test_style_slot_round_trip_and_normalizes_reference_image(tmp_path):
    repository = StyleSlotRepository(tmp_path / "slots.sqlite3", tmp_path / "media")
    slot = repository.create(
        name="纸张插画",
        image_bytes=_image_bytes(),
        style={"style_prefix": "paper texture, bold linework", "style_tags": ["纸张"], "confidence": 0.9},
    )

    assert slot["stylePrefix"] == "paper texture, bold linework"
    assert slot["styleTags"] == ["纸张"]
    assert (tmp_path / "media" / slot["id"] / "reference.jpg").read_bytes().startswith(b"\xff\xd8")

    updated = repository.update(slot["id"], {"stylePrefix": "new prefix", "strength": 85})
    assert updated and updated["stylePrefix"] == "new prefix"
    assert updated["strength"] == 85
    assert repository.delete(slot["id"])
    assert repository.list() == []
