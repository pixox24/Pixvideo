from pixelle_video.utils.bookend import DEFAULT_BOOKEND, normalize_bookend_config


def test_default_bookend_enabled():
    cfg = normalize_bookend_config({})
    assert cfg["enabled"] is True
    assert cfg["intro_seconds"] == DEFAULT_BOOKEND["intro_seconds"]
    assert cfg["outro_seconds"] == DEFAULT_BOOKEND["outro_seconds"]


def test_disable_bookend_zeros_pads():
    cfg = normalize_bookend_config({"bookendEnabled": False})
    assert cfg["enabled"] is False
    assert cfg["intro_seconds"] == 0
    assert cfg["outro_seconds"] == 0


def test_camel_case_and_fade_clamped_to_pad():
    cfg = normalize_bookend_config(
        {
            "bookendEnabled": True,
            "bookendIntroSeconds": 1.0,
            "bookendOutroSeconds": 2.0,
            "bookendIntroFadeSeconds": 5.0,  # > intro → clamp
            "bookendOutroFadeSeconds": 0.5,
        }
    )
    assert cfg["intro_fade_seconds"] == 1.0
    assert cfg["outro_fade_seconds"] == 0.5
