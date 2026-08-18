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
TTS API schemas
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class TTSSynthesizeRequest(BaseModel):
    """TTS synthesis request"""
    text: str = Field(..., description="Text to synthesize")
    inference_mode: Optional[Literal["local", "comfyui", "minimax", "mimo", "qwen_audio"]] = Field(
        None,
        description="TTS inference mode override. Use 'local' for Edge TTS."
    )
    workflow: Optional[str] = Field(
        None, 
        description="TTS workflow key (e.g., 'runninghub/tts_edge.json' or 'selfhost/tts_edge.json'). If not specified, uses default workflow from config."
    )
    ref_audio: Optional[str] = Field(
        None, 
        description="Reference audio path for voice cloning (optional). Can be a local file path or URL."
    )
    voice_id: Optional[str] = Field(
        None, 
        description="Voice ID (deprecated, use workflow instead)"
    )
    speed: Optional[float] = Field(
        None,
        ge=0.5,
        le=2.0,
        description="Speech speed multiplier"
    )
    minimax_model: Optional[str] = Field(
        None,
        description="MiniMax TTS model override"
    )
    minimax_emotion: Optional[str] = Field(
        None,
        description="MiniMax TTS emotion override"
    )
    mimo_model: Optional[str] = Field(
        None,
        description="MiMo TTS model override"
    )
    mimo_style: Optional[str] = Field(
        None,
        description="MiMo natural-language style instruction (optional)"
    )
    qwen_audio_model: Optional[str] = Field(None, description="Qwen Audio TTS model override")
    qwen_audio_language_type: Optional[str] = Field(None, description="Qwen Audio language type override")
    
    class Config:
        json_schema_extra = {
            "example": {
                "text": "Hello, welcome to Pixelle-Video!",
                "inference_mode": "local",
                "workflow": "runninghub/tts_edge.json",
                "voice_id": "zh-CN-YunjianNeural",
                "speed": 1.1,
                "minimax_model": "speech-2.8-turbo",
                "minimax_emotion": None,
                "mimo_model": "mimo-v2.5-tts",
                "mimo_style": None,
                "ref_audio": None
            }
        }


class TTSSynthesizeResponse(BaseModel):
    """TTS synthesis response"""
    success: bool = True
    message: str = "Success"
    audio_path: str = Field(..., description="Path to generated audio file")
    duration: float = Field(..., description="Audio duration in seconds")
