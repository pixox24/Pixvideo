# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0

"""Compatibility endpoints for the React workbench.

These endpoints keep the new UI thin while delegating real work to the
existing FastAPI and Pixelle-Video services.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from api.dependencies import PixelleVideoDep
from api.routers.configuration import test_service
from api.schemas.configuration import ServiceTestRequest
from pixelle_video.config import config_manager
from pixelle_video.services.subtitle_renderer import SUBTITLE_STYLE_DEFAULTS
from pixelle_video.utils.content_generators import (
    clean_narration_text,
    generate_image_prompts,
    generate_narrations_from_content,
    generate_narrations_from_topic,
    split_narration_script,
)
from pixelle_video.utils.os_util import resource_exists

router = APIRouter(tags=["React Workbench"])


class GenerateScriptRequest(BaseModel):
    """Current React workbench script-generation request."""

    topic: str = Field(..., min_length=1)
    sceneCount: int = Field(5, ge=1, le=100)
    splitType: str = "line"
    draftMode: str = "full"
    confirmedText: str | None = None
    # continuous | per_scene — continuous disables soft comma-expand so holds
    # do not inject mid-sentence pauses after clause-level splits.
    ttsDelivery: str | None = None


class GenerateCopyDraftRequest(BaseModel):
    """Create editable copy before generating storyboard prompts."""

    topic: str = Field(..., min_length=1)
    sceneCount: int = Field(5, ge=1, le=100)
    draftMode: str = "full"
    splitType: str = "line"
    targetCharCount: int = Field(175, ge=50, le=3000)
    charCountMode: str = "around"


class TestConnectionRequest(BaseModel):
    """Current React workbench service-test request."""

    service: str
    config: dict[str, Any] = Field(default_factory=dict)


class PromptPrefixSaveRequest(BaseModel):
    """Persisted prompt prefix for Quick Create test and generation flows."""

    promptPrefix: str = ""
    presetId: str | None = None


QUICK_CREATE_PRESETS_PATH = Path("data/quick_create_presets.json")

PRESET_FIELDS = {
    "id",
    "name",
    "createdAt",
    "updatedAt",
    "ttsMode",
    "voice",
    "speed",
    "workflow",
    "bgm",
    "bgmVolume",
    "promptPrefix",
    "splitType",
    "enableMotion",
    "enableSubtitles",
    "minimaxModel",
    "emotion",
    "mimoModel",
    "mimoStyle",
    "sceneCount",
    "copyCharCount",
    "copyCharCountMode",
    "copyDraftMode",
    "mediaWidth",
    "mediaHeight",
    "videoFps",
    "imageAspectRatio",
    "subtitleStyle",
}

PRESET_DEFAULTS = {
    "name": "当前保存配置",
    "ttsMode": "minimax",
    "voice": "male-qn-qingse",
    "speed": 1.0,
    "workflow": "",
    "bgm": "",
    "bgmVolume": 30,
    "promptPrefix": "",
    "splitType": "line",
    "enableMotion": True,
    "enableSubtitles": True,
    "minimaxModel": "speech-2.8-turbo",
    "emotion": "",
    "mimoModel": "mimo-v2.5-tts",
    "mimoStyle": "",
    "sceneCount": 5,
    "copyCharCount": 100,
    "copyCharCountMode": "around",
    "copyDraftMode": "segmented",
    # 成片规格默认竖屏 1080p@30；1440 仅作高级/慢选项
    "mediaWidth": 1080,
    "mediaHeight": 1920,
    "videoFps": 30,
    "imageAspectRatio": "1080x1920",
    "subtitleStyle": {
        **SUBTITLE_STYLE_DEFAULTS,
        "mode": "hyperframes",
        "preset": "caption-box",
        "fontSize": 80,
        "outlineWidth": 10,  # dual-write of boxPadding for caption-box
        "marginV": 200,
        "maxCharsPerLine": 20,
        "maxLines": 1,
        "primaryColor": "#FFFFFF",
        "accentColor": "#F97316",
        "shadow": 0,
        "segmentMode": "sentence",
        "boxEnabled": True,
        "boxPadding": 10,
        "boxOpacity": 72,
        "boxColor": "#000000",
        "boxRadius": 12,
    },
}


def _ensure_llm_configured():
    llm_config = config_manager.get_llm_config()
    if not (
        llm_config.get("api_key")
        and llm_config.get("base_url")
        and llm_config.get("model")
    ):
        raise HTTPException(
            status_code=400,
            detail="LLM 配置未保存。请在系统设置中测试 LLM 连接，成功后配置会自动保存。",
        )


def _normalize_draft_mode(mode: str | None) -> str:
    return "segmented" if mode == "segmented" else "full"


def _normalize_split_type(split_type: str | None) -> str:
    return split_type if split_type in {"paragraph", "line", "sentence"} else "line"


def _normalize_char_count_mode(mode: str | None) -> str:
    return "within" if mode == "within" else "around"


def _char_count_phrase(target_char_count: int, mode: str | None) -> str:
    suffix = "以内" if _normalize_char_count_mode(mode) == "within" else "左右"
    return f"{target_char_count} 字{suffix}"


def _per_storyboard_word_range(target_char_count: int, scene_count: int, mode: str | None) -> tuple[int, int]:
    per_storyboard = max(1, target_char_count / max(scene_count, 1))
    if _normalize_char_count_mode(mode) == "within":
        return max(5, int(per_storyboard * 0.55)), max(6, int(per_storyboard))
    return max(5, int(per_storyboard * 0.75)), max(6, int(per_storyboard * 1.25))


def _format_segmented_draft(narrations: list[str]) -> str:
    cleaned_narrations = [clean_narration_text(narration) for narration in narrations]
    return "\n\n".join(narration for narration in cleaned_narrations if narration)


def _strip_segment_prefix(text: str) -> str:
    return clean_narration_text(text)


async def _narrations_from_confirmed_copy(request: GenerateScriptRequest, llm_service) -> list[str]:
    """
    Build storyboard narrations from confirmed copy.

    Full drafts use *deterministic semantic packing* (same rules as the React
    workbench) instead of LLM re-split. The old LLM path rewrote text into a
    fixed scene count and often mid-cut words (e.g. 「科学家发」/「现，光速」).
    """
    confirmed_text = (request.confirmedText or "").strip()
    if not confirmed_text:
        return await generate_narrations_from_topic(
            llm_service=llm_service,
            topic=request.topic,
            n_scenes=request.sceneCount,
            min_words=5,
            max_words=40,
        )

    split_type = _normalize_split_type(request.splitType)

    if _normalize_draft_mode(request.draftMode) == "segmented":
        segments = await split_narration_script(confirmed_text, split_mode=split_type)
        narrations = [_strip_segment_prefix(segment) for segment in segments]
        narrations = [narration for narration in narrations if narration]
        if not narrations:
            raise ValueError("确认文案为空，无法生成分镜脚本。")
        return narrations

    # full draft: semantic pack (no character-equal LLM rewrite)
    from pixelle_video.utils.storyboard_split import build_storyboard_narrations

    # soft_expand creates multi-clip sentences (clause-level). Prefer off when
    # continuous TTS is selected so hold/pad does not inject mid-sentence pauses.
    tts_delivery = str(
        getattr(request, "ttsDelivery", None)
        or getattr(request, "tts_delivery", None)
        or ""
    ).strip().lower()
    soft_expand = tts_delivery not in {"continuous", "cont", "1", "true"}

    narrations = build_storyboard_narrations(
        confirmed_text,
        split_type=split_type,  # type: ignore[arg-type]
        target_count=request.sceneCount,
        soft_expand=soft_expand,
        heal=True,
    )
    narrations = [_strip_segment_prefix(segment) for segment in narrations]
    narrations = [narration for narration in narrations if narration]
    if not narrations:
        raise ValueError("确认文案为空，无法生成分镜脚本。")
    return narrations


def _frontend_tts_mode(mode: str | None) -> str:
    if mode == "minimax":
        return "minimax"
    if mode == "mimo":
        return "mimo"
    if mode == "comfyui":
        return "comfyui"
    return "local"


def _backend_tts_mode(mode: str | None) -> str:
    if mode == "minimax":
        return "minimax"
    if mode == "mimo":
        return "mimo"
    if mode == "comfyui":
        return "comfyui"
    return "edge"


def _is_frontend_placeholder(value: str | None) -> bool:
    return bool(value and value.startswith(("bgm-", "tpl-", "runninghub-", "bizyair-", "comfyui-")))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, minimum), maximum)


def _coerce_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, minimum), maximum)


def _normalize_subtitle_style(value: Any) -> dict[str, Any]:
    """Normalize via SubtitleRenderer so box/stroke intent matches export."""
    from pixelle_video.services.subtitle_renderer import SubtitleRenderer

    raw = value if isinstance(value, dict) else {}
    return SubtitleRenderer().normalize_style(raw)


def _normalize_preset(preset: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now_iso()
    base = {**PRESET_DEFAULTS, **(existing or {}), **preset}
    normalized = {key: base.get(key) for key in PRESET_FIELDS if key in base}

    normalized["id"] = str(existing.get("id") if existing else preset.get("id") or f"preset-{uuid4().hex[:12]}")
    normalized["name"] = str(base.get("name") or "未命名预设").strip()[:60] or "未命名预设"
    normalized["createdAt"] = str((existing or {}).get("createdAt") or base.get("createdAt") or now)
    normalized["updatedAt"] = now

    normalized["ttsMode"] = normalized.get("ttsMode") if normalized.get("ttsMode") in {"edge", "comfyui", "minimax", "mimo"} else "minimax"
    normalized["splitType"] = _normalize_split_type(str(normalized.get("splitType") or "line"))
    normalized["copyCharCountMode"] = _normalize_char_count_mode(str(normalized.get("copyCharCountMode") or "around"))
    normalized["copyDraftMode"] = _normalize_draft_mode(str(normalized.get("copyDraftMode") or "full"))
    normalized["speed"] = _coerce_float(normalized.get("speed"), 1.0, 0.5, 2.0)
    normalized["bgmVolume"] = _coerce_int(normalized.get("bgmVolume"), 30, 0, 100)
    normalized["sceneCount"] = _coerce_int(normalized.get("sceneCount"), 5, 1, 100)
    normalized["copyCharCount"] = _coerce_int(normalized.get("copyCharCount"), 175, 50, 3000)
    normalized["mediaWidth"] = _coerce_int(normalized.get("mediaWidth"), 1080, 512, 3840)
    normalized["mediaHeight"] = _coerce_int(normalized.get("mediaHeight"), 1920, 512, 3840)
    normalized["videoFps"] = _coerce_int(normalized.get("videoFps"), 30, 12, 60)

    normalized["enableMotion"] = bool(normalized.get("enableMotion", True))
    normalized["enableSubtitles"] = bool(normalized.get("enableSubtitles", True))
    normalized["subtitleStyle"] = _normalize_subtitle_style(normalized.get("subtitleStyle"))

    for key in ["voice", "workflow", "bgm", "promptPrefix", "minimaxModel", "emotion", "mimoModel", "mimoStyle", "imageAspectRatio"]:
        normalized[key] = str(normalized.get(key) or "")

    if not normalized["imageAspectRatio"]:
        normalized["imageAspectRatio"] = f"{normalized['mediaWidth']}x{normalized['mediaHeight']}"

    return normalized


def _legacy_preset_from_config(name: str = "当前保存配置") -> dict[str, Any]:
    legacy = _preset_from_config(name)
    return _normalize_preset({**PRESET_DEFAULTS, **legacy}, existing={"id": "quick-create-default"})


def _read_presets_store() -> dict[str, Any]:
    if not QUICK_CREATE_PRESETS_PATH.exists():
        fallback = _legacy_preset_from_config()
        return {"defaultPresetId": fallback["id"], "presets": [fallback]}

    try:
        data = json.loads(QUICK_CREATE_PRESETS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Quick-create preset store is invalid; falling back to current config.")
        fallback = _legacy_preset_from_config()
        return {"defaultPresetId": fallback["id"], "presets": [fallback]}

    raw_presets = data.get("presets") if isinstance(data, dict) else []
    presets: list[dict[str, Any]] = []
    for raw_preset in raw_presets or []:
        if isinstance(raw_preset, dict):
            presets.append(_normalize_preset(raw_preset, existing=raw_preset))

    if not presets:
        fallback = _legacy_preset_from_config()
        return {"defaultPresetId": fallback["id"], "presets": [fallback]}

    default_preset_id = str(data.get("defaultPresetId") or presets[0]["id"])
    if not any(preset["id"] == default_preset_id for preset in presets):
        default_preset_id = presets[0]["id"]

    return {"defaultPresetId": default_preset_id, "presets": presets}


def _write_presets_store(store: dict[str, Any]) -> None:
    QUICK_CREATE_PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUICK_CREATE_PRESETS_PATH.write_text(
        json.dumps(store, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _preset_response(store: dict[str, Any], preset: dict[str, Any] | None = None) -> dict[str, Any]:
    presets = store["presets"]
    default_preset_id = store["defaultPresetId"]
    active_preset = preset or next((item for item in presets if item["id"] == default_preset_id), presets[0])
    return {
        "success": True,
        "presets": presets,
        "preset": active_preset,
        "defaultPresetId": default_preset_id,
    }


def _find_preset_or_404(store: dict[str, Any], preset_id: str) -> dict[str, Any]:
    preset = next((item for item in store["presets"] if item["id"] == preset_id), None)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在或已被删除。")
    return preset


def _preset_from_config(name: str = "当前保存配置") -> dict[str, Any]:
    comfyui = config_manager.get_comfyui_config()
    quick_create = config_manager.get("quick_create", {})
    tts = comfyui.get("tts", {})
    tts_mode = tts.get("inference_mode", "local")

    if tts_mode == "minimax":
        voice = tts.get("minimax", {}).get("voice_id", "")
        speed = tts.get("minimax", {}).get("speed", 1.0)
    elif tts_mode == "mimo":
        voice = tts.get("mimo", {}).get("voice_id", "")
        speed = tts.get("mimo", {}).get("speed", 1.0)
    else:
        voice = tts.get("local", {}).get("voice", "")
        speed = tts.get("local", {}).get("speed", 1.0)

    workflow = (
        comfyui.get("video", {}).get("default_workflow")
        or comfyui.get("image", {}).get("default_workflow")
        or ""
    )
    bgm_path = quick_create.get("bgm_path")
    bgm = (
        bgm_path
        if bgm_path
        and not _is_frontend_placeholder(bgm_path)
        and resource_exists("bgm", bgm_path)
        else "bgm-none"
    )
    bgm_volume = int(float(quick_create.get("bgm_volume") or 0.2) * 100)

    return {
        "id": "quick-create-default",
        "name": name,
        "ttsMode": _backend_tts_mode(tts_mode),
        "voice": voice,
        "speed": speed,
        "workflow": workflow,
        "bgm": bgm,
        "bgmVolume": bgm_volume,
        "promptPrefix": (
            comfyui.get("video", {}).get("prompt_prefix")
            or comfyui.get("image", {}).get("prompt_prefix")
            or ""
        ),
        "splitType": "line",
        "enableMotion": config_manager.get("template", {}).get("image_motion_enabled", True),
        "enableSubtitles": config_manager.get("template", {}).get("subtitle_enabled", True),
        "subtitleStyle": config_manager.get("subtitle", {}).get("default_style") or SUBTITLE_STYLE_DEFAULTS,
        "minimaxModel": tts.get("minimax", {}).get("model"),
        "emotion": tts.get("minimax", {}).get("emotion"),
        "mimoModel": tts.get("mimo", {}).get("model"),
        "mimoStyle": tts.get("mimo", {}).get("style"),
    }


def _quick_create_config_from_preset(preset: dict[str, Any]) -> dict[str, Any]:
    bgm = preset.get("bgm")
    bgm_path = None if not bgm or _is_frontend_placeholder(bgm) else bgm
    volume = preset.get("bgmVolume", 20)
    if volume > 1:
        volume = volume / 100
    volume = min(max(float(volume), 0.0), 0.5)

    workflow = preset.get("workflow")
    media_workflow = None if _is_frontend_placeholder(workflow) else workflow

    return {
        "tts_inference_mode": _frontend_tts_mode(preset.get("ttsMode")),
        "tts_voice": preset.get("voice"),
        "tts_speed": preset.get("speed"),
        "minimax_model": preset.get("minimaxModel"),
        "minimax_emotion": preset.get("emotion"),
        "mimo_model": preset.get("mimoModel"),
        "mimo_style": preset.get("mimoStyle"),
        "media_workflow": media_workflow,
        "prompt_prefix": preset.get("promptPrefix", ""),
        "bgm_path": bgm_path,
        "bgm_volume": volume,
        "composition_mode": "plain_image",
        "image_motion_enabled": preset.get("enableMotion", True),
        "subtitle_enabled": preset.get("enableSubtitles", True),
        "subtitle_style": preset.get("subtitleStyle") or SUBTITLE_STYLE_DEFAULTS,
    }


def _service_test_request(request: TestConnectionRequest) -> ServiceTestRequest:
    service_aliases = {
        "comfy": "comfyui",
        "comfyui": "comfyui",
        "llm": "llm",
        "image_generation": "image_generation",
        "runninghub": "runninghub",
        "bizyair": "bizyair",
        "minimax": "minimax",
        "mimo": "mimo",
    }
    service = service_aliases.get(request.service)
    if not service:
        raise HTTPException(status_code=400, detail=f"Unsupported service: {request.service}")

    config = dict(request.config)
    normalized = {
        "api_key": config.get("api_key") or config.get("apiKey"),
        "base_url": config.get("base_url") or config.get("baseUrl"),
        "model": config.get("model"),
        "comfyui_url": config.get("comfyui_url") or config.get("url"),
        "comfyui_api_key": config.get("comfyui_api_key") or config.get("apiKey"),
        "runninghub_api_key": config.get("runninghub_api_key") or config.get("apiKey"),
        "bizyair_api_key": config.get("bizyair_api_key") or config.get("apiKey"),
        "minimax_api_key": config.get("minimax_api_key") or config.get("apiKey"),
        "mimo_api_key": config.get("mimo_api_key") or config.get("apiKey"),
    }
    return ServiceTestRequest(
        service=service,  # type: ignore[arg-type]
        config={key: value for key, value in normalized.items() if value},
    )


@router.get("/presets")
async def list_presets():
    """Return all saved quick-create presets and the current default preset."""
    store = _read_presets_store()
    return _preset_response(store)


@router.post("/presets")
async def save_preset(preset: dict[str, Any]):
    """Create a new reusable quick-create preset from the current React state."""
    try:
        store = _read_presets_store()
        existing_presets = [
            item for item in store["presets"] if item.get("id") != "quick-create-default"
        ]
        saved = _normalize_preset(preset)
        presets = [*existing_presets, saved]
        store = {"defaultPresetId": saved["id"], "presets": presets}
        _write_presets_store(store)
        config_manager.save_quick_create_config(_quick_create_config_from_preset(saved))
        return _preset_response(store, saved)
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/presets/{preset_id}")
async def update_preset(preset_id: str, preset: dict[str, Any]):
    """Overwrite an existing reusable quick-create preset."""
    try:
        store = _read_presets_store()
        existing = _find_preset_or_404(store, preset_id)
        saved = _normalize_preset({**preset, "id": preset_id}, existing=existing)
        store["presets"] = [
            saved if item["id"] == preset_id else item for item in store["presets"]
        ]
        if not store.get("defaultPresetId"):
            store["defaultPresetId"] = preset_id
        _write_presets_store(store)
        config_manager.save_quick_create_config(_quick_create_config_from_preset(saved))
        return _preset_response(store, saved)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/presets/{preset_id}/default")
async def set_default_preset(preset_id: str):
    """Set an existing preset as the default quick-create preset."""
    try:
        store = _read_presets_store()
        preset = _find_preset_or_404(store, preset_id)
        store["defaultPresetId"] = preset_id
        _write_presets_store(store)
        config_manager.save_quick_create_config(_quick_create_config_from_preset(preset))
        return _preset_response(store, preset)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: str):
    """Delete a reusable quick-create preset."""
    try:
        store = _read_presets_store()
        _find_preset_or_404(store, preset_id)
        remaining = [item for item in store["presets"] if item["id"] != preset_id]
        if not remaining:
            fallback = _legacy_preset_from_config()
            remaining = [fallback]
            default_preset_id = fallback["id"]
        elif store.get("defaultPresetId") == preset_id:
            default_preset_id = remaining[0]["id"]
        else:
            default_preset_id = store.get("defaultPresetId") or remaining[0]["id"]

        store = {"defaultPresetId": default_preset_id, "presets": remaining}
        active_preset = next(
            (item for item in remaining if item["id"] == default_preset_id),
            remaining[0],
        )
        _write_presets_store(store)
        config_manager.save_quick_create_config(_quick_create_config_from_preset(active_preset))
        return _preset_response(store, active_preset)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/prompt-prefix")
async def save_prompt_prefix(request: PromptPrefixSaveRequest):
    """Persist only the shared prompt prefix without touching other quick-create settings."""
    try:
        config_manager.set_prompt_prefix(request.promptPrefix)
        store = _read_presets_store()
        preset_id = request.presetId or store["defaultPresetId"]
        existing = _find_preset_or_404(store, preset_id)
        saved = _normalize_preset(
            {"id": preset_id, "promptPrefix": request.promptPrefix},
            existing=existing,
        )
        store["presets"] = [
            saved if item["id"] == preset_id else item for item in store["presets"]
        ]
        _write_presets_store(store)
        config_manager.save_quick_create_config(_quick_create_config_from_preset(saved))
        return {
            **_preset_response(store, saved),
            "promptPrefix": saved.get("promptPrefix", ""),
        }
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/test-connection")
async def test_connection(request: TestConnectionRequest):
    """Compatibility route for the React settings panel."""
    return await test_service(_service_test_request(request))


@router.post("/generate-copy-draft")
async def generate_copy_draft(request: GenerateCopyDraftRequest, pixelle_video: PixelleVideoDep):
    """Generate editable copy draft before storyboard generation."""
    try:
        _ensure_llm_configured()

        draft_mode = _normalize_draft_mode(request.draftMode)
        if draft_mode == "segmented":
            min_words, max_words = _per_storyboard_word_range(
                request.targetCharCount,
                request.sceneCount,
                request.charCountMode,
            )
            narrations = await generate_narrations_from_topic(
                llm_service=pixelle_video.llm,
                topic=request.topic,
                n_scenes=request.sceneCount,
                min_words=min_words,
                max_words=max_words,
            )
            draft_text = _format_segmented_draft(narrations)
        else:
            # Step 1 of two-step storyboard flow: pure copy only.
            # Do NOT bind the draft to a fixed sceneCount — that used to force ~N
            # paragraphs and make later "semantic suggestions" self-fulfilling.
            length_phrase = _char_count_phrase(request.targetCharCount, request.charCountMode)
            prompt = (
                "请基于下面的创作主题，写一篇适合短视频旁白的完整中文口播稿。\n"
                f"创作主题：{request.topic}\n\n"
                f"目标：整篇文案总字数控制在 {length_phrase}。\n"
                "要求：\n"
                "1. 只输出口播正文，不要标题、编号、Markdown、分镜序号或解释。\n"
                "2. 语气自然、有画面感，适合 TTS 朗读；用完整句子，句末保留。！？等标点。\n"
                "3. 不要分镜提示词，不要镜头描述，不要写成「第一镜/第二镜」。\n"
                "4. 不要按固定分镜数量切割正文；先把故事讲完整，分镜由后续步骤分析。\n"
                "5. 内容应有自然的起承转合，方便创作者继续编辑。"
            )
            draft_text = str(
                await pixelle_video.llm(
                    prompt=prompt,
                    temperature=0.8,
                    max_tokens=4096,
                    thinking=False,
                )
            ).strip()
            if not draft_text:
                raise ValueError("LLM 未返回口播正文，请检查模型配置或稍后重试")

        return {"success": True, "draftMode": draft_mode, "draftText": draft_text}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/generate-script")
async def generate_script(request: GenerateScriptRequest, pixelle_video: PixelleVideoDep):
    """Generate editable scene narration and visual prompts through the real LLM."""
    try:
        _ensure_llm_configured()

        narrations = await _narrations_from_confirmed_copy(request, pixelle_video.llm)
        image_prompts = await generate_image_prompts(
            llm_service=pixelle_video.llm,
            narrations=narrations,
            min_words=20,
            max_words=80,
        )
        data = [
            {
                "id": index + 1,
                "ttsText": narration,
                "visualPrompt": image_prompts[index] if index < len(image_prompts) else "",
            }
            for index, narration in enumerate(narrations)
        ]
        return {"success": True, "data": data}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
