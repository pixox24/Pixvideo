"""Quick Create copy-draft, storyboard analysis, and script endpoints."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.routers.workbench_support import (
    AUTO_MAX_CHARS_PER_SEGMENT,
    GenerateCopyDraftRequest,
    GenerateScriptRequest,
    StoryboardAnalyzeRequest,
    _char_count_phrase,
    _density_chars_per_scene,
    _ensure_llm_configured,
    _format_segmented_draft,
    _narrations_and_visual_focus_from_confirmed_copy,
    _normalize_director_mode,
    _normalize_draft_mode,
    _normalize_segmentation_mode,
    _normalize_split_type,
    _normalize_storyboard_density,
    _per_storyboard_word_range,
    _should_soft_expand,
    _storyboard_analysis_units,
    _storyboard_analysis_warnings,
    rebalance_long_units,
    soft_expand_by_pause,
    split_draft_by_rule,
)
from pixelle_video.utils.content_generators import (
    generate_image_prompts,
    generate_narrations_from_topic,
    segment_narration_semantically,
)

router = APIRouter()


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
    overlong = len(re.sub(r"\s+", "", source)) > AUTO_MAX_CHARS_PER_SEGMENT
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
        units = rebalance_long_units(units)

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
