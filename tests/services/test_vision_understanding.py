from io import BytesIO

import pytest
from PIL import Image

from pixelle_video.services.vision_understanding import prepare_image_data_url, validate_style_result


def test_prepare_image_data_url_reencodes_and_strips_to_jpeg():
    source = BytesIO()
    Image.new("RGBA", (20, 20), "blue").save(source, format="PNG")
    url, mime = prepare_image_data_url(source.getvalue(), "image/png", max_bytes=100_000, max_pixels=1_000)
    assert mime == "image/jpeg"
    assert url.startswith("data:image/jpeg;base64,")


def test_style_result_requires_non_empty_prefix():
    with pytest.raises(ValueError, match="style_prefix_empty"):
        validate_style_result({"style_prefix": ""})


def test_style_result_limits_user_visible_collections():
    result = validate_style_result({"style_prefix": "ink line art", "style_tags": [str(value) for value in range(20)], "confidence": 2})
    assert len(result["style_tags"]) == 12
    assert result["confidence"] == 1
