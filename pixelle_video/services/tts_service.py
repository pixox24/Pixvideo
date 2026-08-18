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
TTS (Text-to-Speech) Service - Supports local, ComfyUI, MiniMax, and Mimo inference
"""

import asyncio
import base64
import binascii
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from loguru import logger

from pixelle_video.services.comfy_base_service import ComfyBaseService
from pixelle_video.tts_voices import speed_to_rate
from pixelle_video.utils.tts_util import edge_tts


def _async_http_client(**kwargs):
    """httpx client that ignores a dead Windows system proxy.

    When a local proxy (e.g. Clash on 127.0.0.1:19828) is still enabled in
    Internet Settings but the client is not running, httpx's default
    ``trust_env=True`` fails every cloud TTS call with connection refused.
    Cloud MiniMax / MiMo endpoints do not need that proxy.
    """
    import httpx

    kwargs.setdefault("trust_env", False)
    return httpx.AsyncClient(**kwargs)


class TTSService(ComfyBaseService):
    """
    TTS (Text-to-Speech) service - Workflow-based
    
    Uses ComfyKit to execute TTS workflows.
    
    Usage:
        # Use default workflow
        audio_path = await pixelle_video.tts(text="Hello, world!")
        
        # Use specific workflow
        audio_path = await pixelle_video.tts(
            text="你好，世界！",
            workflow="tts_edge.json"
        )
        
        # List available workflows
        workflows = pixelle_video.tts.list_workflows()
    """
    
    WORKFLOW_PREFIX = "tts_"
    DEFAULT_WORKFLOW = None  # No hardcoded default, must be configured
    WORKFLOWS_DIR = "workflows"
    
    def __init__(self, config: dict, core=None):
        """
        Initialize TTS service
        
        Args:
            config: Full application config dict
            core: PixelleVideoCore instance (for accessing shared ComfyKit)
        """
        super().__init__(config, service_name="tts", core=core)
        # When callers pass the TTS subsection directly (unit tests), do not
        # hot-reload from the global config_manager — that would overwrite
        # intentional test fixtures with the developer's config.yaml.
        self._direct_config = False
        # Unit tests and direct service usage may pass the TTS subsection
        # instead of the full app config. Keep full-config behavior unchanged.
        if not self.config and any(
            key in config for key in ("inference_mode", "local", "comfyui", "minimax", "mimo", "qwen_audio", "default_workflow")
        ):
            self.config = config
            self._direct_config = True
        if not self.config.get("default_workflow"):
            nested_default_workflow = self.config.get("comfyui", {}).get("default_workflow")
            if nested_default_workflow:
                self.config["default_workflow"] = nested_default_workflow

    def _refresh_config_from_manager(self) -> None:
        """
        Reload TTS subsection from config_manager.

        Advanced Settings can update API keys after the process starts. The
        service used to keep a one-shot snapshot from initialize(), so MiMo /
        MiniMax keys saved later never became visible until restart.
        """
        if self._direct_config:
            return
        try:
            from pixelle_video.config import config_manager

            live = config_manager.get_comfyui_config().get("tts")
            if isinstance(live, dict) and live:
                self.config = live
        except Exception as exc:
            logger.debug(f"TTS config hot-reload skipped: {exc}")
    
    
    async def __call__(
        self,
        text: str,
        workflow: Optional[str] = None,
        # ComfyUI connection (optional overrides)
        comfyui_url: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        minimax_api_key: Optional[str] = None,
        mimo_api_key: Optional[str] = None,
        qwen_audio_api_key: Optional[str] = None,
        # TTS parameters
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        # Inference mode override
        inference_mode: Optional[str] = None,
        # Output path
        output_path: Optional[str] = None,
        **params
    ) -> str:
        """
        Generate speech using local Edge TTS, ComfyUI workflow, or MiniMax API
        
        Args:
            text: Text to convert to speech
            workflow: Workflow filename (for ComfyUI mode, default: from config)
            comfyui_url: ComfyUI URL (optional, overrides config)
            runninghub_api_key: RunningHub API key (optional, overrides config)
            minimax_api_key: MiniMax API key (optional, overrides config/env)
            voice: Voice ID (for local mode: Edge TTS voice ID; for ComfyUI: workflow-specific; for MiniMax: voice_id)
            speed: Speech speed multiplier (1.0 = normal, >1.0 = faster, <1.0 = slower)
            inference_mode: Override inference mode ("local", "comfyui", or "minimax", default: from config)
            output_path: Custom output path (auto-generated if None)
            **params: Additional workflow parameters
        
        Returns:
            Generated audio file path
        
        Examples:
            # Local inference (Edge TTS)
            audio_path = await pixelle_video.tts(
                text="Hello, world!",
                inference_mode="local",
                voice="zh-CN-YunjianNeural",
                speed=1.2
            )
            
            # ComfyUI inference
            audio_path = await pixelle_video.tts(
                text="你好，世界！",
                inference_mode="comfyui",
                workflow="runninghub/tts_edge.json"
            )
        """
        # Pick up API keys / mode changes saved after process start.
        self._refresh_config_from_manager()

        # Determine inference mode (param > config)
        # Frontend uses "edge"; normalize to backend "local".
        raw_mode = inference_mode or self.config.get("inference_mode", "local")
        mode = str(raw_mode or "local").strip().lower()
        if mode in {"edge", "local"}:
            mode = "local"
        elif mode not in {"comfyui", "minimax", "mimo", "qwen_audio"}:
            mode = "local"
        
        # Route to appropriate implementation
        if mode == "local":
            return await self._call_local_tts(
                text=text,
                voice=voice,
                speed=speed,
                output_path=output_path
            )
        elif mode == "minimax":
            return await self._call_minimax_tts(
                text=text,
                api_key=minimax_api_key,
                voice=voice,
                speed=speed,
                output_path=output_path,
                **params
            )
        elif mode == "mimo":
            return await self._call_mimo_tts(
                text=text,
                api_key=mimo_api_key,
                voice=voice,
                speed=speed,
                output_path=output_path,
                **params
            )
        elif mode == "qwen_audio":
            return await self._call_qwen_audio_tts(
                text=text, api_key=qwen_audio_api_key, voice=voice,
                speed=speed, output_path=output_path, **params
            )
        else:  # comfyui
            # 1. Resolve workflow (returns structured info)
            workflow_info = self._resolve_workflow(workflow=workflow)
            
            # 2. Execute ComfyUI workflow
            return await self._call_comfyui_workflow(
                workflow_info=workflow_info,
                text=text,
                comfyui_url=comfyui_url,
                runninghub_api_key=runninghub_api_key,
                voice=voice,
                speed=speed,
                output_path=output_path,
                **params
            )
    
    async def _call_local_tts(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Generate speech using local Edge TTS
        
        Args:
            text: Text to convert to speech
            voice: Edge TTS voice ID (default: from config)
            speed: Speech speed multiplier (default: from config)
            output_path: Custom output path (auto-generated if None)
        
        Returns:
            Generated audio file path
        """
        # Get config defaults
        local_config = self.config.get("local", {})
        
        # Determine voice and speed (param > config)
        final_voice = voice or local_config.get("voice", "zh-CN-YunjianNeural")
        final_speed = speed if speed is not None else local_config.get("speed", 1.2)
        
        # Convert speed to rate parameter
        rate = speed_to_rate(final_speed)
        
        logger.info(f"🎙️  Using local Edge TTS: voice={final_voice}, speed={final_speed}x (rate={rate})")
        
        # Generate output path if not provided
        if not output_path:
            # Generate unique filename
            unique_id = uuid.uuid4().hex
            output_path = f"output/{unique_id}.mp3"
            
            # Ensure output directory exists
            Path("output").mkdir(parents=True, exist_ok=True)
        
        # Call Edge TTS
        try:
            await edge_tts(
                text=text,
                voice=final_voice,
                rate=rate,
                output_path=output_path
            )
            from pixelle_video.utils.tts_audio_postprocess import postprocess_tts_clip

            await asyncio.to_thread(postprocess_tts_clip, output_path)
            logger.info(f"✅ Generated audio (local Edge TTS): {output_path}")
            return output_path
        
        except Exception as e:
            logger.error(f"Local TTS generation error: {e}")
            raise

    def _resolve_minimax_api_key(self, api_key: Optional[str] = None) -> str:
        minimax_config = self.config.get("minimax", {})
        final_api_key = (
            api_key
            or os.getenv("MINIMAX_API_KEY")
            or self._load_dotenv_value("MINIMAX_API_KEY")
            or minimax_config.get("api_key")
            or ""
        )
        if not final_api_key.strip():
            raise ValueError(
                "MiniMax API key is not configured. "
                "Please set it in Advanced Settings or MINIMAX_API_KEY."
            )
        return final_api_key.strip()

    def _resolve_mimo_api_key(self, api_key: Optional[str] = None) -> str:
        mimo_config = self.config.get("mimo", {})
        final_api_key = (
            api_key
            or os.getenv("MIMO_API_KEY")
            or self._load_dotenv_value("MIMO_API_KEY")
            or mimo_config.get("api_key")
            or ""
        )
        if not final_api_key.strip():
            raise ValueError(
                "Mimo API key is not configured. "
                "Please set it in Advanced Settings or MIMO_API_KEY."
            )
        return final_api_key.strip()

    def _resolve_qwen_audio_api_key(self, api_key: Optional[str] = None) -> str:
        config = self.config.get("qwen_audio", {})
        value = api_key or os.getenv("DASHSCOPE_API_KEY") or self._load_dotenv_value("DASHSCOPE_API_KEY") or config.get("api_key") or ""
        if not str(value).strip():
            raise ValueError("DashScope API key is not configured. Please set it in Advanced Settings or DASHSCOPE_API_KEY.")
        return str(value).strip()

    async def _call_qwen_audio_tts(self, text: str, api_key: Optional[str] = None,
                                   voice: Optional[str] = None, speed: Optional[float] = None,
                                   output_path: Optional[str] = None, **params) -> str:
        """Generate speech with DashScope Qwen TTS multimodal generation."""
        import httpx

        config = self.config.get("qwen_audio", {})
        key = self._resolve_qwen_audio_api_key(api_key)
        model = params.get("qwen_audio_model") or config.get("model", "qwen3-tts-flash")
        final_voice = voice or config.get("voice_id", "Cherry")
        language = params.get("qwen_audio_language_type") or config.get("language_type", "Chinese")
        endpoint = params.get("qwen_audio_endpoint") or config.get("endpoint", "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation")
        output_path = output_path or f"output/{uuid.uuid4().hex}.mp3"
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        parameters = {"voice": final_voice, "language_type": language, "response_format": params.get("qwen_audio_format", "mp3")}
        if speed is not None:
            parameters["rate"] = speed
        payload = {"model": model, "input": {"text": text}, "parameters": parameters}
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        try:
            async with _async_http_client(timeout=params.get("qwen_audio_timeout", 120.0)) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            raise Exception(f"Qwen Audio TTS HTTP error: {exc.response.status_code} - {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise Exception(f"Qwen Audio TTS request failed: {exc}") from exc
        except ValueError as exc:
            raise Exception(f"Qwen Audio TTS returned invalid JSON: {exc}") from exc

        output = body.get("output") if isinstance(body, dict) else None
        audio_value = output.get("audio") if isinstance(output, dict) else None
        audio_value = audio_value or (body.get("audio") if isinstance(body, dict) else None)
        if not audio_value:
            raise Exception(f"Qwen Audio TTS response did not include audio: {body.get('message') or body.get('code') or 'unknown error'}")
        if isinstance(audio_value, dict):
            audio_value = audio_value.get("url") or audio_value.get("data") or audio_value.get("base64")
        if isinstance(audio_value, str) and audio_value.startswith(("http://", "https://")):
            async with _async_http_client(timeout=params.get("qwen_audio_timeout", 120.0)) as client:
                audio_response = await client.get(audio_value)
                audio_response.raise_for_status()
                audio_bytes = audio_response.content
        elif isinstance(audio_value, str):
            try:
                if "," in audio_value and audio_value.startswith("data:"):
                    audio_value = audio_value.split(",", 1)[1]
                audio_bytes = base64.b64decode(audio_value, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise Exception("Qwen Audio TTS returned invalid base64 audio") from exc
        elif isinstance(audio_value, (bytes, bytearray)):
            audio_bytes = bytes(audio_value)
        else:
            raise Exception("Qwen Audio TTS returned unsupported audio data")
        output_file.write_bytes(audio_bytes)
        from pixelle_video.utils.tts_audio_postprocess import postprocess_tts_clip
        await asyncio.to_thread(postprocess_tts_clip, output_path)
        return output_path

    def _load_dotenv_value(self, key: str) -> Optional[str]:
        env_path = Path(".env")
        if not env_path.exists():
            return None

        try:
            lines = env_path.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            logger.warning(f"Failed to read .env file: {e}")
            return None

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            env_key, env_value = stripped.split("=", 1)
            if env_key.strip() != key:
                continue
            value = env_value.strip()
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {"'", '"'}
            ):
                value = value[1:-1]
            return value.strip() or None
        return None

    async def _call_minimax_tts(
        self,
        text: str,
        api_key: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        output_path: Optional[str] = None,
        **params
    ) -> str:
        """
        Generate speech using MiniMax synchronous T2A HTTP API.

        MiniMax non-streaming hex output is decoded and saved locally so the
        existing duration probing and video assembly pipeline can keep using
        file paths, just like local Edge TTS.
        """
        import httpx

        minimax_config = self.config.get("minimax", {})
        final_api_key = self._resolve_minimax_api_key(api_key)
        final_model = params.get("minimax_model") or minimax_config.get("model", "speech-2.8-turbo")
        final_voice = voice or params.get("minimax_voice_id") or minimax_config.get("voice_id", "male-qn-qingse")
        final_speed = speed if speed is not None else minimax_config.get("speed", 1.0)
        final_vol = params.get("minimax_vol", minimax_config.get("vol", 1.0))
        final_pitch = params.get("minimax_pitch", minimax_config.get("pitch", 0))
        final_emotion = params.get("minimax_emotion")
        if final_emotion is None:
            final_emotion = minimax_config.get("emotion")
        if final_emotion == "":
            final_emotion = None

        if not output_path:
            unique_id = uuid.uuid4().hex
            output_path = f"output/{unique_id}.mp3"

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        voice_setting = {
            "voice_id": final_voice,
            "speed": final_speed,
            "vol": final_vol,
            "pitch": final_pitch,
        }
        if final_emotion:
            voice_setting["emotion"] = final_emotion

        # Prefer sentence-level timestamps for subtitle burn-in sync.
        subtitle_enable = params.get("subtitle_enable", minimax_config.get("subtitle_enable", True))
        subtitle_type = params.get("subtitle_type", minimax_config.get("subtitle_type", "sentence"))
        if subtitle_type not in {"sentence", "word", "word_streaming"}:
            subtitle_type = "sentence"

        payload = {
            "model": final_model,
            "text": text,
            "stream": False,
            "voice_setting": voice_setting,
            "audio_setting": {
                "sample_rate": params.get("minimax_sample_rate", minimax_config.get("sample_rate", 32000)),
                "bitrate": params.get("minimax_bitrate", minimax_config.get("bitrate", 128000)),
                "format": params.get("minimax_format", minimax_config.get("format", "mp3")),
                "channel": params.get("minimax_channel", minimax_config.get("channel", 1)),
            },
            "subtitle_enable": bool(subtitle_enable),
            "subtitle_type": subtitle_type,
            "output_format": "hex",
        }

        endpoint = params.get("minimax_endpoint") or minimax_config.get(
            "endpoint",
            "https://api.minimaxi.com/v1/t2a_v2"
        )
        headers = {
            "Authorization": f"Bearer {final_api_key}",
            "Content-Type": "application/json",
        }

        logger.info(f"🎙️  Using MiniMax TTS: model={final_model}, voice={final_voice}, speed={final_speed}x")

        try:
            async with _async_http_client(timeout=params.get("minimax_timeout", 120.0)) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
                response.raise_for_status()
                response_json = response.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"MiniMax TTS HTTP error: {e.response.status_code} - {e.response.text}") from e
        except httpx.HTTPError as e:
            raise Exception(f"MiniMax TTS request failed: {e}") from e
        except ValueError as e:
            raise Exception(f"MiniMax TTS returned invalid JSON: {e}") from e

        trace_id = response_json.get("trace_id", "")
        base_resp = response_json.get("base_resp") or {}
        status_code = base_resp.get("status_code")
        status_msg = base_resp.get("status_msg", "")
        if status_code not in (None, 0):
            raise Exception(
                f"MiniMax TTS failed: status_code={status_code}, "
                f"status_msg={status_msg}, trace_id={trace_id}"
            )

        data = response_json.get("data")
        if not isinstance(data, dict) or not data.get("audio"):
            response_keys = ", ".join(sorted(response_json.keys()))
            raise Exception(
                "MiniMax TTS response did not include audio "
                f"(trace_id={trace_id}, response_keys={response_keys})"
            )

        try:
            audio_bytes = bytes.fromhex(data["audio"])
        except (TypeError, ValueError, binascii.Error) as e:
            raise Exception(f"MiniMax TTS returned invalid hex audio (trace_id={trace_id}): {e}") from e

        output_file.write_bytes(audio_bytes)

        # Persist subtitle timestamps when MiniMax returns them (URL or inline).
        await self._save_minimax_alignment(data, output_path, params)
        from pixelle_video.utils.tts_audio_postprocess import postprocess_tts_clip

        await asyncio.to_thread(postprocess_tts_clip, output_path)

        extra_info = response_json.get("extra_info") or {}
        audio_length_ms = extra_info.get("audio_length")
        if audio_length_ms:
            logger.info(f"✅ Generated audio (MiniMax): {output_path} ({audio_length_ms}ms, trace_id={trace_id})")
        else:
            logger.info(f"✅ Generated audio (MiniMax): {output_path} (trace_id={trace_id})")
        return output_path

    async def _save_minimax_alignment(
        self,
        data: dict,
        output_path: str,
        params: dict,
    ) -> None:
        """Download/parse MiniMax subtitle timestamps and write a sidecar JSON."""
        from pixelle_video.services.subtitle_alignment import (
            parse_alignment_payload,
            save_alignment,
        )

        raw_payload = data.get("subtitle") or data.get("subtitles") or data.get("subtitle_data")
        subtitle_file = data.get("subtitle_file")

        try:
            if not raw_payload and subtitle_file:
                import httpx

                timeout = params.get("minimax_timeout", 120.0)
                async with _async_http_client(timeout=timeout) as client:
                    response = await client.get(str(subtitle_file))
                    response.raise_for_status()
                    content_type = (response.headers.get("content-type") or "").lower()
                    if "json" in content_type or str(subtitle_file).endswith(".json"):
                        raw_payload = response.json()
                    else:
                        # Some MiniMax variants return JSON text body without content-type.
                        try:
                            raw_payload = response.json()
                        except ValueError:
                            raw_payload = json.loads(response.text)

            if raw_payload is None:
                return

            cues = parse_alignment_payload(raw_payload)
            if not cues:
                logger.debug("MiniMax subtitle payload produced no alignment cues")
                return
            sidecar = save_alignment(output_path, cues)
            logger.info(f"📝 Saved MiniMax subtitle alignment ({len(cues)} cues): {sidecar}")
        except Exception as exc:
            logger.warning(f"Failed to save MiniMax subtitle alignment: {exc}")

    async def _call_mimo_tts(
        self,
        text: str,
        api_key: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        output_path: Optional[str] = None,
        **params
    ) -> str:
        """
        Generate speech using the Xiaomi MiMo chat-completions TTS API.

        MiMo returns base64-encoded audio in ``choices[0].message.audio.data``.
        The audio is decoded and saved locally so the existing duration probing
        and video assembly pipeline can keep using file paths.
        """
        import httpx

        mimo_config = self.config.get("mimo", {})
        final_api_key = self._resolve_mimo_api_key(api_key)
        final_model = str(params.get("mimo_model") or mimo_config.get("model", "mimo-v2.5-tts")).strip()
        # Reject MiniMax model IDs accidentally routed here (common when both
        # minimaxModel and mimoModel exist on the same project payload).
        if final_model.startswith("speech-") or final_model.lower().startswith("speech"):
            logger.warning(
                "MiMo TTS received MiniMax model {!r}; falling back to mimo-v2.5-tts",
                final_model,
            )
            final_model = "mimo-v2.5-tts"
        final_voice = voice or params.get("mimo_voice_id") or mimo_config.get("voice_id", "mimo_default")
        final_speed = speed if speed is not None else mimo_config.get("speed", 1.0)
        final_style = params.get("mimo_style")
        if final_style is None:
            final_style = mimo_config.get("style")
        if final_style == "":
            final_style = None

        # MiMo models differ in how voice is specified:
        # - mimo-v2.5-tts: preset voice via audio.voice
        # - mimo-v2.5-tts-voicedesign: natural-language description in user message;
        #   audio.voice is forbidden (API returns 400 Param Incorrect)
        # - mimo-v2.5-tts-voiceclone: reference audio cloning (not fully wired here)
        model_lower = final_model.lower()
        is_voice_design = "voicedesign" in model_lower or "voice-design" in model_lower
        is_voice_clone = "voiceclone" in model_lower or "voice-clone" in model_lower

        if is_voice_design and not (final_style and str(final_style).strip()):
            raise ValueError(
                "MiMo voice design 模式需要填写「自然语言风格指令」"
                "（作为音色描述，例如：年轻女声，清亮温柔，语速适中）"
            )

        if not output_path:
            unique_id = uuid.uuid4().hex
            output_path = f"output/{unique_id}.wav"

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Target text goes in the assistant message; optional style / voice-design
        # guidance goes in the user message.
        messages = []
        if final_style:
            messages.append({"role": "user", "content": final_style})
        elif is_voice_design:
            # Should be unreachable due to the guard above; keep for safety.
            messages.append({"role": "user", "content": "自然清晰的中文旁白音色"})
        messages.append({"role": "assistant", "content": text})

        audio_params: dict = {"format": "wav"}
        if is_voice_design:
            # Official API: voice design rejects audio.voice entirely.
            pass
        elif is_voice_clone:
            # Clone mode uses reference audio rather than preset voice IDs.
            # If only a voice id is provided, omit it to avoid invalid params;
            # callers should pass reference audio via dedicated params later.
            ref_audio = params.get("mimo_ref_audio") or params.get("ref_audio")
            if ref_audio:
                audio_params["voice"] = final_voice
                # Keep room for future ref-audio payload fields.
                params = {**params, "mimo_ref_audio": ref_audio}
            # Without ref audio, still avoid sending unsupported preset voices if empty.
            elif final_voice and final_voice not in {"mimo_default", ""}:
                audio_params["voice"] = final_voice
        else:
            # Standard TTS: preset built-in voices.
            if final_voice:
                audio_params["voice"] = final_voice

        payload = {
            "model": final_model,
            "messages": messages,
            "audio": audio_params,
        }

        endpoint = params.get("mimo_endpoint") or mimo_config.get(
            "endpoint",
            "https://api.xiaomimimo.com/v1/chat/completions",
        )
        headers = {
            "Authorization": f"Bearer {final_api_key}",
            "Content-Type": "application/json",
        }

        logger.info(
            "🎙️  Using Mimo TTS: model={}, voice={}, style={!r}, speed={}x, voice_design={}",
            final_model,
            None if is_voice_design else final_voice,
            final_style,
            final_speed,
            is_voice_design,
        )

        try:
            async with _async_http_client(timeout=params.get("mimo_timeout", 120.0)) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
                response.raise_for_status()
                response_json = response.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"Mimo TTS HTTP error: {e.response.status_code} - {e.response.text}") from e
        except httpx.HTTPError as e:
            raise Exception(f"Mimo TTS request failed: {e}") from e
        except ValueError as e:
            raise Exception(f"Mimo TTS returned invalid JSON: {e}") from e

        choices = response_json.get("choices") or []
        if not choices:
            response_keys = ", ".join(sorted(response_json.keys()))
            raise Exception(
                "Mimo TTS response did not include choices "
                f"(response_keys={response_keys})"
            )
        message = choices[0].get("message") or {}
        audio_data = (message.get("audio") or {}).get("data")
        if not audio_data:
            raise Exception("Mimo TTS response did not include audio data")

        try:
            audio_bytes = base64.b64decode(audio_data)
        except (TypeError, ValueError, binascii.Error) as e:
            raise Exception(f"Mimo TTS returned invalid base64 audio: {e}") from e

        output_file.write_bytes(audio_bytes)
        from pixelle_video.utils.tts_audio_postprocess import postprocess_tts_clip

        await asyncio.to_thread(postprocess_tts_clip, output_path)
        logger.info(f"✅ Generated audio (Mimo): {output_path}")
        return output_path

    async def _call_comfyui_workflow(
        self,
        workflow_info: dict,
        text: str,
        comfyui_url: Optional[str] = None,
        runninghub_api_key: Optional[str] = None,
        voice: Optional[str] = None,
        speed: float = 1.0,
        output_path: Optional[str] = None,
        **params
    ) -> str:
        """
        Generate speech using ComfyUI workflow
        
        Args:
            workflow_info: Workflow info dict from _resolve_workflow()
            text: Text to convert to speech
            comfyui_url: ComfyUI URL
            runninghub_api_key: RunningHub API key
            voice: Voice ID (workflow-specific)
            speed: Speech speed multiplier (workflow-specific)
            output_path: Custom output path (downloads if URL returned)
            **params: Additional workflow parameters
        
        Returns:
            Generated audio file path (local if output_path provided, otherwise URL)
        """
        logger.info(f"🎙️  Using workflow: {workflow_info['key']}")
        
        # 1. Build workflow parameters (ComfyKit config is now managed by core)
        workflow_params = {"text": text}
        
        # Add optional TTS parameters (only if explicitly provided and not None)
        if voice is not None:
            workflow_params["voice"] = voice
        if speed is not None and speed != 1.0:
            workflow_params["speed"] = speed
        
        # Add any additional parameters
        workflow_params.update(params)
        
        logger.debug(f"Workflow parameters: {workflow_params}")
        
        # 3. Execute workflow using shared ComfyKit instance from core
        try:
            # Get shared ComfyKit instance (lazy initialization + config hot-reload)
            kit = await self.core._get_or_create_comfykit()
            
            # Determine what to pass to ComfyKit based on source
            if workflow_info["source"] == "runninghub" and "workflow_id" in workflow_info:
                # RunningHub: pass workflow_id
                workflow_input = workflow_info["workflow_id"]
                logger.info(f"Executing RunningHub TTS workflow: {workflow_input}")
            else:
                # Selfhost: pass file path
                workflow_input = workflow_info["path"]
                logger.info(f"Executing selfhost TTS workflow: {workflow_input}")
            
            result = await kit.execute(workflow_input, workflow_params)
            
            # 4. Handle result
            if result.status != "completed":
                error_msg = result.msg or "Unknown error"
                logger.error(f"TTS generation failed: {error_msg}")
                raise Exception(f"TTS generation failed: {error_msg}")
            
            # ComfyKit result can have audio files in different output types
            # Try to get audio file path from result
            audio_path = None
            
            # Check for audio files in result.audios (if available)
            if hasattr(result, 'audios') and result.audios:
                audio_path = result.audios[0]
                logger.debug(f"✅ Found audio in result.audios: {audio_path}")
            # Check for files in result.files
            elif hasattr(result, 'files') and result.files:
                audio_path = result.files[0]
                logger.debug(f"✅ Found audio in result.files: {audio_path}")
            # Check in outputs dictionary
            elif hasattr(result, 'outputs') and result.outputs:
                logger.debug(f"Searching for audio file in result.outputs: {result.outputs}")
                # Try to find audio file in outputs
                for key, value in result.outputs.items():
                    if isinstance(value, str) and any(value.endswith(ext) for ext in ['.mp3', '.wav', '.flac']):
                        audio_path = value
                        logger.debug(f"✅ Found audio in result.outputs[{key}]: {audio_path}")
                        break
            
            if not audio_path:
                logger.error("No audio file generated")
                logger.error("❌ Result analysis:")
                logger.error(f"   - result.audios: {getattr(result, 'audios', 'NOT_FOUND')}")
                logger.error(f"   - result.files: {getattr(result, 'files', 'NOT_FOUND')}")
                logger.error(f"   - result.outputs: {getattr(result, 'outputs', 'NOT_FOUND')}")
                logger.error(f"   - Full __dict__: {result.__dict__}")
                raise Exception("No audio file generated by workflow")
            
            # If output_path provided and audio_path is URL, download to local
            if output_path and audio_path.startswith(('http://', 'https://')):
                import os

                import httpx
                
                # Ensure parent directory exists
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                logger.info(f"Downloading audio from {audio_path} to {output_path}")
                async with _async_http_client() as client:
                    response = await client.get(audio_path)
                    response.raise_for_status()
                    
                    with open(output_path, 'wb') as f:
                        f.write(response.content)
                
                logger.info(f"✅ Generated audio (ComfyUI): {output_path}")
                return output_path
            
            logger.info(f"✅ Generated audio (ComfyUI): {audio_path}")
            return audio_path
        
        except Exception as e:
            logger.error(f"TTS generation error: {e}")
            raise
