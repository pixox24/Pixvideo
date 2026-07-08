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
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


class ImageGenerationConfigPayload(BaseModel):
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


class ComfyUIConfigPayload(BaseModel):
    comfyui_url: Optional[str] = None
    comfyui_api_key: Optional[str] = None
    runninghub_api_key: Optional[str] = None
    runninghub_concurrent_limit: Optional[int] = Field(default=None, ge=1, le=10)
    runninghub_instance_type: Optional[str] = None
    bizyair_api_key: Optional[str] = None
    minimax_api_key: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    llm: Optional[LLMConfigPayload] = None
    image_generation: Optional[ImageGenerationConfigPayload] = None
    comfyui: Optional[ComfyUIConfigPayload] = None


class ServiceTestRequest(BaseModel):
    service: Literal["llm", "image_generation", "comfyui", "runninghub", "bizyair", "minimax"]
    config: dict[str, Any] = Field(default_factory=dict)


class QuickCreatePresetRequest(BaseModel):
    name: Optional[str] = None
    config: dict[str, Any]


class APIResponse(BaseModel):
    success: bool = True
    message: str = "Success"
