from pathlib import Path

from PIL import Image

from pixelle_video.services.pillow_caption_renderer import (
    PillowCaptionRenderer,
    should_use_pillow_captions,
)


def test_should_use_pillow_for_rounded_caption_box():
    assert should_use_pillow_captions({"preset": "caption-box", "boxRadius": 12}) is True
    assert should_use_pillow_captions({"boxEnabled": True, "boxRadius": 8}) is True
    assert should_use_pillow_captions({"preset": "caption-box", "boxRadius": 0}) is False
    assert should_use_pillow_captions({"preset": "short-video-bold", "boxRadius": 12}) is False
    assert should_use_pillow_captions(None) is False


def test_render_overlays_splits_sentences_and_draws_rounded_box(tmp_path):
    renderer = PillowCaptionRenderer()
    overlays = renderer.render_overlays(
        text="第一句旁白。第二句旁白。",
        duration=4.0,
        width=720,
        height=1280,
        style={
            "preset": "caption-box",
            "boxRadius": 16,
            "boxPadding": 10,
            "boxColor": "#000000",
            "boxOpacity": 80,
            "primaryColor": "#FFFFFF",
            "fontSize": 48,
            "segmentMode": "sentence",
            "marginV": 120,
            "maxCharsPerLine": 14,
            "maxLines": 1,
        },
        output_dir=tmp_path,
    )

    assert len(overlays) == 2
    assert overlays[0].start == 0.0
    assert overlays[-1].end == 4.0
    for item in overlays:
        path = Path(item.path)
        assert path.is_file()
        assert path.stat().st_size > 0
        image = Image.open(path).convert("RGBA")
        assert image.size == (720, 1280)
        # Must not be fully transparent (box/text present).
        alpha = [pixel[3] for pixel in image.getdata()]
        assert max(alpha) > 0


def test_legacy_outline_width_zero_still_gets_visible_box(tmp_path):
    renderer = PillowCaptionRenderer()
    overlays = renderer.render_overlays(
        text="旧默认无框修复",
        duration=2.0,
        width=540,
        height=960,
        style={
            "preset": "caption-box",
            "outlineWidth": 0,
            "boxRadius": 12,
            "fontSize": 40,
            "segmentMode": "sentence",
        },
        output_dir=tmp_path,
    )
    assert len(overlays) == 1
    image = Image.open(overlays[0].path).convert("RGBA")
    # Count near-black semi-opaque pixels near bottom (caption box).
    w, h = image.size
    dark = 0
    total = 0
    for y in range(int(h * 0.75), h):
        for x in range(int(w * 0.2), int(w * 0.8)):
            r, g, b, a = image.getpixel((x, y))
            total += 1
            if a > 40 and r < 40 and g < 40 and b < 40:
                dark += 1
    assert dark > 50, f"expected rounded box pixels, dark={dark}/{total}"
