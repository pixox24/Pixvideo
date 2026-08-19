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
Configuration schema with Pydantic models

Single source of truth for all configuration defaults and validation.
"""
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """LLM configuration"""
    provider: str = Field(default="gemini", description="LLM provider preset")
    api_key: str = Field(default="", description="LLM API Key")
    base_url: str = Field(default="", description="LLM API Base URL")
    model: str = Field(default="", description="LLM Model Name")


class ImageGenerationConfig(BaseModel):
    """OpenAI-compatible image generation API configuration."""
    api_key: str = Field(default="", description="Image generation API key")
    base_url: str = Field(default="https://img-cn.65535.space/v1", description="Image generation API base URL")
    model: str = Field(default="gpt-image-2", description="Image generation model name")


class VisionUnderstandingConfig(BaseModel):
    """OpenAI-compatible multimodal vision understanding configuration."""
    enabled: bool = Field(default=False, description="Enable reference-image style analysis")
    provider: str = Field(default="dashscope", description="Vision provider")
    api_key: str = Field(default="", description="Vision API key")
    base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        description="OpenAI-compatible vision API base URL",
    )
    model: str = Field(default="qwen3.7-plus", description="Primary vision model")
    fallback_model: str = Field(default="qwen3.7-flash", description="Fallback vision model")
    timeout_seconds: int = Field(default=60, ge=10, le=180)
    max_image_bytes: int = Field(default=10 * 1024 * 1024, ge=1_000_000)
    max_image_pixels: int = Field(default=16_000_000, ge=1_000_000)
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)


class TTSLocalConfig(BaseModel):
    """Local TTS configuration (Edge TTS)"""
    voice: str = Field(default="zh-CN-YunjianNeural", description="Edge TTS voice ID")
    speed: float = Field(default=1.2, ge=0.5, le=2.0, description="Speech speed multiplier (0.5-2.0)")


class TTSComfyUIConfig(BaseModel):
    """ComfyUI TTS configuration"""
    default_workflow: Optional[str] = Field(default=None, description="Default TTS workflow (optional)")


class TTSMiniMaxConfig(BaseModel):
    """MiniMax TTS API configuration"""
    api_key: str = Field(default="", description="MiniMax API Key")
    model: str = Field(default="speech-2.8-turbo", description="MiniMax speech model")
    voice_id: str = Field(default="male-qn-qingse", description="MiniMax voice ID")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech speed multiplier (0.5-2.0)")
    vol: float = Field(default=1.0, gt=0.0, le=10.0, description="Speech volume (0-10]")
    pitch: int = Field(default=0, ge=-12, le=12, description="Speech pitch (-12 to 12)")
    emotion: Optional[str] = Field(default=None, description="MiniMax emotion override (optional)")


class TTSMimoConfig(BaseModel):
    """MiMo TTS API configuration (Xiaomi MiMo-V2.5-TTS)"""
    api_key: str = Field(default="", description="MiMo API Key")
    model: str = Field(default="mimo-v2.5-tts", description="MiMo speech model")
    voice_id: str = Field(default="mimo_default", description="MiMo voice ID")
    style: str = Field(default="", description="MiMo natural-language style instruction (optional)")


class TTSQwenAudioConfig(BaseModel):
    """DashScope Qwen TTS configuration."""
    api_key: str = Field(default="", description="DashScope API Key")
    model: str = Field(default="qwen3-tts-flash", description="Qwen TTS model")
    voice_id: str = Field(default="Cherry", description="Qwen TTS voice ID")
    language_type: str = Field(default="Chinese", description="Qwen TTS language type")
    mode: str = Field(default="preset", description="Qwen voice mode: preset, instruct, design, or clone")
    instruction: str = Field(default="", description="Qwen natural-language voice instruction or design description")
    ref_audio: str = Field(default="", description="Qwen voice-cloning reference audio key")
    workspace_id: str = Field(default="", description="百炼业务空间 ID（Qwen-Audio-TTS 需要）")
    endpoint: str = Field(
        default="https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
        description="DashScope multimodal generation endpoint",
    )


class TTSSubConfig(BaseModel):
    """TTS-specific configuration (under comfyui.tts)"""
    inference_mode: str = Field(default="local", description="TTS inference mode: 'local', 'comfyui', 'minimax', 'mimo', or 'qwen_audio'")
    local: TTSLocalConfig = Field(default_factory=TTSLocalConfig, description="Local TTS (Edge TTS) configuration")
    comfyui: TTSComfyUIConfig = Field(default_factory=TTSComfyUIConfig, description="ComfyUI TTS configuration")
    minimax: TTSMiniMaxConfig = Field(default_factory=TTSMiniMaxConfig, description="MiniMax TTS API configuration")
    mimo: TTSMimoConfig = Field(default_factory=TTSMimoConfig, description="MiMo TTS API configuration")
    qwen_audio: TTSQwenAudioConfig = Field(default_factory=TTSQwenAudioConfig, description="Qwen Audio TTS configuration")
    
    # Backward compatibility: keep default_workflow at top level
    @property
    def default_workflow(self) -> Optional[str]:
        """Get default workflow (for backward compatibility)"""
        return self.comfyui.default_workflow


class ImageSubConfig(BaseModel):
    """Image-specific configuration (under comfyui.image)"""
    default_workflow: Optional[str] = Field(default=None, description="Default image workflow (optional)")
    prompt_prefix: str = Field(
        default="Minimalist black-and-white matchstick figure style illustration, clean lines, simple sketch style",
        description="Prompt prefix for all image generation"
    )


class VideoSubConfig(BaseModel):
    """Video-specific configuration (under comfyui.video)"""
    default_workflow: Optional[str] = Field(default=None, description="Default video workflow (optional)")
    prompt_prefix: str = Field(
        default="Minimalist black-and-white matchstick figure style illustration, clean lines, simple sketch style",
        description="Prompt prefix for all video generation"
    )


class ComfyUIConfig(BaseModel):
    """ComfyUI configuration (includes global settings and service-specific configs)"""
    comfyui_url: str = Field(default="http://127.0.0.1:8188", description="ComfyUI Server URL")
    comfyui_api_key: Optional[str] = Field(default=None, description="ComfyUI API Key (optional)")
    runninghub_api_key: Optional[str] = Field(default=None, description="RunningHub API Key (optional)")
    runninghub_concurrent_limit: int = Field(default=1, ge=1, le=10, description="RunningHub concurrent execution limit (1-10)")
    runninghub_instance_type: Optional[str] = Field(default=None, description="RunningHub instance type (optional, set to 'plus' for 48GB VRAM)")
    bizyair_api_key: Optional[str] = Field(default=None, description="BizyAir API Key (optional)")
    tts: TTSSubConfig = Field(default_factory=TTSSubConfig, description="TTS-specific configuration")
    image: ImageSubConfig = Field(default_factory=ImageSubConfig, description="Image-specific configuration")
    video: VideoSubConfig = Field(default_factory=VideoSubConfig, description="Video-specific configuration")


class TemplateConfig(BaseModel):
    """Template configuration"""
    default_template: str = Field(
        default="1080x1920/default.html",
        description="Default frame template path"
    )
    template_type: str = Field(default="image", description="Default template type")
    composition_mode: str = Field(default="template", description="Default composition mode")
    image_motion_enabled: bool = Field(default=True, description="Enable image motion in plain image mode")
    subtitle_enabled: bool = Field(default=True, description="Enable subtitles in plain image mode")
    image_motion_mode: str = Field(default="auto", description="Image motion mode")
    image_motion_strength: str = Field(default="subtle", description="Image motion strength")
    image_fit_mode: str = Field(default="cover", description="Image fit mode")


class QuickCreateConfig(BaseModel):
    """Quick Create reusable UI defaults"""
    custom_bgm_folder: Optional[str] = Field(default=None, description="User-selected custom BGM folder")
    bgm_path: Optional[str] = Field(default="default.mp3", description="Default BGM filename")
    bgm_volume: float = Field(default=0.2, ge=0.0, le=0.5, description="Default BGM volume")


class SubtitleConfig(BaseModel):
    """Subtitle rendering configuration"""
    custom_font_folder: Optional[str] = Field(default=None, description="User-selected custom subtitle font folder")
    npx_command: Optional[str] = Field(
        default=None,
        description="Optional absolute Node.js npx/npx.cmd path for dynamic subtitles",
    )
    default_style: Dict[str, Any] = Field(default_factory=dict, description="Default subtitle style")


class WorkbenchConfig(BaseModel):
    """Workbench project generation settings"""
    scene_concurrency: int = Field(
        default=6,
        ge=1,
        le=16,
        description="Max scenes generating media in parallel (1–16)",
    )


class PixelleVideoConfig(BaseModel):
    """Pixelle-Video main configuration"""
    project_name: str = Field(default="Pixelle-Video", description="Project name")
    llm: LLMConfig = Field(default_factory=LLMConfig)
    image_generation: ImageGenerationConfig = Field(default_factory=ImageGenerationConfig)
    vision_understanding: VisionUnderstandingConfig = Field(default_factory=VisionUnderstandingConfig)
    comfyui: ComfyUIConfig = Field(default_factory=ComfyUIConfig)
    template: TemplateConfig = Field(default_factory=TemplateConfig)
    quick_create: QuickCreateConfig = Field(default_factory=QuickCreateConfig)
    subtitle: SubtitleConfig = Field(default_factory=SubtitleConfig)
    workbench_dir: Optional[str] = Field(default=None, description="Workbench data directory override")
    workbench: WorkbenchConfig = Field(default_factory=WorkbenchConfig)
    
    def is_llm_configured(self) -> bool:
        """Check if LLM is properly configured"""
        return bool(
            self.llm.api_key and self.llm.api_key.strip() and
            self.llm.base_url and self.llm.base_url.strip() and
            self.llm.model and self.llm.model.strip()
        )
    
    def validate_required(self) -> bool:
        """Validate required configuration"""
        return self.is_llm_configured()
    
    def to_dict(self) -> dict:
        """Convert to dictionary (for backward compatibility)"""
        return self.model_dump()
