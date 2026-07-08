from api.routers import workbench


def test_quick_create_preset_defaults_to_image_motion_view(monkeypatch):
    monkeypatch.setattr(
        workbench.config_manager,
        "get_comfyui_config",
        lambda: {
            "tts": {},
            "image": {"prompt_prefix": ""},
            "video": {"prompt_prefix": ""},
        },
    )
    monkeypatch.setattr(
        workbench.config_manager,
        "get",
        lambda key, default=None: {
            "quick_create": {},
            "template": {"composition_mode": "template"},
        }.get(key, default),
    )
    monkeypatch.setattr(workbench, "resource_exists", lambda *_args: False)

    preset = workbench._preset_from_config()

    assert preset["viewMode"] == "pure-image"
