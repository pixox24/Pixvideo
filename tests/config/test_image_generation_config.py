from pixelle_video.config.manager import ConfigManager


def test_config_manager_persists_image_generation_config(tmp_path):
    old_instance = ConfigManager._instance
    config_path = tmp_path / "config.yaml"
    config_path.write_text("project_name: Pixelle-Video\n", encoding="utf-8")

    try:
        ConfigManager._instance = None
        manager = ConfigManager(str(config_path))

        manager.set_image_generation_config(
            api_key="img-key",
            base_url="https://img-cn.65535.space/v1",
            model="gpt-image-2",
        )
        manager.save()

        ConfigManager._instance = None
        reloaded = ConfigManager(str(config_path))

        assert reloaded.get_image_generation_config() == {
            "api_key": "img-key",
            "base_url": "https://img-cn.65535.space/v1",
            "model": "gpt-image-2",
        }
    finally:
        ConfigManager._instance = old_instance
