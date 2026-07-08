# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""Compatibility endpoints for the React workbench.

These endpoints keep the new UI thin while delegating real work to the
existing FastAPI and Pixelle-Video services.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from api.dependencies import PixelleVideoDep
from api.routers.configuration import test_service
from api.schemas.configuration import ServiceTestRequest
from pixelle_video.config import config_manager
from pixelle_video.utils.content_generators import (
    generate_image_prompts,
    generate_narrations_from_topic,
)
from pixelle_video.utils.os_util import resource_exists

router = APIRouter(tags=["React Workbench"])


class GenerateScriptRequest(BaseModel):
    """Current React workbench script-generation request."""

    topic: str = Field(..., min_length=1)
    sceneCount: int = Field(5, ge=1, le=20)
    splitType: str = "line"


class TestConnectionRequest(BaseModel):
    """Current React workbench service-test request."""

    service: str
    config: dict[str, Any] = Field(default_factory=dict)


def _frontend_tts_mode(mode: str | None) -> str:
    if mode == "minimax":
        return "minimax"
    if mode == "comfyui":
        return "comfyui"
    return "local"


def _backend_tts_mode(mode: str | None) -> str:
    if mode == "minimax":
        return "minimax"
    if mode == "comfyui":
        return "comfyui"
    return "edge"


def _is_frontend_placeholder(value: str | None) -> bool:
    return bool(value and value.startswith(("bgm-", "tpl-", "runninghub-", "bizyair-", "comfyui-")))


def _template_type_from_path(template_path: str | None) -> str:
    filename = (template_path or "").split("/")[-1]
    if filename.startswith("video_"):
        return "video"
    if filename.startswith("static_"):
        return "static"
    return "image"


def _preset_from_config(name: str = "当前保存配置") -> dict[str, Any]:
    comfyui = config_manager.get_comfyui_config()
    quick_create = config_manager.get("quick_create", {})
    tts = comfyui.get("tts", {})
    tts_mode = tts.get("inference_mode", "local")

    if tts_mode == "minimax":
        voice = tts.get("minimax", {}).get("voice_id", "")
        speed = tts.get("minimax", {}).get("speed", 1.0)
    else:
        voice = tts.get("local", {}).get("voice", "")
        speed = tts.get("local", {}).get("speed", 1.0)

    workflow = (
        comfyui.get("video", {}).get("default_workflow")
        or comfyui.get("image", {}).get("default_workflow")
        or ""
    )
    bgm_path = quick_create.get("bgm_path")
    bgm = (
        bgm_path
        if bgm_path
        and not _is_frontend_placeholder(bgm_path)
        and resource_exists("bgm", bgm_path)
        else "bgm-none"
    )
    bgm_volume = int(float(quick_create.get("bgm_volume") or 0.2) * 100)

    return {
        "id": "quick-create-default",
        "name": name,
        "ttsMode": _backend_tts_mode(tts_mode),
        "voice": voice,
        "speed": speed,
        "workflow": workflow,
        "bgm": bgm,
        "bgmVolume": bgm_volume,
        "promptPrefix": (
            comfyui.get("video", {}).get("prompt_prefix")
            or comfyui.get("image", {}).get("prompt_prefix")
            or ""
        ),
        "splitType": "line",
        "template": config_manager.get("template", {}).get("default_template"),
        "viewMode": "pure-image"
        if config_manager.get("template", {}).get("composition_mode") == "plain_image"
        else "template",
        "enableMotion": config_manager.get("template", {}).get("image_motion_enabled", True),
        "enableSubtitles": config_manager.get("template", {}).get("subtitle_enabled", True),
        "minimaxModel": tts.get("minimax", {}).get("model"),
        "emotion": tts.get("minimax", {}).get("emotion"),
    }


