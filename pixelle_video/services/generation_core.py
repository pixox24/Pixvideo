"""Shared single-scene generation helpers.

Used by the one-shot StandardPipeline path (via FrameProcessor) and the
resumable workbench path (via WorkbenchJobService). Persistence and
orchestration stay in those callers.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from loguru import logger

EDGE_TTS_FALLBACK = {
    "inference_mode": "local",
    "voice": "zh-CN-YunjianNeural",
    "speed": 1.0,
}


def compose_image_prompt(prompt: str, prefix: str = "") -> str:
    cleaned_prompt = str(prompt or "").strip()
    cleaned_prefix = str(prefix or "").strip()
    if cleaned_prefix and cleaned_prompt:
        return f"{cleaned_prefix}, {cleaned_prompt}"
    return cleaned_prefix or cleaned_prompt


async def synthesize_speech(
    core: Any,
    *,
    text: str,
    output_path: str,
    scene_id: str | None = None,
    fallback_on_comfyui: bool = True,
    **tts_kwargs: Any,
) -> str:
    """Run TTS and fall back to Edge when ComfyUI is unavailable.

    Returns the local audio path. Copies provider output onto ``output_path``
    when the provider writes a different file.
    """
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        result = await core.tts(
            text=text,
            output_path=str(dest),
            scene_id=scene_id,
            **tts_kwargs,
        )
    except Exception as exc:
        if fallback_on_comfyui and tts_kwargs.get("inference_mode") == "comfyui":
            logger.warning("ComfyUI TTS failed, falling back to Edge TTS: {}", exc)
            result = await core.tts(
                text=text,
                output_path=str(dest),
                scene_id=scene_id,
                **EDGE_TTS_FALLBACK,
            )
        else:
            raise

    if result and Path(str(result)).resolve() != dest.resolve() and Path(str(result)).is_file():
        shutil.copyfile(result, dest)
    if not dest.is_file():
        raise FileNotFoundError("TTS provider did not create an audio file")
    return str(dest)


async def generate_scene_image(
    core: Any,
    *,
    prompt: str,
    prefix: str = "",
    workflow: str | None = None,
    width: int,
    height: int,
    scene_id: str | None = None,
    use_api_image: bool = False,
    media_type: str = "image",
    **extra: Any,
) -> Any:
    """Call the media service with an optional style prefix."""
    params: dict[str, Any] = {
        "prompt": compose_image_prompt(prompt, prefix),
        "media_type": media_type,
        "width": width,
        "height": height,
        "use_api_image": use_api_image,
    }
    if workflow:
        params["workflow"] = workflow
    if scene_id:
        params["scene_id"] = scene_id
    params.update(extra)
    return await core.media(**params)
