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
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    segment_narration_semantically,
)
from pixelle_video.utils.os_util import resource_exists
from pixelle_video.utils.storyboard_split import (
    AUTO_MAX_CHARS_PER_SEGMENT,
    soft_expand_by_pause,
    split_draft_by_rule,
)

router = APIRouter(tags=["React Workbench"])


class GenerateScriptRequest(BaseModel):
    """Current React workbench script-generation request."""

    topic: str = Field(..., min_length=1)
    sceneCount: int = Field(5, ge=1, le=100)
    splitType: str = "auto"
    draftMode: str = "full"
    confirmedText: str | None = None
    # continuous | per_scene — continuous disables soft comma-expand so holds
    # do not inject mid-sentence pauses after clause-level splits.
    ttsDelivery: str | None = None
    promptPrefix: str | None = None
    segmentationMode: str = "auto"
    directorMode: str = "auto"
    density: str = "standard"
    targetSceneCount: int | None = Field(default=None, ge=1, le=100)


class GenerateCopyDraftRequest(BaseModel):
    """Create editable copy before generating storyboard prompts."""

    topic: str = Field(..., min_length=1)
    sceneCount: int = Field(5, ge=1, le=100)
    draftMode: str = "full"
    splitType: str = "auto"
    targetCharCount: int = Field(175, ge=50, le=3000)
    charCountMode: str = "around"
    directorMode: str = "auto"
    density: str = "standard"
    targetSceneCount: int | None = Field(default=None, ge=1, le=100)


class StoryboardAnalyzeRequest(BaseModel):
    """Analyze narration boundaries without rewriting the source copy."""

    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(..., min_length=1, max_length=20000)
    split_type: str = Field("auto", alias="splitType")
    scene_count: int = Field(5, ge=1, le=100, alias="sceneCount")
    tts_delivery: str | None = Field(default=None, alias="ttsDelivery")
    segmentation_mode: str = Field("deterministic", alias="segmentationMode")
    soft_expand: bool | None = Field(default=None, alias="softExpand")
    director_mode: str = Field("auto", alias="directorMode")
    density: str = "standard"
    target_scene_count: int | None = Field(default=None, ge=1, le=100, alias="targetSceneCount")

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value


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
    "directorMode",
    "density",
    "targetSceneCount",
    "enableMotion",
    "enableSubtitles",
    "minimaxModel",
    "emotion",
    "mimoModel",
    "mimoStyle",
    "qwenAudioModel",
    "qwenAudioMode",
    "qwenAudioInstruction",
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
    "splitType": "auto",
    "directorMode": "auto",
    "density": "standard",
    "targetSceneCount": None,
    "enableMotion": True,
    "enableSubtitles": True,
    "minimaxModel": "speech-2.8-turbo",
    "emotion": "",
    "mimoModel": "mimo-v2.5-tts",
    "mimoStyle": "",
    "qwenAudioModel": "qwen3-tts-flash",
    "qwenAudioMode": "preset",
    "qwenAudioInstruction": "",
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
    return split_type if split_type in {"auto", "paragraph", "line", "sentence"} else "auto"


def _normalize_segmentation_mode(mode: str | None) -> str:
    return mode if mode in {"auto", "deterministic", "llm"} else "auto"


def _normalize_director_mode(mode: str | None) -> str:
    return "custom" if str(mode or "").strip().lower() == "custom" else "auto"


def _normalize_storyboard_density(density: str | None) -> str:
    value = str(density or "").strip().lower()
    return value if value in {"sparse", "standard", "dense"} else "standard"


def _density_chars_per_scene(density: str | None) -> int:
    return {"sparse": 60, "standard": 40, "dense": 28}.get(
        _normalize_storyboard_density(density),
        40,
    )


def _should_soft_expand(*, density: str | None, tts_delivery: str | None, requested: bool | None = None) -> bool:
    if requested is not None:
        return requested
    if _normalize_storyboard_density(density) == "sparse":
        return False
    if str(tts_delivery or "").strip().lower() in {"continuous", "cont", "1", "true"}:
        return False
    return True


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


