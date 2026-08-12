from pixelle_video.utils.video_canvas import (
    DEFAULT_VIDEO_HEIGHT,
    DEFAULT_VIDEO_WIDTH,
    map_image_gen_size,
    normalize_video_canvas,
)


def test_default_canvas_is_1080x1920_30():
    canvas = normalize_video_canvas({})
    assert canvas["width"] == DEFAULT_VIDEO_WIDTH
    assert canvas["height"] == DEFAULT_VIDEO_HEIGHT
    assert canvas["fps"] == 30
    assert canvas["tier"] == "recommended"


def test_1440_is_advanced():
    canvas = normalize_video_canvas({"mediaWidth": 1440, "mediaHeight": 2560})
    assert canvas["is_advanced"] is True
    assert canvas["preset_id"] == "1440x2560"


def test_map_portrait_1080_to_whitelist():
    w, h = map_image_gen_size(1080, 1920)
    # exact whitelist or closest portrait
    assert h >= w
    assert (w, h) in {
        (1024, 1536),
        (1080, 1920),
        (720, 1280),
    }


def test_map_square():
    w, h = map_image_gen_size(1080, 1080)
    assert w == h
    assert (w, h) in {(1024, 1024), (1080, 1080)}


def test_map_advanced_1440_to_whitelist():
    # 1440p canvas is advanced; gen size must still hit whitelist
    w, h = map_image_gen_size(1440, 2560)
    assert h >= w
    assert (w, h) in {
        (1024, 1536),
        (1080, 1920),
        (720, 1280),
    }
    assert (w, h) != (1440, 2560)


def test_map_landscape_advanced_to_whitelist():
    w, h = map_image_gen_size(2560, 1440)
    assert w >= h
    assert (w, h) == (1920, 1080)
