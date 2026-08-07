# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""Configuration endpoints for the React workbench."""

from __future__ import annotations

import requests
from fastapi import APIRouter, HTTPException
from loguru import logger

from api.schemas.configuration import (
    ConfigUpdateRequest,
    QuickCreatePresetRequest,
    ServiceTestRequest,
)
from pixelle_video.config import config_manager

router = APIRouter(prefix="/config", tags=["Configuration"])


def _mask_secret(value: str | None) -> str:
    """Return a non-sensitive display value for secret fields."""
    if not value:
        return ""
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}...{value[-4:]}"


def _sanitized_config() -> dict:
    """Build sanitized config for frontend display."""
    llm = config_manager.get_llm_config()
    image_generation = config_manager.get_image_generation_config()
    comfyui = config_manager.get_comfyui_config()
    minimax = comfyui.get("tts", {}).get("minimax", {})

    return {
        "success": True,
        "configured": config_manager.validate(),
        "llm": {
            "provider": llm.get("provider", "gemini"),
            "api_key_set": bool(llm.get("api_key")),
            "api_key_masked": _mask_secret(llm.get("api_key")),
            "base_url": llm.get("base_url", ""),
            "model": llm.get("model", ""),
        },
        "image_generation": {
            "api_key_set": bool(image_generation.get("api_key")),
            "api_key_masked": _mask_secret(image_generation.get("api_key")),
            "base_url": image_generation.get("base_url", ""),
            "model": image_generation.get("model", ""),
        },
        "comfyui": {
            "comfyui_url": comfyui.get("comfyui_url", ""),
            "comfyui_api_key_set": bool(comfyui.get("comfyui_api_key")),
            "comfyui_api_key_masked": _mask_secret(comfyui.get("comfyui_api_key")),
            "runninghub_api_key_set": bool(comfyui.get("runninghub_api_key")),
            "runninghub_api_key_masked": _mask_secret(comfyui.get("runninghub_api_key")),
            "runninghub_concurrent_limit": comfyui.get("runninghub_concurrent_limit", 1),
            "runninghub_instance_type": comfyui.get("runninghub_instance_type"),
            "bizyair_api_key_set": bool(comfyui.get("bizyair_api_key")),
            "bizyair_api_key_masked": _mask_secret(comfyui.get("bizyair_api_key")),
            "minimax_api_key_set": bool(minimax.get("api_key")),
            "minimax_api_key_masked": _mask_secret(minimax.get("api_key")),
        },
        "quick_create": config_manager.get("quick_create", {}),
        "template": config_manager.get("template", {}),
        "service_status": {
            "llm": bool(llm.get("api_key") and llm.get("base_url") and llm.get("model")),
            "image_generation": bool(
                image_generation.get("api_key")
                and image_generation.get("base_url")
                and image_generation.get("model")
            ),
            "comfyui": bool(comfyui.get("comfyui_url")),
            "runninghub": bool(comfyui.get("runninghub_api_key")),
            "bizyair": bool(comfyui.get("bizyair_api_key")),
            "minimax": bool(minimax.get("api_key")),
        },
    }


@router.get("")
async def get_config():
    """Return sanitized backend configuration for the React workbench."""
    return _sanitized_config()


@router.put("")
async def update_config(request: ConfigUpdateRequest):
    """Persist system configuration."""
    try:
        if request.llm:
            current = config_manager.get_llm_config()
            if request.llm.provider is not None:
                config_manager.update({"llm": {"provider": request.llm.provider}})
            api_key = request.llm.api_key if request.llm.api_key is not None else current["api_key"]
            base_url = request.llm.base_url if request.llm.base_url is not None else current["base_url"]
            model = request.llm.model if request.llm.model is not None else current["model"]
            config_manager.set_llm_config(api_key, base_url, model)

        if request.image_generation:
            current = config_manager.get_image_generation_config()
            api_key = (
                request.image_generation.api_key
                if request.image_generation.api_key is not None
                else current["api_key"]
            )
            base_url = (
                request.image_generation.base_url
                if request.image_generation.base_url is not None
                else current["base_url"]
            )
            model = (
                request.image_generation.model
                if request.image_generation.model is not None
                else current["model"]
            )
            config_manager.set_image_generation_config(api_key, base_url, model)

        if request.comfyui:
            config_manager.set_comfyui_config(
                comfyui_url=request.comfyui.comfyui_url,
                comfyui_api_key=request.comfyui.comfyui_api_key,
                runninghub_api_key=request.comfyui.runninghub_api_key,
                runninghub_concurrent_limit=request.comfyui.runninghub_concurrent_limit,
                runninghub_instance_type=request.comfyui.runninghub_instance_type,
                bizyair_api_key=request.comfyui.bizyair_api_key,
                minimax_api_key=request.comfyui.minimax_api_key,
            )

        config_manager.save()
        return _sanitized_config()
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/test")
async def test_service(request: ServiceTestRequest):
    """Test one backend service configuration."""
    try:
        if request.service == "llm":
            from pixelle_video.utils.llm_util import test_llm_connection

            llm = config_manager.get_llm_config()
            api_key = request.config.get("api_key") or llm.get("api_key")
            base_url = request.config.get("base_url") or llm.get("base_url")
            model = request.config.get("model") or llm.get("model")
            success, message, model_count = test_llm_connection(api_key, base_url, model=model)
            return {
                "success": success,
                "message": message,
                "model_count": model_count,
            }

        if request.service == "comfyui":
            comfyui = config_manager.get_comfyui_config()
            url = request.config.get("comfyui_url") or comfyui.get("comfyui_url")
            response = requests.get(f"{url.rstrip('/')}/system_stats", timeout=5)
            return {
                "success": response.status_code == 200,
                "message": "ComfyUI connection successful"
                if response.status_code == 200
                else f"ComfyUI returned {response.status_code}",
            }

        if request.service == "image_generation":
            image_generation = config_manager.get_image_generation_config()
            api_key = request.config.get("api_key") or image_generation.get("api_key")
            base_url = request.config.get("base_url") or image_generation.get("base_url")
            model = request.config.get("model") or image_generation.get("model")
            missing = [
                name
                for name, value in {
                    "api_key": api_key,
                    "base_url": base_url,
                    "model": model,
                }.items()
                if not value
            ]
            return {
                "success": not missing,
                "message": "image_generation configuration is complete"
                if not missing
                else f"image_generation missing: {', '.join(missing)}",
            }

        key_names = {
            "runninghub": "runninghub_api_key",
            "bizyair": "bizyair_api_key",
            "minimax": "minimax_api_key",
        }
        key_name = key_names[request.service]
        key = request.config.get(key_name)
        if not key:
            comfyui = config_manager.get_comfyui_config()
            if request.service == "minimax":
                key = comfyui.get("tts", {}).get("minimax", {}).get("api_key")
            else:
                key = comfyui.get(key_name)
        return {
            "success": bool(key),
            "message": f"{request.service} API key is configured"
            if key
            else f"{request.service} API key is missing",
        }
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/presets")
async def get_quick_create_preset():
    """Return the saved reusable quick-create production defaults."""
    return {
        "success": True,
        "preset": {
            "id": "quick-create-default",
            "name": "Saved Quick Create Defaults",
            "config": {
                "quick_create": config_manager.get("quick_create", {}),
                "template": config_manager.get("template", {}),
                "comfyui": config_manager.get_comfyui_config(),
            },
        },
    }


@router.post("/presets")
async def save_quick_create_preset(request: QuickCreatePresetRequest):
    """Save reusable quick-create defaults."""
    try:
        config_manager.save_quick_create_config(request.config)
        return await get_quick_create_preset()
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
