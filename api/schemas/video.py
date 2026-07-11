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
Video generation API schemas
"""

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class SubtitleStyle(BaseModel):
    """Styled subtitle rendering options."""

    mode: Literal["drawtext", "ass", "hyperframes"] = Field("ass", description="Subtitle renderer mode")
    preset: str = Field("short-video-bold", description="Subtitle visual preset")
    fontFamily: Optional[str] = Field(None, description="Font family display name")
    fontPath: Optional[str] = Field(None, description="Absolute or project-relative font path")
    fontSize: int = Field(52, ge=12, le=120, description="Subtitle font size in pixels")
    primaryColor: str = Field("#FFFFFF", description="Primary text color")
    accentColor: str = Field("#FFD43B", description="Accent/highlight color")
    outlineColor: str = Field("#000000", description="Outline color")
    backColor: str = Field("#000000", description="Background box color")
    outlineWidth: int = Field(3, ge=0, le=12, description="Outline width")
    shadow: int = Field(0, ge=0, le=12, description="ASS shadow depth")
    marginV: int = Field(120, ge=0, le=600, description="Vertical margin from aligned edge")
    alignment: int = Field(2, ge=1, le=9, description="ASS alignment code")
    maxCharsPerLine: int = Field(14, ge=4, le=40, description="Max CJK chars per subtitle line")
    maxLines: int = Field(2, ge=1, le=4, description="Max lines per subtitle segment")
    animation: Literal["none", "fade", "pop", "word-pop"] = Field(
        "fade",
        description="Subtitle animation",
    )
    segmentMode: Literal["line", "sentence", "phrase"] = Field("phrase", description="Subtitle segmentation")
    highlightWords: list[str] = Field(default_factory=list, description="Manual highlighted words")
    highlightStyle: Literal["accent", "pop", "badge"] = Field(
        "accent",
        description="Highlighted phrase appearance",
    )
    highlightScale: int = Field(125, ge=100, le=180, description="Highlighted phrase scale percentage")
    backgroundOpacity: int = Field(72, ge=0, le=100, description="Caption-box background opacity percentage")


class VideoGenerateRequest(BaseModel):
    """Video generation request"""

    # === Pipeline ===
    pipeline: str = Field("standard", description="Backend pipeline key")
    
    # === Input ===
    text: str = Field(..., description="Source text for video generation")
    
    # === Processing Mode ===
    mode: Literal["generate", "fixed"] = Field(
        "generate",
        description="Processing mode: 'generate' (AI generates narrations) or 'fixed' (use text as-is)"
    )
    split_mode: Literal["paragraph", "line", "sentence"] = Field(
        "paragraph",
        description="Fixed-script split mode"
    )
    
    # === Optional Title ===
    title: Optional[str] = Field(None, description="Video title (auto-generated if not provided)")
    
    # === Basic Config ===
    n_scenes: Optional[int] = Field(5, ge=1, le=30, description="Number of scenes (only used in 'generate' mode, ignored in 'fixed' mode)")
    
    # === TTS Parameters ===
    tts_inference_mode: Literal["local", "comfyui", "minimax"] = Field(
        "local",
        description="TTS inference mode"
    )
    tts_voice: Optional[str] = Field(None, description="Local or MiniMax voice ID")
    tts_speed: Optional[float] = Field(None, ge=0.5, le=2.0, description="TTS speed")
    tts_workflow: Optional[str] = Field(
        None, 
        description="TTS workflow key (e.g., 'runninghub/tts_edge.json'). If not specified, uses default workflow from config."
    )
    ref_audio: Optional[str] = Field(
        None, 
        description="Reference audio path for voice cloning (optional)"
    )
    voice_id: Optional[str] = Field(
        None, 
        description="(Deprecated) TTS voice ID for legacy compatibility"
    )
    minimax_model: Optional[str] = Field(None, description="MiniMax TTS model")
    minimax_emotion: Optional[str] = Field(None, description="MiniMax TTS emotion")
    
    # === LLM Parameters ===
    min_narration_words: int = Field(5, ge=1, le=100, description="Min narration words")
    max_narration_words: int = Field(20, ge=1, le=200, description="Max narration words")
    min_image_prompt_words: int = Field(30, ge=10, le=100, description="Min image prompt words")
    max_image_prompt_words: int = Field(60, ge=10, le=200, description="Max image prompt words")
    
    # === Media Parameters ===
    # Note: media_width and media_height are auto-determined from template meta tags
    media_workflow: Optional[str] = Field(None, description="Custom media workflow (image or video)")
    media_width: Optional[int] = Field(None, ge=1, description="Media width override")
    media_height: Optional[int] = Field(None, ge=1, description="Media height override")
    
    # === Video Parameters ===
    video_fps: int = Field(30, ge=15, le=60, description="Video FPS")
    
    # === Frame Template (determines video size) ===
    frame_template: Optional[str] = Field(
        None, 
        description="HTML template path with size (e.g., '1080x1920/default.html'). Video size is auto-determined from template."
    )
    template_type: Optional[str] = Field(None, description="Template type: static, image, or video")
    template_media_type: Optional[str] = Field(None, description="Template media type")
    
    # === Template Custom Parameters ===
    template_params: Optional[Dict[str, Any]] = Field(
        None,
        description="Custom template parameters (e.g., {'accent_color': '#ff0000', 'background': 'url'}). "
                    "Available parameters depend on the template. Use GET /api/templates/{template_path}/params to discover them."
    )
    
    # === Image Style ===
    prompt_prefix: Optional[str] = Field(None, description="Image style prefix")

    # === Composition ===
    composition_mode: Literal["template", "plain_image"] = Field("template", description="Composition mode")
    image_motion_enabled: bool = Field(False, description="Enable image motion in plain image mode")
    subtitle_enabled: bool = Field(True, description="Enable subtitles")
    subtitle_style: Optional[SubtitleStyle] = Field(None, description="Styled subtitle rendering options")
    image_motion_mode: str = Field("auto", description="Image motion mode")
    image_motion_strength: str = Field("subtle", description="Image motion strength")
    image_fit_mode: str = Field("cover", description="Image fit mode")
    
    # === BGM ===
    bgm_path: Optional[str] = Field(None, description="Background music path")
    bgm_volume: float = Field(0.3, ge=0.0, le=1.0, description="BGM volume (0.0-1.0)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "text": "Atomic Habits teaches us that small changes compound over time to produce remarkable results.",
                "mode": "generate",
                "n_scenes": 5,
                "frame_template": "1080x1920/image_default.html",
                "template_params": {
                    "accent_color": "#3498db",
                    "background": "https://example.com/custom-bg.jpg"
                },
                "title": "The Power of Atomic Habits"
            }
        }


class VideoGenerateResponse(BaseModel):
    """Video generation response (synchronous)"""
    success: bool = True
    message: str = "Success"
    video_url: str = Field(..., description="URL to access generated video")
    duration: float = Field(..., description="Video duration in seconds")
    file_size: int = Field(..., description="File size in bytes")


class VideoGenerateAsyncResponse(BaseModel):
    """Video generation async response"""
    success: bool = True
    message: str = "Task created successfully"
    task_id: str = Field(..., description="Task ID for tracking progress")
