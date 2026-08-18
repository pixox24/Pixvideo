from pixelle_video.utils.project_config import normalize_project_config, pick_config


def test_pick_config_prefers_camel_when_both_present():
    cfg = {"enableSubtitles": False, "subtitle_enabled": True}
    assert pick_config(cfg, "enableSubtitles", "subtitle_enabled", default=True) is False


def test_pick_config_falls_back_to_snake():
    cfg = {"subtitle_enabled": False}
    assert pick_config(cfg, "enableSubtitles", "subtitle_enabled", default=True) is False


def test_normalize_dual_writes_from_camel():
    out = normalize_project_config({"enableSubtitles": False, "bgmVolume": 40, "mediaWidth": 1080})
    assert out["enableSubtitles"] is False
    assert out["subtitle_enabled"] is False
    assert out["bgmVolume"] == 40
    assert out["bgm_volume"] == 40
    assert out["mediaWidth"] == 1080
    assert out["media_width"] == 1080


def test_normalize_dual_writes_from_snake():
    out = normalize_project_config({"subtitle_enabled": True, "image_motion_enabled": False})
    assert out["enableSubtitles"] is True
    assert out["enableMotion"] is False


def test_normalize_camel_wins_when_both_conflict():
    out = normalize_project_config({
        "enableSubtitles": False,
        "subtitle_enabled": True,
        "enableMotion": False,
        "image_motion_enabled": True,
    })
    assert out["enableSubtitles"] is False
    assert out["subtitle_enabled"] is False
    assert out["enableMotion"] is False
    assert out["image_motion_enabled"] is False


def test_normalize_defaults_to_auto_standard_director():
    out = normalize_project_config({})
    assert out["directorMode"] == "auto"
    assert out["director_mode"] == "auto"
    assert out["density"] == "standard"
    assert out["storyboard_density"] == "standard"
    assert out["targetSceneCount"] is None


def test_normalize_legacy_scene_count_as_custom_soft_target():
    out = normalize_project_config({"sceneCount": 7})
    assert out["directorMode"] == "custom"
    assert out["director_mode"] == "custom"
    assert out["targetSceneCount"] == 7
    assert out["target_scene_count"] == 7
