"""Alibaba DashScope-compatible multimodal style analysis."""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

import httpx
from PIL import Image, ImageOps

from pixelle_video.config import config_manager

STYLE_SYSTEM_PROMPT = """你是专业的视觉风格分析器。你的任务是从参考图中提取可迁移、可用于文生图的视觉语言。
只分析媒介、线条、形状、色彩、材质、纹理、光影、构图、镜头语言、空间感和情绪。
严禁把参考图中的具体人物、脸、服装、地点、建筑、物体、品牌、Logo、日期和原图文字写入 style_prefix。
不要输出艺术家姓名来代替风格描述；将其转换成客观视觉特征。
style_prefix 必须是适合拼接到其他场景提示词前面的短英文提示词，80-180 个英文词以内。
只返回 JSON，不要 Markdown，不要解释。"""

STYLE_SCHEMA_HINT = {
    "style_name": "短中文名称",
    "style_prefix": "可复用的英文画风前缀",
    "style_tags": ["最多12个风格标签"],
    "visual_features": {
        "medium": "",
        "linework": "",
        "color_palette": [],
        "lighting": "",
        "composition": "",
        "texture": "",
        "mood": "",
    },
    "content_excluded": [],
    "negative_constraints": ["do not copy the original subject"],
    "confidence": 0.0,
}


def _normalise_base_url(value: str) -> str:
    return str(value or "").rstrip("/")


def prepare_image_data_url(data: bytes, content_type: str | None, *, max_bytes: int, max_pixels: int) -> tuple[str, str]:
    if len(data) > max_bytes:
        raise ValueError("vision_image_too_large")
    try:
        image = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        raise ValueError("vision_image_invalid") from exc
    if image.width * image.height > max_pixels:
        scale = (max_pixels / (image.width * image.height)) ** 0.5
        image = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}", "image/jpeg"


def _parse_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.I)
    if fenced:
        raw = fenced.group(1).strip()
    candidates = [raw]
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start:end + 1])
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError as exc:
            last_error = exc
    raise ValueError("vision_response_invalid") from last_error


def validate_style_result(payload: dict[str, Any]) -> dict[str, Any]:
    prefix = str(payload.get("style_prefix") or "").strip()
    if not prefix:
        raise ValueError("style_prefix_empty")
    tags = [str(item).strip() for item in (payload.get("style_tags") or []) if str(item).strip()][:12]
    features = payload.get("visual_features") if isinstance(payload.get("visual_features"), dict) else {}
    confidence = min(1.0, max(0.0, float(payload.get("confidence") or 0)))
    return {
        "style_name": str(payload.get("style_name") or "未命名画风").strip()[:80],
        "style_prefix": prefix[:1200],
        "style_tags": tags,
        "visual_features": features,
        "content_excluded": [str(v).strip() for v in (payload.get("content_excluded") or []) if str(v).strip()][:20],
        "negative_constraints": [str(v).strip() for v in (payload.get("negative_constraints") or []) if str(v).strip()][:20],
        "confidence": confidence,
    }


def _message_content(response: dict[str, Any]) -> str:
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return str(content or "")


async def analyze_style_image(data: bytes, content_type: str | None = None) -> dict[str, Any]:
    cfg = config_manager.get_vision_understanding_config()
    if not cfg.get("enabled") or not cfg.get("api_key") or not cfg.get("base_url") or not cfg.get("model"):
        raise ValueError("vision_understanding_not_configured")
    image_url, _ = prepare_image_data_url(
        data,
        content_type,
        max_bytes=int(cfg.get("max_image_bytes", 10 * 1024 * 1024)),
        max_pixels=int(cfg.get("max_image_pixels", 16_000_000)),
    )
    prompt = "分析这张参考图的可迁移画风。严格按照以下 JSON 结构返回，不要描述原图具体内容：\n" + json.dumps(STYLE_SCHEMA_HINT, ensure_ascii=False)
    models = [str(cfg["model"])]
    fallback = str(cfg.get("fallback_model") or "").strip()
    if fallback and fallback not in models:
        models.append(fallback)
    last_error: Exception | None = None
    for model in models:
        try:
            async with httpx.AsyncClient(timeout=float(cfg.get("timeout_seconds", 60)), trust_env=False) as client:
                response = await client.post(
                    f"{_normalise_base_url(cfg['base_url'])}/chat/completions",
                    headers={"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "temperature": float(cfg.get("temperature", 0.2)),
                        "messages": [
                            {"role": "system", "content": STYLE_SYSTEM_PROMPT},
                            {"role": "user", "content": [
                                {"type": "image_url", "image_url": {"url": image_url}},
                                {"type": "text", "text": prompt},
                            ]},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                return {**validate_style_result(_parse_json(_message_content(response.json()))), "model": model}
        except Exception as exc:
            last_error = exc
    raise ValueError("vision_model_failed") from last_error
