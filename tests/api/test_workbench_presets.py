import json

import pytest

from api.routers import workbench
from api.routers import workbench_support


def test_quick_create_preset_excludes_template_mode(monkeypatch):
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
    monkeypatch.setattr(workbench_support, "resource_exists", lambda *_args: False)

    preset = workbench._preset_from_config()

    assert "viewMode" not in preset
    assert "template" not in preset


def _preset_payload(name: str = "小红书竖屏口播"):
    return {
        "name": name,
        "ttsMode": "minimax",
        "voice": "male-qn-qingse",
        "speed": 1.15,
        "workflow": "runninghub/video.json",
        "bgm": "custom.mp3",
        "bgmVolume": 25,
        "promptPrefix": "cinematic amber style",
        "splitType": "sentence",
        "enableMotion": True,
        "enableSubtitles": False,
        "minimaxModel": "speech-2.8-hd",
        "emotion": "happy",
        "sceneCount": 10,
        "copyCharCount": 120,
        "copyCharCountMode": "within",
        "copyDraftMode": "full",
        "mediaWidth": 1080,
        "mediaHeight": 1920,
        "imageAspectRatio": "custom",
        "subtitleStyle": {
            "mode": "ass",
            "preset": "cinema-soft",
            "fontFamily": "BrandFont",
            "fontPath": "/tmp/fonts/BrandFont.ttf",
            "fontSize": 58,
            "primaryColor": "#F8FAFC",
            "accentColor": "#FFD43B",
            "outlineColor": "#111111",
            "backColor": "#000000",
            "outlineWidth": 4,
            "shadow": 1,
            "marginV": 160,
            "alignment": 2,
            "maxCharsPerLine": 12,
            "maxLines": 2,
            "animation": "fade",
            "segmentMode": "sentence",
        },
    }


def _fallback_preset():
    preset = _preset_payload("当前保存配置")
    preset["id"] = "quick-create-default"
    return preset


@pytest.mark.asyncio
async def test_quick_create_presets_can_create_update_set_default_and_delete(monkeypatch, tmp_path):
    preset_path = tmp_path / "quick_create_presets.json"
    monkeypatch.setattr(workbench_support, "QUICK_CREATE_PRESETS_PATH", preset_path)
    monkeypatch.setattr(workbench.config_manager, "save_quick_create_config", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workbench_support, "_preset_from_config", lambda *_args, **_kwargs: _fallback_preset())

    created_response = await workbench.save_preset(_preset_payload("小红书竖屏口播"))
    created = created_response["preset"]

    assert created["id"] != "quick-create-default"
    assert created_response["defaultPresetId"] == created["id"]
    assert created_response["preset"]["name"] == "小红书竖屏口播"
    assert created_response["presets"] == [created]

    listed_response = await workbench.list_presets()
    assert listed_response["preset"]["id"] == created["id"]
    assert listed_response["defaultPresetId"] == created["id"]

    updated_response = await workbench.update_preset(
        created["id"],
        {**created, "name": "产品发布竖屏", "sceneCount": 8, "copyCharCountMode": "around"},
    )
    assert updated_response["preset"]["name"] == "产品发布竖屏"
    assert updated_response["preset"]["sceneCount"] == 8
    assert updated_response["preset"]["copyCharCountMode"] == "around"

    second_response = await workbench.save_preset(_preset_payload("科技感横屏宣传片"))
    second = second_response["preset"]
    default_response = await workbench.set_default_preset(second["id"])
    assert default_response["defaultPresetId"] == second["id"]
    assert default_response["preset"]["name"] == "科技感横屏宣传片"

    deleted_response = await workbench.delete_preset(second["id"])
    assert deleted_response["defaultPresetId"] == created["id"]
    assert [preset["id"] for preset in deleted_response["presets"]] == [created["id"]]

    saved_data = json.loads(preset_path.read_text(encoding="utf-8"))
    assert saved_data["defaultPresetId"] == created["id"]
    assert saved_data["presets"][0]["name"] == "产品发布竖屏"