def _quick_create_config_from_preset(preset: dict[str, Any]) -> dict[str, Any]:
    bgm = preset.get("bgm")
    bgm_path = None if not bgm or _is_frontend_placeholder(bgm) else bgm
    volume = preset.get("bgmVolume", 20)
    if volume > 1:
        volume = volume / 100
    volume = min(max(float(volume), 0.0), 0.5)

    workflow = preset.get("workflow")
    media_workflow = None if _is_frontend_placeholder(workflow) else workflow

    return {
        "tts_inference_mode": _frontend_tts_mode(preset.get("ttsMode")),
        "tts_voice": preset.get("voice"),
        "tts_speed": preset.get("speed"),
        "minimax_model": preset.get("minimaxModel"),
        "minimax_emotion": preset.get("emotion"),
        "media_workflow": media_workflow,
        "prompt_prefix": preset.get("promptPrefix", ""),
        "bgm_path": bgm_path,
        "bgm_volume": volume,
        "frame_template": preset.get("template"),
        "template_type": _template_type_from_path(preset.get("template")),
        "template_media_type": _template_type_from_path(preset.get("template")),
        "composition_mode": "plain_image"
        if preset.get("viewMode") == "pure-image"
        else "template",
        "image_motion_enabled": preset.get("enableMotion", True),
        "subtitle_enabled": preset.get("enableSubtitles", True),
    }


def _service_test_request(request: TestConnectionRequest) -> ServiceTestRequest:
    service_aliases = {
        "comfy": "comfyui",
        "comfyui": "comfyui",
        "llm": "llm",
        "image_generation": "image_generation",
        "runninghub": "runninghub",
        "bizyair": "bizyair",
        "minimax": "minimax",
    }
    service = service_aliases.get(request.service)
    if not service:
        raise HTTPException(status_code=400, detail=f"Unsupported service: {request.service}")

    config = dict(request.config)
    normalized = {
        "api_key": config.get("api_key") or config.get("apiKey"),
        "base_url": config.get("base_url") or config.get("baseUrl"),
        "model": config.get("model"),
        "comfyui_url": config.get("comfyui_url") or config.get("url"),
        "comfyui_api_key": config.get("comfyui_api_key") or config.get("apiKey"),
        "runninghub_api_key": config.get("runninghub_api_key") or config.get("apiKey"),
        "bizyair_api_key": config.get("bizyair_api_key") or config.get("apiKey"),
        "minimax_api_key": config.get("minimax_api_key") or config.get("apiKey"),
    }
    return ServiceTestRequest(
        service=service,  # type: ignore[arg-type]
        config={key: value for key, value in normalized.items() if value},
    )


@router.get("/presets")
async def list_presets():
    """Return the saved quick-create preset in the shape expected by React."""
    preset = _preset_from_config()
    return {"success": True, "presets": [preset], "preset": preset}


@router.post("/presets")
async def save_preset(preset: dict[str, Any]):
    """Persist the reusable quick-create configuration from React."""
    try:
        config_manager.save_quick_create_config(_quick_create_config_from_preset(preset))
        saved = _preset_from_config(preset.get("name") or "当前保存配置")
        return {"success": True, "preset": saved, "presets": [saved]}
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/test-connection")
async def test_connection(request: TestConnectionRequest):
    """Compatibility route for the React settings panel."""
    return await test_service(_service_test_request(request))


@router.post("/generate-script")
async def generate_script(request: GenerateScriptRequest, pixelle_video: PixelleVideoDep):
    """Generate editable scene narration and visual prompts through the real LLM."""
    try:
        llm_config = config_manager.get_llm_config()
        if not (
            llm_config.get("api_key")
            and llm_config.get("base_url")
            and llm_config.get("model")
        ):
            raise HTTPException(
                status_code=400,
                detail="LLM 配置未保存。请在系统设置中测试 LLM 连接，成功后配置会自动保存。",
            )

        narrations = await generate_narrations_from_topic(
            llm_service=pixelle_video.llm,
            topic=request.topic,
            n_scenes=request.sceneCount,
            min_words=5,
            max_words=40,
        )
        image_prompts = await generate_image_prompts(
            llm_service=pixelle_video.llm,
            narrations=narrations,
            min_words=20,
            max_words=80,
        )
        data = [
            {
                "id": index + 1,
                "ttsText": narration,
                "visualPrompt": image_prompts[index] if index < len(image_prompts) else "",
            }
            for index, narration in enumerate(narrations)
        ]
        return {"success": True, "data": data}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
