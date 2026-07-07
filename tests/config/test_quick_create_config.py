import yaml

from pixelle_video.config.manager import ConfigManager


def test_save_quick_create_config_persists_reusable_defaults(tmp_path):
    old_instance = ConfigManager._instance
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
project_name: Pixelle-Video
comfyui:
  tts:
    minimax:
      api_key: keep-this-key
template:
  image_motion_enabled: false
quick_create:
  bgm_path: default.mp3
  bgm_volume: 0.2
""",
        encoding="utf-8",
    )

    try:
        ConfigManager._instance = None
        manager = ConfigManager(str(config_path))

        manager.save_quick_create_config(
            {
                "text": "one-off topic",
                "title": "one-off title",
                "ref_audio": "temp/ref.wav",
                "tts_inference_mode": "minimax",
                "tts_voice": "female-shaonv",
                "tts_speed": 1.4,
                "minimax_model": "speech-2.8-hd",
                "minimax_emotion": "happy",
                "frame_template": "1080x1920/video_default.html",
                "template_type": "video",
                "template_media_type": "video",
                "composition_mode": "template",
                "image_motion_enabled": True,
                "subtitle_enabled": False,
                "media_workflow": "runninghub/video_wan2.1_fusionx.json",
                "prompt_prefix": "cinematic style",
                "bgm_path": "custom.mp3",
                "bgm_volume": 0.31,
            }
        )

        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))

        assert data["comfyui"]["tts"]["inference_mode"] == "minimax"
        assert data["comfyui"]["tts"]["minimax"]["api_key"] == "keep-this-key"
        assert data["comfyui"]["tts"]["minimax"]["model"] == "speech-2.8-hd"
        assert data["comfyui"]["tts"]["minimax"]["voice_id"] == "female-shaonv"
        assert data["comfyui"]["tts"]["minimax"]["speed"] == 1.4
        assert data["comfyui"]["tts"]["minimax"]["emotion"] == "happy"
        assert data["comfyui"]["video"]["default_workflow"] == "runninghub/video_wan2.1_fusionx.json"
        assert data["comfyui"]["video"]["prompt_prefix"] == "cinematic style"
        assert data["template"]["default_template"] == "1080x1920/video_default.html"
        assert data["template"]["template_type"] == "video"
        assert data["template"]["composition_mode"] == "template"
        assert data["template"]["image_motion_enabled"] is True
        assert data["template"]["subtitle_enabled"] is False
        assert data["quick_create"]["bgm_path"] == "custom.mp3"
        assert data["quick_create"]["bgm_volume"] == 0.31
        assert "one-off topic" not in str(data)
        assert "one-off title" not in str(data)
        assert "temp/ref.wav" not in str(data)

        ConfigManager._instance = None
        reloaded = ConfigManager(str(config_path))

        assert reloaded.config.comfyui.tts.inference_mode == "minimax"
        assert reloaded.config.comfyui.tts.minimax.voice_id == "female-shaonv"
        assert reloaded.config.comfyui.video.default_workflow == "runninghub/video_wan2.1_fusionx.json"
        assert reloaded.config.template.default_template == "1080x1920/video_default.html"
        assert reloaded.config.quick_create.bgm_path == "custom.mp3"
    finally:
        ConfigManager._instance = old_instance
