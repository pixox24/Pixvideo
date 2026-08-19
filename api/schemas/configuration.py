# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""Configuration API schemas."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class LLMConfigPayload(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


class ImageGenerationConfigPayload(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


class VisionUnderstandingConfigPayload(BaseModel):
    enabled: Optional[bool] = None
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    fallback_model: Optional[str] = None
    timeout_seconds: Optional[int] = Field(default=None, ge=10, le=180)
    max_image_bytes: Optional[int] = Field(default=None, ge=1_000_000)
    max_image_pixels: Optional[int] = Field(default=None, ge=1_000_000)
    temperature: Optional[float] = Field(default=None, ge=0, le=1)


class ComfyUIConfigPayload(BaseModel):
    comfyui_url: Optional[str] = None
    comfyui_api_key: Optional[str] = None
    runninghub_api_key: Optional[str] = None
    runninghub_concurrent_limit: Optional[int] = Field(default=None, ge=1, le=10)
    runninghub_instance_type: Optional[str] = None
    bizyair_api_key: Optional[str] = None
    minimax_api_key: Optional[str] = None
    mimo_api_key: Optional[str] = None
    qwen_audio_api_key: Optional[str] = None
    qwen_audio_workspace_id: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    llm: Optional[LLMConfigPayload] = None
    image_generation: Optional[ImageGenerationConfigPayload] = None
    vision_understanding: Optional[VisionUnderstandingConfigPayload] = None
    comfyui: Optional[ComfyUIConfigPayload] = None


class ServiceTestRequest(BaseModel):
    service: Literal["llm", "image_generation", "vision_understanding", "comfyui", "runninghub", "bizyair", "minimax", "mimo", "qwen_audio"]
    config: dict[str, Any] = Field(default_factory=dict)


class QuickCreatePresetRequest(BaseModel):
    name: Optional[str] = None
    config: dict[str, Any]


class APIResponse(BaseModel):
    success: bool = True
    message: str = "Success"
