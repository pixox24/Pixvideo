# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Configuration Manager - Singleton pattern

Provides unified access to configuration with automatic validation.
"""
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .loader import load_config_dict, save_config_dict
from .schema import PixelleVideoConfig


class ConfigManager:
    """
    Configuration Manager (Singleton)
    
    Provides unified access to configuration with automatic validation.
    """
    _instance: Optional['ConfigManager'] = None
    
    def __new__(cls, config_path: str = "config.yaml"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, config_path: str = "config.yaml"):
        # Only initialize once
        if hasattr(self, '_initialized'):
            return
        
        self.config_path = Path(config_path)
        self.config: PixelleVideoConfig = self._load()
        self._initialized = True
    
    def _load(self) -> PixelleVideoConfig:
        """Load configuration from file"""
        data = load_config_dict(str(self.config_path))
        config = PixelleVideoConfig(**data)
        
        # Validate template path exists
        self._validate_template(config.template.default_template)
        
        return config
    
    def _validate_template(self, template_path: str):
        """Validate that the configured template exists"""
        from pixelle_video.utils.template_util import resolve_template_path
        
        try:
            # Try to resolve the template path
            resolved_path = resolve_template_path(template_path)
            logger.debug(f"Template validation passed: {template_path} -> {resolved_path}")
        except FileNotFoundError as e:
            logger.warning(
                f"Configured default template '{template_path}' not found. "
                f"Will fall back to '1080x1920/default.html' if needed. Error: {e}"
            )
    
    def reload(self):
        """Reload configuration from file"""
        self.config = self._load()
        logger.info("Configuration reloaded")
    
    def save(self):
        """Save current configuration to file"""
        save_config_dict(self.config.to_dict(), str(self.config_path))
    
    def update(self, updates: dict):
        """
        Update configuration with new values
        
        Args:
            updates: Dictionary of updates (e.g., {"llm": {"api_key": "xxx"}})
        """
        current = self.config.to_dict()
        
        # Deep merge
        def deep_merge(base: dict, updates: dict) -> dict:
            for key, value in updates.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    deep_merge(base[key], value)
                else:
                    base[key] = value
            return base
        
        merged = deep_merge(current, updates)
        self.config = PixelleVideoConfig(**merged)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like access (for backward compatibility)"""
        return self.config.to_dict().get(key, default)
    
    def validate(self) -> bool:
        """Validate configuration completeness"""
        return self.config.validate_required()
    
    def get_llm_config(self) -> dict:
        """Get LLM configuration as dict"""
        return {
            "api_key": self.config.llm.api_key,
            "base_url": self.config.llm.base_url,
            "model": self.config.llm.model,
        }

    def get_image_generation_config(self) -> dict:
        """Get OpenAI-compatible image generation configuration as dict."""
        return {
            "api_key": self.config.image_generation.api_key,
            "base_url": self.config.image_generation.base_url,
            "model": self.config.image_generation.model,
        }
    
    def set_llm_config(self, api_key: str, base_url: str, model: str):
        """Set LLM configuration"""
        self.update({
            "llm": {
                "api_key": api_key,
                "base_url": base_url,
                "model": model,
            }
        })

    def set_image_generation_config(
        self,
        api_key: str,
        base_url: str,
        model: str,
    ):
        """Set OpenAI-compatible image generation configuration."""
        self.update({
            "image_generation": {
                "api_key": api_key,
                "base_url": base_url,
                "model": model,
            }
        })
    
    def get_comfyui_config(self) -> dict:
        """Get ComfyUI configuration as dict"""
        return {
            "comfyui_url": self.config.comfyui.comfyui_url,
            "comfyui_api_key": self.config.comfyui.comfyui_api_key,
            "runninghub_api_key": self.config.comfyui.runninghub_api_key,
            "runninghub_concurrent_limit": self.config.comfyui.runninghub_concurrent_limit,
            "runninghub_instance_type": self.config.comfyui.runninghub_instance_type,
            "bizyair_api_key": self.config.comfyui.bizyair_api_key,
            "tts": {
                "default_workflow": self.config.comfyui.tts.default_workflow,
                "inference_mode": self.config.comfyui.tts.inference_mode,
                "local": {
                    "voice": self.config.comfyui.tts.local.voice,
                    "speed": self.config.comfyui.tts.local.speed,
                },
                "comfyui": {
                    "default_workflow": self.config.comfyui.tts.comfyui.default_workflow,
                },
                "minimax": {
                    "api_key": self.config.comfyui.tts.minimax.api_key,
                    "model": self.config.comfyui.tts.minimax.model,
                    "voice_id": self.config.comfyui.tts.minimax.voice_id,
                    "speed": self.config.comfyui.tts.minimax.speed,
                    "vol": self.config.comfyui.tts.minimax.vol,
                    "pitch": self.config.comfyui.tts.minimax.pitch,
                    "emotion": self.config.comfyui.tts.minimax.emotion,
                },
            },
            "image": {
                "default_workflow": self.config.comfyui.image.default_workflow,
                "prompt_prefix": self.config.comfyui.image.prompt_prefix,
            },
            "video": {
                "default_workflow": self.config.comfyui.video.default_workflow,
                "prompt_prefix": self.config.comfyui.video.prompt_prefix,
            }
        }
    
    def set_comfyui_config(
        self, 
        comfyui_url: Optional[str] = None,
        comfyui_api_key: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        runninghub_concurrent_limit: Optional[int] = None,
        runninghub_instance_type: Optional[str] = None,
        bizyair_api_key: Optional[str] = None,
        minimax_api_key: Optional[str] = None,
    ):
        """Set ComfyUI global configuration"""
        updates = {}
        if comfyui_url is not None:
            updates["comfyui_url"] = comfyui_url
        if comfyui_api_key is not None:
            updates["comfyui_api_key"] = comfyui_api_key
        if runninghub_api_key is not None:
            updates["runninghub_api_key"] = runninghub_api_key
        if runninghub_concurrent_limit is not None:
            updates["runninghub_concurrent_limit"] = runninghub_concurrent_limit
        if runninghub_instance_type is not None:
            # Empty string means disable (treat as None for storage)
            updates["runninghub_instance_type"] = runninghub_instance_type if runninghub_instance_type else None
        if bizyair_api_key is not None:
            updates["bizyair_api_key"] = bizyair_api_key
        if minimax_api_key is not None:
            updates.setdefault("tts", {}).setdefault("minimax", {})["api_key"] = minimax_api_key
        
        if updates:
            self.update({"comfyui": updates})

    def set_prompt_prefix(self, prompt_prefix: str):
        """Persist the shared prompt prefix for image and video generation."""
        value = prompt_prefix or ""
        self.update({
            "comfyui": {
                "image": {"prompt_prefix": value},
                "video": {"prompt_prefix": value},
            }
        })
        self.save()

    def save_quick_create_config(self, video_params: dict):
        """
        Persist reusable Quick Create settings from the current UI state.

        One-off content such as prompts, titles, uploaded files, and preview values
        is intentionally ignored.
        """
        tts_mode = video_params.get("tts_inference_mode") or self.config.comfyui.tts.inference_mode
        composition_mode = video_params.get("composition_mode") or self.config.template.composition_mode
        frame_template = video_params.get("frame_template") or self.config.template.default_template
        template_type = video_params.get("template_type") or self.config.template.template_type
        media_type = video_params.get("template_media_type") or template_type
        if composition_mode == "plain_image":
            media_config_key = "image"
        elif media_type in {"image", "video"}:
            media_config_key = media_type
        else:
            media_config_key = None

        comfyui_updates: dict[str, Any] = {
            "tts": {
                "inference_mode": tts_mode,
            }
        }

        if tts_mode == "local":
            local_updates = {}
            if video_params.get("tts_voice"):
                local_updates["voice"] = video_params["tts_voice"]
            if video_params.get("tts_speed") is not None:
                local_updates["speed"] = video_params["tts_speed"]
            if local_updates:
                comfyui_updates["tts"]["local"] = local_updates
        elif tts_mode == "comfyui":
            if video_params.get("tts_workflow"):
                comfyui_updates["tts"]["comfyui"] = {
                    "default_workflow": video_params["tts_workflow"],
                }
        elif tts_mode == "minimax":
            minimax_updates = {}
            if video_params.get("minimax_model"):
                minimax_updates["model"] = video_params["minimax_model"]
            if video_params.get("tts_voice"):
                minimax_updates["voice_id"] = video_params["tts_voice"]
            if video_params.get("tts_speed") is not None:
                minimax_updates["speed"] = video_params["tts_speed"]
            if "minimax_emotion" in video_params:
                minimax_updates["emotion"] = video_params.get("minimax_emotion")
            if minimax_updates:
                comfyui_updates["tts"]["minimax"] = minimax_updates

        if media_config_key:
            media_updates = {}
            if video_params.get("media_workflow"):
                media_updates["default_workflow"] = video_params["media_workflow"]
            if "prompt_prefix" in video_params:
                media_updates["prompt_prefix"] = video_params.get("prompt_prefix") or ""
            if media_updates:
                comfyui_updates[media_config_key] = media_updates

        bgm_volume = video_params.get("bgm_volume")
        if bgm_volume is None:
            bgm_volume = self.config.quick_create.bgm_volume

        subtitle_updates: dict[str, Any] = {}
        if "subtitle_style" in video_params:
            subtitle_updates["default_style"] = video_params.get("subtitle_style") or {}

        updates = {
            "comfyui": comfyui_updates,
            "template": {
                "default_template": frame_template,
                "template_type": template_type,
                "composition_mode": composition_mode,
                "image_motion_enabled": video_params.get(
                    "image_motion_enabled",
                    self.config.template.image_motion_enabled,
                ),
                "subtitle_enabled": video_params.get(
                    "subtitle_enabled",
                    self.config.template.subtitle_enabled,
                ),
                "image_motion_mode": video_params.get(
                    "image_motion_mode",
                    self.config.template.image_motion_mode,
                ),
                "image_motion_strength": video_params.get(
                    "image_motion_strength",
                    self.config.template.image_motion_strength,
                ),
                "image_fit_mode": video_params.get(
                    "image_fit_mode",
                    self.config.template.image_fit_mode,
                ),
            },
            "quick_create": {
                "view_mode": video_params.get("view_mode") or self.config.quick_create.view_mode,
                "bgm_path": video_params.get("bgm_path"),
                "bgm_volume": bgm_volume,
            },
        }
        if subtitle_updates:
            updates["subtitle"] = subtitle_updates

        self.update(updates)
        self.save()
