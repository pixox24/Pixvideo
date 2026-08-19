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
TTS (Text-to-Speech) endpoints
"""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.schemas.tts import (
    QwenVoiceDesignRequest,
    QwenVoiceDesignResponse,
    TTSSynthesizeRequest,
    TTSSynthesizeResponse,
)
from pixelle_video.utils.tts_util import get_audio_duration

router = APIRouter(prefix="/tts", tags=["Basic Services"])

_QWEN_DESIGN_MODEL = "qwen3-tts-vd-2026-01-26"
_QWEN_CLONE_MODEL = "qwen3-tts-vc-2026-01-22"
_QWEN_CLONE_EXTENSIONS = {".mp3", ".wav", ".m4a"}
_MAX_QWEN_CLONE_BYTES = 10 * 1024 * 1024


@router.get("/qwen/capabilities")
async def qwen_capabilities():
    """Return the supported Qwen model capabilities used by the director UI."""
    return {
        "success": True,
        "models": [
            {"id": "qwen3-tts-flash", "mode": "preset", "supports_instruction": False},
            {"id": "qwen3-tts-instruct-flash", "mode": "instruct", "supports_instruction": True},
            {"id": _QWEN_DESIGN_MODEL, "mode": "design", "supports_instruction": False},
            {"id": _QWEN_CLONE_MODEL, "mode": "clone", "supports_instruction": False},
            {"id": "qwen-audio-3.0-tts-flash", "mode": "preset", "supports_instruction": True, "requires_workspace_id": True},
            {"id": "qwen-audio-3.0-tts-plus", "mode": "preset", "supports_instruction": True, "requires_workspace_id": True},
        ],
        "notes": {
            "design": "先通过 voice-design 创建 voice ID，再合成；创建与合成必须使用同一模型。",
            "clone": "先通过 voice-clone 创建 voice ID，再合成；需要音频使用授权。",
        },
    }


@router.post("/qwen/voice-design", response_model=QwenVoiceDesignResponse)
async def qwen_voice_design(request: QwenVoiceDesignRequest, pixelle_video: PixelleVideoDep):
    """Create a reusable Qwen voice from a text description and return its voice ID."""
    import base64
    import httpx
    import uuid
    from pathlib import Path

    try:
        config = pixelle_video.tts.config.get("qwen_audio", {})
        key = pixelle_video.tts._resolve_qwen_audio_api_key(None)
        endpoint = config.get("design_endpoint") or "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"
        if request.target_model != _QWEN_DESIGN_MODEL:
            raise ValueError(f"Qwen 声音设计仅支持 {_QWEN_DESIGN_MODEL}")
        payload = {
            "model": "qwen-voice-design",
            "input": {
                "action": "create",
                "target_model": request.target_model,
                "preferred_name": request.preferred_name,
                "voice_prompt": request.voice_prompt,
                "preview_text": request.preview_text,
            },
            "parameters": {"sample_rate": 24000, "response_format": "wav"},
        }
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            body = response.json()
        output = body.get("output") or {}
        voice_id = output.get("voice") or output.get("voice_id")
        if not voice_id:
            raise ValueError(f"Qwen voice design response did not include voice ID: {body.get('message') or body.get('code') or 'unknown error'}")
        preview = output.get("preview_audio") or output.get("audio")
        preview_path = None
        if isinstance(preview, dict):
            preview = preview.get("data") or preview.get("url")
        if isinstance(preview, str) and preview.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
                audio_response = await client.get(preview)
                audio_response.raise_for_status()
                preview_bytes = audio_response.content
        elif isinstance(preview, str):
            if "," in preview and preview.startswith("data:"):
                preview = preview.split(",", 1)[1]
            preview_bytes = base64.b64decode(preview)
        else:
            preview_bytes = None
        if preview_bytes:
            preview_path = f"output/{uuid.uuid4().hex}_qwen_voice_preview.wav"
            Path(preview_path).parent.mkdir(parents=True, exist_ok=True)
            Path(preview_path).write_bytes(preview_bytes)
        return QwenVoiceDesignResponse(voice_id=str(voice_id), target_model=request.target_model, preview_audio_path=preview_path)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:1000]
        raise HTTPException(status_code=502, detail=f"Qwen voice design HTTP error {exc.response.status_code}: {detail}") from exc
    except Exception as exc:
        logger.error(f"Qwen voice design error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/qwen/voice-clone", response_model=QwenVoiceDesignResponse)
async def qwen_voice_clone(
    pixelle_video: PixelleVideoDep,
    file: UploadFile = File(...),
    preferred_name: str = Form(default="pixelle_voice"),
    target_model: str = Form(default=_QWEN_CLONE_MODEL),
    consent: bool = Form(...),
):
    """Create a Qwen3 cloned voice from an authorized 10-20 second audio sample."""
    import base64
    import httpx
    from pathlib import Path

    if not consent:
        raise HTTPException(status_code=422, detail="需要确认您拥有该参考音频及声音的合法使用授权")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in _QWEN_CLONE_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Qwen 音色克隆仅支持 MP3、WAV 或 M4A 参考音频")
    if target_model != _QWEN_CLONE_MODEL:
        raise HTTPException(status_code=422, detail=f"Qwen 音色克隆仅支持 {_QWEN_CLONE_MODEL}")
    try:
        audio_bytes = await file.read(_MAX_QWEN_CLONE_BYTES + 1)
        if not audio_bytes:
            raise HTTPException(status_code=422, detail="参考音频不能为空")
        if len(audio_bytes) > _MAX_QWEN_CLONE_BYTES:
            raise HTTPException(status_code=413, detail="参考音频不能超过 10 MB")
        mime_type = file.content_type or {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}[suffix]
        data_uri = f"data:{mime_type};base64,{base64.b64encode(audio_bytes).decode('ascii')}"
        key = pixelle_video.tts._resolve_qwen_audio_api_key(None)
        payload = {
            "model": "qwen-voice-enrollment",
            "input": {
                "action": "create",
                "target_model": target_model,
                "preferred_name": preferred_name.strip() or "pixelle_voice",
                "audio": {"data": data_uri},
            },
        }
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            response = await client.post(
                "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization",
                json=payload,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            response.raise_for_status()
            body = response.json()
        voice_id = (body.get("output") or {}).get("voice")
        if not voice_id:
            raise ValueError(f"Qwen voice clone response did not include voice ID: {body.get('message') or body.get('code') or 'unknown error'}")
        return QwenVoiceDesignResponse(voice_id=str(voice_id), target_model=target_model)
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Qwen voice clone HTTP error {exc.response.status_code}: {exc.response.text[:1000]}") from exc
    except Exception as exc:
        logger.error(f"Qwen voice clone error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await file.close()


@router.post("/synthesize", response_model=TTSSynthesizeResponse)
async def tts_synthesize(
    request: TTSSynthesizeRequest,
    pixelle_video: PixelleVideoDep
):
    """
    Text-to-Speech synthesis endpoint
    
    Convert text to speech audio using ComfyUI workflows.
    
    - **text**: Text to synthesize
    - **workflow**: TTS workflow key (optional, uses default if not specified)
    - **ref_audio**: Reference audio for voice cloning (optional)
    - **voice_id**: (Deprecated) Voice ID for legacy compatibility
    
    Returns path to generated audio file and duration.
    
    Examples:
    ```json
    {
        "text": "Hello, welcome to Pixelle-Video!",
        "workflow": "runninghub/tts_edge.json"
    }
    ```
    
    With voice cloning:
    ```json
    {
        "text": "Hello, this is a cloned voice",
        "workflow": "runninghub/tts_index2.json",
        "ref_audio": "path/to/reference.wav"
    }
    ```
    """
    try:
        logger.info(f"TTS synthesis request: {request.text[:50]}...")
        
        # Build TTS parameters
        tts_params = {"text": request.text}

        if request.inference_mode:
            tts_params["inference_mode"] = request.inference_mode
        
        # Add workflow if specified
        if request.workflow:
            tts_params["workflow"] = request.workflow
        
        # Add ref_audio if specified
        if request.ref_audio:
            tts_params["ref_audio"] = request.ref_audio
        
        # Legacy voice_id support (deprecated)
        if request.voice_id and (request.inference_mode == "local" or not request.workflow):
            tts_params["voice"] = request.voice_id

        if request.speed is not None:
            tts_params["speed"] = request.speed

        if request.minimax_model:
            tts_params["minimax_model"] = request.minimax_model
        if request.minimax_emotion:
            tts_params["minimax_emotion"] = request.minimax_emotion

        if request.mimo_model:
            tts_params["mimo_model"] = request.mimo_model
        if request.mimo_style:
            tts_params["mimo_style"] = request.mimo_style
        if request.qwen_audio_model:
            tts_params["qwen_audio_model"] = request.qwen_audio_model
        if request.qwen_audio_language_type:
            tts_params["qwen_audio_language_type"] = request.qwen_audio_language_type
        if request.qwen_audio_mode:
            tts_params["qwen_audio_mode"] = request.qwen_audio_mode
        if request.qwen_audio_instruction:
            tts_params["qwen_audio_instruction"] = request.qwen_audio_instruction
        if request.qwen_audio_ref_audio:
            tts_params["qwen_audio_ref_audio"] = request.qwen_audio_ref_audio
        
        # Call TTS service
        audio_path = await pixelle_video.tts(**tts_params)
        
        # Get audio duration
        duration = get_audio_duration(audio_path)
        
        return TTSSynthesizeResponse(
            audio_path=audio_path,
            duration=duration
        )
        
    except Exception as e:
        logger.error(f"TTS synthesis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