async def _narrations_and_visual_focus_from_confirmed_copy(
    request: GenerateScriptRequest,
    llm_service,
) -> tuple[list[str], list[str], list[list[str]]]:
    """
    Build storyboard narrations from confirmed copy.

    Full drafts use *deterministic semantic packing* (same rules as the React
    workbench) instead of LLM re-split. The old LLM path rewrote text into a
    fixed scene count and often mid-cut words (e.g. 「科学家发」/「现，光速」).
    """
    confirmed_text = (request.confirmedText or "").strip()
    if not confirmed_text:
        narrations = await generate_narrations_from_topic(
            llm_service=llm_service,
            topic=request.topic,
            n_scenes=request.sceneCount,
            min_words=5,
            max_words=40,
        )
        return narrations, [""] * len(narrations), [[] for _ in narrations]

    split_type = _normalize_split_type(request.splitType)

    director_mode = _normalize_director_mode(getattr(request, "directorMode", "auto"))
    density = _normalize_storyboard_density(getattr(request, "density", "standard"))
    tts_delivery = str(
        getattr(request, "ttsDelivery", None)
        or getattr(request, "tts_delivery", None)
        or ""
    ).strip().lower()
    soft_expand = _should_soft_expand(density=density, tts_delivery=tts_delivery)
    source_split_type = "line" if _normalize_draft_mode(request.draftMode) == "segmented" else split_type
    source_units = split_draft_by_rule(confirmed_text, source_split_type)  # type: ignore[arg-type]
    if soft_expand:
        source_units = soft_expand_by_pause(source_units)
    target_count = getattr(request, "targetSceneCount", None) if director_mode == "custom" else None
    if target_count is None and director_mode == "custom":
        target_count = request.sceneCount

    # Auto mode keeps every safe semantic unit. Custom mode packs adjacent units
    # toward the user's target but never invents a mid-phrase cut.
    if director_mode == "custom":
        from pixelle_video.utils.storyboard_split import pack_semantic_units
        narrations = pack_semantic_units(source_units, int(target_count or request.sceneCount))
    else:
        narrations = source_units or [confirmed_text]
    segmentation_mode = _normalize_segmentation_mode(getattr(request, "segmentationMode", "auto"))
    visual_focuses = [""] * len(narrations)
    text_anchor_hints: list[list[str]] = [[] for _ in narrations]
    overlong = any(len(re.sub(r"\s+", "", narration)) > 52 for narration in narrations)
    if segmentation_mode in {"auto", "llm"} and overlong:
        try:
            semantic_segments = await segment_narration_semantically(
                llm_service,
                confirmed_text,
                target_count=(int(target_count) if target_count else max(2, min(3, len(narrations) + 1))),
                max_chars=52,
            )
            if semantic_segments:
                narrations = [item["text"] for item in semantic_segments]
                visual_focuses = [str(item.get("visual_focus") or "") for item in semantic_segments]
                text_anchor_hints = [
                    [str(value).strip() for value in (item.get("text_anchors") or []) if str(value).strip()]
                    for item in semantic_segments
                ]
                logger.info(
                    "Semantic segmentation accepted {} extractive narration segments",
                    len(narrations),
                )
        except Exception as exc:
            logger.warning("Semantic segmentation unavailable; using deterministic units: {}", exc)
    narrations = [_strip_segment_prefix(segment) for segment in narrations]
    narrations = [narration for narration in narrations if narration]
    if not narrations:
        raise ValueError("确认文案为空，无法生成分镜脚本。")
    if len(visual_focuses) != len(narrations):
        visual_focuses = [""] * len(narrations)
    if len(text_anchor_hints) != len(narrations):
        text_anchor_hints = [[] for _ in narrations]
    return narrations, visual_focuses, text_anchor_hints


async def _narrations_from_confirmed_copy(request: GenerateScriptRequest, llm_service) -> list[str]:
    """Backward-compatible narration-only view for callers that do not need focus hints."""
    narrations, _visual_focuses, _text_anchor_hints = await _narrations_and_visual_focus_from_confirmed_copy(
        request,
        llm_service,
    )
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