@pytest.mark.asyncio
async def test_quick_create_preset_preserves_global_workbench_fields(monkeypatch, tmp_path):
    preset_path = tmp_path / "quick_create_presets.json"
    monkeypatch.setattr(workbench_support, "QUICK_CREATE_PRESETS_PATH", preset_path)
    monkeypatch.setattr(workbench.config_manager, "save_quick_create_config", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workbench_support, "_preset_from_config", lambda *_args, **_kwargs: _fallback_preset())

    response = await workbench.save_preset(_preset_payload())
    preset = response["preset"]

    assert preset["sceneCount"] == 10
    assert preset["copyCharCount"] == 120
    assert preset["copyCharCountMode"] == "within"
    assert preset["copyDraftMode"] == "full"
    assert preset["mediaWidth"] == 1080
    assert preset["mediaHeight"] == 1920
    assert preset["imageAspectRatio"] == "custom"
    assert preset["subtitleStyle"]["preset"] == "cinema-soft"
    assert preset["subtitleStyle"]["fontPath"] == "/tmp/fonts/BrandFont.ttf"
    assert preset["subtitleStyle"]["segmentMode"] == "sentence"
    assert "aiTopic" not in preset
    assert "copyDraft" not in preset
    assert "previewTtsText" not in preset


def test_quick_create_config_from_preset_includes_subtitle_style():
    preset = workbench._normalize_preset(_preset_payload())

    config = workbench._quick_create_config_from_preset(preset)

    assert config["subtitle_style"]["preset"] == "cinema-soft"
    assert config["subtitle_style"]["fontSize"] == 58
    assert config["subtitle_style"]["fontPath"] == "/tmp/fonts/BrandFont.ttf"


def test_quick_create_preset_normalizes_subtitle_values_at_storage_boundary():
    payload = _preset_payload()
    payload["subtitleStyle"].update(
        {
            "fontSize": 300,
            "outlineWidth": -3,
            "marginV": 900,
            "maxCharsPerLine": 2,
            "maxLines": 9,
            "highlightScale": 250,
            "backgroundOpacity": -10,
        }
    )

    preset = workbench._normalize_preset(payload)

    assert preset["subtitleStyle"]["fontSize"] == 120
    assert preset["subtitleStyle"]["outlineWidth"] == 0
    assert preset["subtitleStyle"]["marginV"] == 600
    assert preset["subtitleStyle"]["maxCharsPerLine"] == 4
    assert preset["subtitleStyle"]["maxLines"] == 4
    assert preset["subtitleStyle"]["highlightScale"] == 180
    assert preset["subtitleStyle"]["backgroundOpacity"] == 0


@pytest.mark.asyncio
async def test_prompt_prefix_save_updates_selected_quick_create_preset(monkeypatch, tmp_path):
    preset_path = tmp_path / "quick_create_presets.json"
    monkeypatch.setattr(workbench_support, "QUICK_CREATE_PRESETS_PATH", preset_path)
    monkeypatch.setattr(workbench.config_manager, "save_quick_create_config", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workbench.config_manager, "set_prompt_prefix", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(workbench_support, "_preset_from_config", lambda *_args, **_kwargs: _fallback_preset())

    created_response = await workbench.save_preset(_preset_payload("竖屏默认工作台"))
    created = created_response["preset"]

    response = await workbench.save_prompt_prefix(
        workbench.PromptPrefixSaveRequest(
            promptPrefix="soft cinematic light, warm product texture",
            presetId=created["id"],
        )
    )

    saved_data = json.loads(preset_path.read_text(encoding="utf-8"))
    assert response["preset"]["id"] == created["id"]
    assert response["preset"]["promptPrefix"] == "soft cinematic light, warm product texture"
    assert saved_data["presets"][0]["id"] == created["id"]
    assert saved_data["presets"][0]["promptPrefix"] == "soft cinematic light, warm product texture"