def _storyboard_analysis_units(
    units: list[str],
    *,
    semantic_metadata: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attach stable duration and boundary metadata to narration units."""
    metadata = semantic_metadata or []
    result: list[dict[str, Any]] = []
    for index, raw_unit in enumerate(units):
        unit = str(raw_unit or "").strip()
        if not unit:
            continue
        chars = len(re.sub(r"\s+", "", unit))
        semantic = metadata[index] if index < len(metadata) else {}
        text_anchors: list[str] = []
        if semantic:
            boundary_reason = str(semantic.get("boundary_reason") or "语义边界")
            visual_focus = str(semantic.get("visual_focus") or "")
            text_anchors = [str(value).strip() for value in (semantic.get("text_anchors") or []) if str(value).strip()]
        elif re.search(r"[。！？.!?…]$", unit):
            boundary_reason = "句末边界"
            visual_focus = ""
        elif re.search(r"[，,；;：:]$", unit):
            boundary_reason = "停顿边界"
            visual_focus = ""
        else:
            boundary_reason = "换行或段落边界"
            visual_focus = ""
            text_anchors = []
        if not text_anchors:
            text_anchors = _extract_text_anchors(unit)
        result.append(
            {
                "index": len(result) + 1,
                "text": unit,
                "chars": chars,
                "estimatedSeconds": round(max(0.5, chars / 260 * 60), 1),
                "boundaryReason": boundary_reason,
                "visualFocus": visual_focus,
                "textAnchors": text_anchors,
            }
        )
    return result


def _extract_text_anchors(text: str) -> list[str]:
    """Extract short factual tokens that benefit from deterministic visual carriers."""
    source = str(text or "")
    patterns = (
        r"星期[一二三四五六日天]",
        r"周[一二三四五六日]",
        r"\b\d{4}年\d{1,2}月\d{1,2}[日号]?\b",
        r"\b\d{1,2}月\d{1,2}[日号]?\b",
        r"\b\d{4}[./-]\d{1,2}[./-]\d{1,2}\b",
        r"\b\d{1,2}:\d{2}\b",
        r"(?:清晨|早上|上午|中午|下午|傍晚|晚上)?[零一二三四五六七八九十百两\d]{1,3}点(?:[零一二三四五六七八九十百两\d]{1,3}分)?",
        r"\b\d+(?:\.\d+)?%?\b",
    )
    anchors: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, source):
            value = str(match).strip()
            if value and value not in anchors:
                anchors.append(value)
    return anchors[:3]


def _storyboard_analysis_warnings(units: list[dict[str, Any]]) -> list[str]:
    if not units:
        return ["没有可分析的旁白内容"]
    longest_chars = max(int(unit["chars"]) for unit in units)
    longest_seconds = max(float(unit["estimatedSeconds"]) for unit in units)
    warnings: list[str] = []
    if longest_chars > AUTO_MAX_CHARS_PER_SEGMENT:
        warnings.append(f"仍有 {longest_chars} 字的旁白无法在现有边界处安全拆分")
    if longest_seconds > 10:
        warnings.append(
            f"最长分镜预计 {longest_seconds:.1f} 秒，建议补充停顿标点或启用视觉节拍"
        )
    return warnings


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

    normalized["ttsMode"] = normalized.get("ttsMode") if normalized.get("ttsMode") in {"edge", "comfyui", "minimax", "mimo", "qwen_audio"} else "minimax"
    normalized["splitType"] = _normalize_split_type(str(normalized.get("splitType") or "auto"))
    normalized["directorMode"] = _normalize_director_mode(str(normalized.get("directorMode") or "auto"))
    normalized["density"] = _normalize_storyboard_density(str(normalized.get("density") or "standard"))
    normalized["copyCharCountMode"] = _normalize_char_count_mode(str(normalized.get("copyCharCountMode") or "around"))
    normalized["copyDraftMode"] = _normalize_draft_mode(str(normalized.get("copyDraftMode") or "full"))
    normalized["qwenAudioMode"] = normalized.get("qwenAudioMode") if normalized.get("qwenAudioMode") in {"preset", "instruct", "design", "clone"} else "preset"
    normalized["speed"] = _coerce_float(normalized.get("speed"), 1.0, 0.5, 2.0)
    normalized["bgmVolume"] = _coerce_int(normalized.get("bgmVolume"), 30, 0, 100)
    normalized["sceneCount"] = _coerce_int(normalized.get("sceneCount"), 5, 1, 100)
    if normalized.get("targetSceneCount") is not None:
        normalized["targetSceneCount"] = _coerce_int(normalized.get("targetSceneCount"), normalized["sceneCount"], 1, 100)
    elif normalized["directorMode"] == "custom":
        normalized["targetSceneCount"] = normalized["sceneCount"]
    normalized["copyCharCount"] = _coerce_int(normalized.get("copyCharCount"), 175, 50, 3000)
    normalized["mediaWidth"] = _coerce_int(normalized.get("mediaWidth"), 1080, 512, 3840)
    normalized["mediaHeight"] = _coerce_int(normalized.get("mediaHeight"), 1920, 512, 3840)
    normalized["videoFps"] = _coerce_int(normalized.get("videoFps"), 30, 12, 60)

    normalized["enableMotion"] = bool(normalized.get("enableMotion", True))
    normalized["enableSubtitles"] = bool(normalized.get("enableSubtitles", True))
    normalized["subtitleStyle"] = _normalize_subtitle_style(normalized.get("subtitleStyle"))

    for key in ["voice", "workflow", "bgm", "promptPrefix", "minimaxModel", "emotion", "mimoModel", "mimoStyle", "qwenAudioModel", "qwenAudioInstruction", "imageAspectRatio"]:
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
        "splitType": "auto",
        "enableMotion": config_manager.get("template", {}).get("image_motion_enabled", True),
        "enableSubtitles": config_manager.get("template", {}).get("subtitle_enabled", True),
        "useApiImage": bool(config_manager.get("template", {}).get("use_api_image", False)),
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
        "use_api_image": bool(preset.get("useApiImage", preset.get("use_api_image", False))),
        "subtitle_style": preset.get("subtitleStyle") or SUBTITLE_STYLE_DEFAULTS,
    }


def _service_test_request(request: TestConnectionRequest) -> ServiceTestRequest:
    service_aliases = {
        "comfy": "comfyui",
        "comfyui": "comfyui",
        "llm": "llm",
        "image_generation": "image_generation",
        "vision_understanding": "vision_understanding",
        "runninghub": "runninghub",
        "bizyair": "bizyair",
        "minimax": "minimax",
        "mimo": "mimo",
        "qwen_audio": "qwen_audio",
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
        "qwen_audio_api_key": config.get("qwen_audio_api_key") or config.get("apiKey"),
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
                f"当前用户填写的初始参考分镜数：{request.sceneCount} 个分镜，仅用于节奏参考，不要求正文按该数量切割。\n"
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


@router.post("/storyboard/analyze")
async def analyze_storyboard(request: StoryboardAnalyzeRequest, pixelle_video: PixelleVideoDep):
    """Return semantic/rhythm storyboard analysis for editable narration."""
    source = request.text.strip()
    split_type = _normalize_split_type(request.split_type)
    segmentation_mode = _normalize_segmentation_mode(request.segmentation_mode)
    tts_delivery = str(request.tts_delivery or "").strip().lower()
    director_mode = _normalize_director_mode(request.director_mode)
    density = _normalize_storyboard_density(request.density)
    soft_expand = _should_soft_expand(
        density=density,
        tts_delivery=tts_delivery,
        requested=request.soft_expand,
    )

    units = split_draft_by_rule(source, split_type)  # type: ignore[arg-type]
    if soft_expand:
        units = soft_expand_by_pause(units)
    semantic_count = len(units) or 1
    target_count = request.target_scene_count if director_mode == "custom" else None
    if target_count is None and director_mode == "custom":
        target_count = request.scene_count

    used_llm = False
    semantic_metadata: list[dict[str, Any]] = []
    overlong = any(len(re.sub(r"\s+", "", unit)) > AUTO_MAX_CHARS_PER_SEGMENT for unit in units)
    if overlong and segmentation_mode in {"auto", "llm"}:
        llm_service = getattr(pixelle_video, "llm", None)
        if llm_service is not None:
            try:
                semantic_segments = await segment_narration_semantically(
                    llm_service,
                    source,
                    target_count=(int(target_count) if target_count else max(2, min(3, semantic_count + 1))),
                    max_chars=AUTO_MAX_CHARS_PER_SEGMENT,
                )
                if len(semantic_segments) > 1:
                    units = [item["text"] for item in semantic_segments]
                    semantic_metadata = [
                        {
                            "boundary_reason": str(item.get("boundary_reason") or "语义边界"),
                            "visual_focus": str(item.get("visual_focus") or ""),
                            "text_anchors": item.get("text_anchors") or [],
                        }
                        for item in semantic_segments
                    ]
                    used_llm = True
            except Exception as exc:
                logger.warning("Storyboard analysis LLM fallback unavailable: {}", exc)

    semantic_count = len(units) or 1
    if director_mode == "custom":
        from pixelle_video.utils.storyboard_split import pack_semantic_units
        units = pack_semantic_units(units, int(target_count or request.scene_count))

    analyzed_units = _storyboard_analysis_units(units, semantic_metadata=semantic_metadata)
    warnings = _storyboard_analysis_warnings(analyzed_units)
    char_count = sum(int(unit["chars"]) for unit in analyzed_units)
    rhythm_count = max(1, min(100, round(char_count / _density_chars_per_scene(density))))
    actual_count = len(analyzed_units) or 1
    if target_count is not None and actual_count != int(target_count):
        warnings.append(f"目标 {int(target_count)} 镜，实际采用 {actual_count} 个自然语义镜头")
    return {
        "success": True,
        "sourceText": source,
        "splitType": split_type,
        "segmentationMode": segmentation_mode,
        "directorMode": director_mode,
        "density": density,
        "targetSceneCount": target_count,
        "usedLlm": used_llm,
        "semanticSceneCount": semantic_count,
        "rhythmSceneCount": rhythm_count,
        "recommendedSceneCount": semantic_count,
        "actualSceneCount": actual_count,
        "charCount": char_count,
        "estimatedDurationSeconds": round(max(1, char_count / 260 * 60), 1),
        "units": analyzed_units,
        "semanticUnits": analyzed_units,
        "warnings": warnings,
    }


def _script_scene_response(
    *,
    index: int,
    narration: str,
    visual_prompt: str,
    visual_focus: str,
    text_anchors: list[str],
) -> dict[str, Any]:
    """Build a script scene while keeping the legacy response shape for empty metadata."""
    scene: dict[str, Any] = {
        "id": index + 1,
        "ttsText": narration,
        "visualPrompt": visual_prompt,
    }
    if visual_focus:
        scene["visualFocus"] = visual_focus
    if text_anchors:
        scene["textAnchors"] = text_anchors
    return scene


@router.post("/generate-script")
async def generate_script(request: GenerateScriptRequest, pixelle_video: PixelleVideoDep):
    """Generate editable scene narration and visual prompts through the real LLM."""
    try:
        _ensure_llm_configured()

        narrations, visual_focuses, text_anchor_hints = await _narrations_and_visual_focus_from_confirmed_copy(
            request,
            pixelle_video.llm,
        )
        semantic_units = _storyboard_analysis_units(
            narrations,
            semantic_metadata=[
                {"visual_focus": focus, "text_anchors": text_anchor_hints[index] if index < len(text_anchor_hints) else []}
                for index, focus in enumerate(visual_focuses)
            ],
        )
        text_anchors = [unit.get("textAnchors", []) for unit in semantic_units]
        image_prompts = await generate_image_prompts(
            llm_service=pixelle_video.llm,
            narrations=narrations,
            min_words=20,
            max_words=80,
            style_prefix=request.promptPrefix or "",
            visual_focuses=visual_focuses,
            text_anchors=text_anchors,
        )
        data = [
            _script_scene_response(
                index=index,
                narration=narration,
                visual_prompt=image_prompts[index] if index < len(image_prompts) else "",
                visual_focus=semantic_units[index].get("visualFocus", "") if index < len(semantic_units) else "",
                text_anchors=semantic_units[index].get("textAnchors", []) if index < len(semantic_units) else [],
            )
            for index, narration in enumerate(narrations)
        ]
        return {"success": True, "data": data}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
