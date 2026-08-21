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
Content generation utility functions

Pure/stateless functions for generating content using LLM.
These functions are reusable across different pipelines.
"""

import json
import re
from typing import List, Literal, Optional

from loguru import logger

_NARRATION_PREFIX_PATTERNS = [
    re.compile(r"^\s*[\(\（\[]?\s*\d{1,3}\s*[\)\）\]]\s*[、,，.．:：\-]?\s*"),
    re.compile(r"^\s*\d{1,3}\s*[、,，.．:：\-]\s*"),
    re.compile(r"^\s*第\s*[\d一二三四五六七八九十百千万]+\s*(?:句|段|条|部分|幕|镜|个)?\s*[、,，.．:：\-]\s*"),
    re.compile(r"^\s*(?:旁白|分镜|镜头|场景)\s*[\d一二三四五六七八九十百千万]+\s*[、,，.．:：\-]\s*"),
    re.compile(r"^\s*(?:scene|storyboard|narration|segment)\s*\d{1,3}\s*[.:\-]\s*", re.IGNORECASE),
]


def clean_narration_text(text: str) -> str:
    """Remove speakable ordering labels before narration text reaches TTS."""
    cleaned = str(text).strip()

    for _ in range(3):
        previous = cleaned
        for pattern in _NARRATION_PREFIX_PATTERNS:
            cleaned = pattern.sub("", cleaned, count=1).strip()
        if cleaned == previous:
            break

    return cleaned


def _clean_narrations(narrations: List[str]) -> List[str]:
    return [clean_narration_text(narration) for narration in narrations]


async def generate_title(
    llm_service,
    content: str,
    strategy: Literal["auto", "direct", "llm"] = "auto",
    max_length: int = 15
) -> str:
    """
    Generate title from content
    
    Args:
        llm_service: LLM service instance
        content: Source content (topic or script)
        strategy: Generation strategy
            - "auto": Auto-decide based on content length (default)
            - "direct": Use content directly (truncated if needed)
            - "llm": Always use LLM to generate title
        max_length: Maximum title length (default: 15)
    
    Returns:
        Generated title
    """
    if strategy == "direct":
        content = content.strip()
        return content[:max_length] if len(content) > max_length else content
    
    if strategy == "auto":
        if len(content.strip()) <= 15:
            return content.strip()
        # Fall through to LLM
    
    # Use LLM to generate title
    from pixelle_video.prompts import build_title_generation_prompt
    
    # Pass max_length to prompt so LLM knows the character limit
    prompt = build_title_generation_prompt(content, max_length=max_length)
    response = await llm_service(prompt, temperature=0.7, max_tokens=50)
    
    # Clean up response
    title = response.strip()
    
    # Remove quotes if present
    if title.startswith('"') and title.endswith('"'):
        title = title[1:-1]
    if title.startswith("'") and title.endswith("'"):
        title = title[1:-1]
    
    # Remove trailing punctuation
    title = title.rstrip('.,!?;:\'"')
    
    # Safety: if still over limit, truncate smartly
    if len(title) > max_length:
        # Try to truncate at word boundary
        truncated = title[:max_length]
        last_space = truncated.rfind(' ')
        
        # Only use word boundary if it's not too far back (at least 60% of max_length)
        if last_space > max_length * 0.6:
            title = truncated[:last_space]
        else:
            title = truncated
        
        # Remove any trailing punctuation after truncation
        title = title.rstrip('.,!?;:\'"')
    
    logger.debug(f"Generated title: '{title}' (length: {len(title)})")
    return title


# Large scene counts must not rely on a single LLM JSON array.
# ~12 items keeps output within common token budgets and model reliability.
_NARRATION_BATCH_SIZE = 12
_NARRATION_TOPUP_ROUNDS = 4


async def generate_narrations_from_topic(
    llm_service,
    topic: str,
    n_scenes: int = 5,
    min_words: int = 5,
    max_words: int = 20,
    batch_size: int = _NARRATION_BATCH_SIZE,
) -> List[str]:
    """
    Generate narrations from topic using LLM.

    Large ``n_scenes`` values are generated in batches with automatic top-up
    when a batch returns fewer items than requested (common at 50–100 scenes).
    """
    from pixelle_video.prompts import build_topic_narration_prompt

    logger.info(f"Generating {n_scenes} narrations from topic: {topic}")
    return await _generate_narrations_batched(
        llm_service,
        source_label="topic",
        source_text=topic,
        n_scenes=n_scenes,
        min_words=min_words,
        max_words=max_words,
        batch_size=batch_size,
        prompt_builder=lambda count: build_topic_narration_prompt(
            topic=topic,
            n_storyboard=count,
            min_words=min_words,
            max_words=max_words,
        ),
    )


async def generate_narrations_from_content(
    llm_service,
    content: str,
    n_scenes: int = 5,
    min_words: int = 5,
    max_words: int = 20,
    batch_size: int = _NARRATION_BATCH_SIZE,
) -> List[str]:
    """
    Generate narrations from user-provided content using LLM.

    Same batch + top-up strategy as topic mode for large scene counts.
    """
    from pixelle_video.prompts import build_content_narration_prompt

    logger.info(f"Generating {n_scenes} narrations from content ({len(content)} chars)")
    return await _generate_narrations_batched(
        llm_service,
        source_label="content",
        source_text=content,
        n_scenes=n_scenes,
        min_words=min_words,
        max_words=max_words,
        batch_size=batch_size,
        prompt_builder=lambda count: build_content_narration_prompt(
            content=content,
            n_storyboard=count,
            min_words=min_words,
            max_words=max_words,
        ),
    )


async def _generate_narrations_batched(
    llm_service,
    *,
    source_label: str,
    source_text: str,
    n_scenes: int,
    min_words: int,
    max_words: int,
    batch_size: int,
    prompt_builder,
) -> List[str]:
    target = max(1, int(n_scenes or 1))
    size = max(1, min(int(batch_size or _NARRATION_BATCH_SIZE), 30))
    collected: List[str] = []
    total_batches = (target + size - 1) // size

    for batch_index, start in enumerate(range(0, target, size), start=1):
        count = min(size, target - start)
        logger.info(
            "Narration batch {}/{}: requesting {} items ({} progress {}/{})",
            batch_index,
            total_batches,
            count,
            source_label,
            len(collected),
            target,
        )
        batch_prompt = prompt_builder(count)
        batch_prompt = _append_batch_context(
            batch_prompt,
            batch_index=batch_index,
            total_batches=total_batches,
            global_start=start + 1,
            global_end=start + count,
            total_scenes=target,
            count=count,
            previous_tail=collected[-4:],
            source_label=source_label,
            source_text=source_text,
        )
        chunk = await _generate_narration_chunk_with_topup(
            llm_service,
            base_prompt=batch_prompt,
            n_scenes=count,
            previous_tail=collected[-4:],
            source_label=source_label,
            source_text=source_text,
            min_words=min_words,
            max_words=max_words,
        )
        collected.extend(chunk)

    narrations = _clean_narrations(collected[:target])
    if len(narrations) < target:
        # Last-resort global top-up across the whole list (rare after per-batch top-up).
        missing = target - len(narrations)
        logger.warning(
            "After batches still short {}/{} narrations; global top-up for {}",
            len(narrations),
            target,
            missing,
        )
        extra = await _topup_narrations(
            llm_service,
            need=missing,
            previous_tail=narrations[-6:],
            source_label=source_label,
            source_text=source_text,
            min_words=min_words,
            max_words=max_words,
            context_note=f"全片共 {target} 条，已有 {len(narrations)} 条，请补齐剩余。",
        )
        narrations = _clean_narrations((narrations + extra)[:target])

    if len(narrations) < target:
        raise ValueError(
            f"Expected {target} narrations, got only {len(narrations)} "
            f"(batch generation + top-up still incomplete)"
        )

    logger.info(f"Generated {len(narrations)} narrations successfully")
    return narrations


def _append_batch_context(
    prompt: str,
    *,
    batch_index: int,
    total_batches: int,
    global_start: int,
    global_end: int,
    total_scenes: int,
    count: int,
    previous_tail: List[str],
    source_label: str,
    source_text: str,
) -> str:
    if total_batches <= 1:
        return prompt
    tail_block = "\n".join(f"- {text}" for text in previous_tail) if previous_tail else "（无，这是第一批）"
    source_preview = str(source_text or "").strip()
    if len(source_preview) > 800:
        source_preview = source_preview[:800] + "…"
    return (
        f"{prompt}\n\n"
        f"# Batch Generation Context (IMPORTANT)\n"
        f"This is batch {batch_index}/{total_batches} of a longer {total_scenes}-storyboard script.\n"
        f"Generate EXACTLY {count} narrations for storyboards {global_start}–{global_end} only.\n"
        f"Continue the narrative arc; do not restart the intro or renumber from 1.\n"
        f"Source ({source_label}) preview:\n{source_preview}\n\n"
        f"Previous narrations (for continuity only — do not repeat):\n{tail_block}\n"
    )


async def _generate_narration_chunk_with_topup(
    llm_service,
    *,
    base_prompt: str,
    n_scenes: int,
    previous_tail: List[str],
    source_label: str,
    source_text: str,
    min_words: int,
    max_words: int,
) -> List[str]:
    """Request one chunk; if short, top-up until full or rounds exhausted."""
    result = await _request_narration_json(llm_service, base_prompt, n_scenes)
    narrations = _coerce_narration_list(result)

    if len(narrations) > n_scenes:
        logger.warning(
            "Chunk returned {} narrations, taking first {}",
            len(narrations),
            n_scenes,
        )
        narrations = narrations[:n_scenes]

    round_index = 0
    while len(narrations) < n_scenes and round_index < _NARRATION_TOPUP_ROUNDS:
        need = n_scenes - len(narrations)
        round_index += 1
        logger.warning(
            "Chunk short ({}/{}), top-up round {} for {} more",
            len(narrations),
            n_scenes,
            round_index,
            need,
        )
        extra = await _topup_narrations(
            llm_service,
            need=need,
            previous_tail=(previous_tail + narrations)[-6:],
            source_label=source_label,
            source_text=source_text,
            min_words=min_words,
            max_words=max_words,
            context_note=(
                f"本批目标 {n_scenes} 条，已有 {len(narrations)} 条，"
                f"请再写恰好 {need} 条，承接上文、勿重复。"
            ),
        )
        if not extra:
            break
        # Deduplicate against immediate prior lines while preserving order.
        seen = {text.casefold() for text in narrations[-8:]}
        for item in extra:
            key = item.casefold()
            if key in seen:
                continue
            narrations.append(item)
            seen.add(key)
            if len(narrations) >= n_scenes:
                break

    if len(narrations) < n_scenes:
        if narrations:
            # Defer hard failure: outer global top-up can still complete the list.
            logger.warning(
                "Batch incomplete after top-up: {}/{}; deferring to global top-up",
                len(narrations),
                n_scenes,
            )
            return narrations
        raise ValueError(
            f"Expected {n_scenes} narrations in batch, got only {len(narrations)}"
        )
    return narrations[:n_scenes]


async def _topup_narrations(
    llm_service,
    *,
    need: int,
    previous_tail: List[str],
    source_label: str,
    source_text: str,
    min_words: int,
    max_words: int,
    context_note: str,
) -> List[str]:
    need = max(1, int(need))
    tail_block = "\n".join(f"- {text}" for text in previous_tail) if previous_tail else "（无）"
    source_preview = str(source_text or "").strip()
    if len(source_preview) > 600:
        source_preview = source_preview[:600] + "…"
    prompt = (
        f"你正在补齐短视频旁白列表。\n"
        f"{context_note}\n"
        f"来源类型：{source_label}\n"
        f"来源内容：{source_preview}\n"
        f"每条字数约 {min_words}~{max_words} 字，口语化，适合 TTS。\n"
        f"已有旁白（勿重复）：\n{tail_block}\n\n"
        f"只输出 JSON 对象：{{\"narrations\":[\"旁白1\",...]}}\n"
        f"数组长度必须恰好是 {need}；不要 Markdown、编号或解释。"
    )
    try:
        result = await _request_narration_json(llm_service, prompt, need)
        items = _coerce_narration_list(result)
    except Exception as exc:
        logger.warning("Narration top-up failed: {}", exc)
        return []
    if len(items) > need:
        items = items[:need]
    return _clean_narrations(items)


def _coerce_narration_list(result) -> List[str]:
    """Normalize LLM JSON / list payloads into non-empty narration strings."""
    if isinstance(result, list):
        raw_items = result
    elif isinstance(result, dict):
        raw_items = result.get("narrations")
        if raw_items is None:
            # Some models nest under data/result.
            for key in ("data", "result", "items", "scenes"):
                nested = result.get(key)
                if isinstance(nested, list):
                    raw_items = nested
                    break
                if isinstance(nested, dict) and isinstance(nested.get("narrations"), list):
                    raw_items = nested["narrations"]
                    break
        if raw_items is None:
            raise ValueError("Invalid response format: missing 'narrations' key")
    else:
        raise ValueError("Invalid narration response type")

    if not isinstance(raw_items, list):
        raise ValueError("Invalid response format: 'narrations' must be a list")

    narrations: List[str] = []
    for item in raw_items:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(
                item.get("narration")
                or item.get("text")
                or item.get("content")
                or item.get("ttsText")
                or ""
            ).strip()
        else:
            text = str(item or "").strip()
        if text:
            narrations.append(text)
    return narrations


async def split_narration_script(
    script: str,
    split_mode: Literal["auto", "paragraph", "line", "sentence"] = "auto",
) -> List[str]:
    """
    Split user-provided narration script into segments
    
    Args:
        script: Fixed narration script
        split_mode: Splitting strategy
            - "auto": Split at sentence boundaries and safe pause boundaries for long sentences
            - "paragraph": Split by double newline (\\n\\n), preserve single newlines within paragraphs
            - "line": Split by single newline (\\n), each line is a segment
            - "sentence": Split by sentence-ending punctuation (。.!?！？)
    
    Returns:
        List of narration segments
    """
    logger.info(f"Splitting script (mode={split_mode}, length={len(script)} chars)")
    
    narrations = []

    if split_mode == "auto":
        from pixelle_video.utils.storyboard_split import auto_split_draft

        narrations = auto_split_draft(script)
        logger.info(f"✅ Split script into {len(narrations)} segments (auto semantic/rhythm)")
    elif split_mode == "paragraph":
        # Split by double newline (paragraph mode)
        # Preserve single newlines within paragraphs
        paragraphs = re.split(r'\n\s*\n', script)
        for para in paragraphs:
            # Only strip leading/trailing whitespace, preserve internal newlines
            cleaned = para.strip()
            if cleaned:
                narrations.append(cleaned)
        logger.info(f"✅ Split script into {len(narrations)} segments (by paragraph)")
    
    elif split_mode == "line":
        # Split by single newline (original behavior)
        narrations = [line.strip() for line in script.split('\n') if line.strip()]
        logger.info(f"✅ Split script into {len(narrations)} segments (by line)")
    
    elif split_mode == "sentence":
        # Split by sentence-ending punctuation
        # Supports Chinese (。！？) and English (.!?)
        from pixelle_video.utils.storyboard_split import split_draft_by_rule

        narrations = split_draft_by_rule(script, "sentence")
        logger.info(f"✅ Split script into {len(narrations)} segments (by sentence)")
    
    else:
        # Fallback to the semantic auto splitter
        logger.warning(f"Unknown split_mode '{split_mode}', falling back to 'auto'")
        from pixelle_video.utils.storyboard_split import auto_split_draft

        narrations = auto_split_draft(script)
    
    narrations = _clean_narrations(narrations)

    # Log statistics
    if narrations:
        lengths = [len(s) for s in narrations]
        logger.info(f"   Min: {min(lengths)} chars, Max: {max(lengths)} chars, Avg: {sum(lengths)//len(lengths)} chars")
    
    return narrations


def _normalize_segment_match(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip()


async def segment_narration_semantically(
    llm_service,
    text: str,
    *,
    target_count: int,
    max_chars: int = 52,
) -> list[dict]:
    """Ask the LLM for extractive semantic boundaries and validate them strictly."""
    from pixelle_video.prompts.storyboard_segmentation import (
        STORYBOARD_SEGMENTATION_SYSTEM_PROMPT,
        build_storyboard_segmentation_prompt,
    )

    source = str(text or "").strip()
    if not source:
        return []
    prompt = build_storyboard_segmentation_prompt(
        source,
        target_count=target_count,
        max_chars=max_chars,
    )
    raw = await llm_service(
        prompt=prompt,
        system_prompt=STORYBOARD_SEGMENTATION_SYSTEM_PROMPT,
        temperature=0.1,
        max_tokens=max(500, min(3000, len(source) * 8)),
    )
    payload = _parse_json(str(raw or ""))
    items = payload.get("segments") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("Semantic segmentation response must contain a non-empty segments array")

    segments: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Semantic segmentation items must be objects")
        segment_text = str(item.get("text") or "").strip()
        if not segment_text:
            raise ValueError("Semantic segmentation item text must not be empty")
        segments.append({
            "text": segment_text,
            "boundary_reason": str(item.get("boundary_reason") or "semantic boundary").strip(),
            "visual_focus": str(item.get("visual_focus") or "concrete scene detail").strip(),
            "text_anchors": [
                str(value).strip()
                for value in (item.get("text_anchors") or [])
                if str(value).strip()
            ][:3],
        })

    expected = _normalize_segment_match(source)
    actual = _normalize_segment_match("".join(item["text"] for item in segments))
    if actual != expected:
        raise ValueError("Semantic segmentation changed, omitted, or duplicated source narration")
    if len(segments) > max(1, int(target_count)):
        raise ValueError("Semantic segmentation returned more segments than requested")
    if any(len(re.sub(r"\s+", "", item["text"])) > max_chars for item in segments):
        raise ValueError("Semantic segmentation left an overlong narration segment")
    return segments


_KEYWORD_PALETTE = [
    "#FFD43B",
    "#FF6B6B",
    "#4DABF7",
    "#69DB7C",
    "#DA77F2",
    "#FFA94D",
    "#22B8CF",
    "#F06595",
]


async def generate_highlight_keywords(
    llm_service,
    text: str,
    max_keywords: int = 8,
    style: str = "balanced",
    density: Optional[str] = None,
    avoid_words: Optional[List[str]] = None,
) -> List[dict]:
    """
    Extract highlight keywords (with optional colors) from narration text via LLM.

    Returns a list of dicts: [{"word": str, "color": "#RRGGBB"}, ...]
    Falls back to a simple heuristic if the LLM response cannot be parsed.
    """
    cleaned = str(text or "").strip()
    if not cleaned:
        return []

    max_keywords = _keyword_limit(max_keywords, density)
    avoid = _normalize_keyword_words(avoid_words)
    style_description = {
        "balanced": "均衡选择概念、卖点、情绪和数字信息",
        "concept": "优先选择名词、方法、结论和关键概念",
        "selling_point": "优先选择功能、利益点和差异化卖点",
        "emotion": "优先选择冲突、态度、情绪和记忆点",
        "numeric": "优先选择数字、比例、时间、结果和指标",
        "action": "优先选择建议、动作、结论和行动词",
    }.get(str(style), "均衡选择概念、卖点、情绪和数字信息")
    density_description = {
        "low": "少量高价值关键词，保持字幕画面干净",
        "standard": "适中的关键词数量，适合普通短视频口播",
        "high": "相对密集的关键词，适合卖点或信息密集文案",
    }.get(str(density), "按请求上限选择关键词")
    avoid_text = "、".join(sorted(avoid)) if avoid else "无"
    prompt = f"""你是短视频字幕高亮词提取助手。从下面旁白中提取最值得高亮的关键词/短语。

要求：
1. 只输出 JSON 数组，不要 markdown，不要解释
2. 每项格式：{{"word":"关键词","color":"#RRGGBB"}}
3. 最多 {max_keywords} 个词；{density_description}；{style_description}
4. 关键词必须完整、原样出现在原文中
5. 颜色用醒目高饱和十六进制色，彼此尽量区分
6. 不要标点，不要整句
7. 不要返回这些已选或已展示的词：{avoid_text}

旁白：
{cleaned[:2000]}
"""
    try:
        response = await llm_service(prompt=prompt, temperature=0.3, max_tokens=400)
        raw = str(response or "").strip()
        # Strip optional code fences.
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        # Prefer first JSON array.
        match = re.search(r"\[[\s\S]*\]", raw)
        payload = json.loads(match.group(0) if match else raw)
        if not isinstance(payload, list):
            raise ValueError("keywords payload is not a list")
    except Exception as exc:
        logger.warning(f"LLM keyword extraction failed, using heuristic: {exc}")
        return _heuristic_keywords(cleaned, max_keywords, avoid)

    results: List[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(payload):
        if isinstance(item, str):
            word = item.strip()
            color = _KEYWORD_PALETTE[index % len(_KEYWORD_PALETTE)]
        elif isinstance(item, dict):
            word = str(item.get("word") or item.get("text") or item.get("keyword") or "").strip()
            color = str(item.get("color") or _KEYWORD_PALETTE[index % len(_KEYWORD_PALETTE)]).strip()
        else:
            continue
        if not word or len(word) > 20:
            continue
        # Prefer keywords that actually appear in source text.
        if word not in cleaned and word.casefold() not in cleaned.casefold():
            continue
        key = word.casefold()
        if key in avoid:
            continue
        if key in seen:
            continue
        if not re.fullmatch(r"#?[0-9a-fA-F]{6}", color):
            color = _KEYWORD_PALETTE[index % len(_KEYWORD_PALETTE)]
        if not color.startswith("#"):
            color = f"#{color}"
        results.append({"word": word, "color": color.upper()})
        seen.add(key)
        if len(results) >= max_keywords:
            break

    if not results:
        return _heuristic_keywords(cleaned, max_keywords, avoid)
    logger.info(f"Extracted {len(results)} highlight keywords")
    return results


def _heuristic_keywords(text: str, max_keywords: int, avoid_words: Optional[set[str] | List[str]] = None) -> List[dict]:
    """Lightweight fallback: pick mid-length CJK/English tokens from the text."""
    # English-like tokens
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,16}", text)
    # Sliding CJK windows of length 2–4 prefer natural short keywords.
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    for size in (4, 3, 2):
        for index in range(0, max(0, len(cjk_chars) - size + 1)):
            tokens.append("".join(cjk_chars[index : index + size]))
    avoid = _normalize_keyword_words(avoid_words)
    stop = {
        "我们", "你们", "他们", "这个", "那个", "一个", "可以", "已经",
        "因为", "所以", "如果", "什么", "怎么", "成为", "进行", "以及",
    }
    # Prefer rarer mid-length phrases that appear once.
    ranked = sorted(
        {t for t in tokens if t.casefold() not in stop and t.casefold() not in avoid and 2 <= len(t) <= 6},
        key=lambda t: (-(3 if 2 <= len(t) <= 4 else 1), text.find(t)),
    )
    results: List[dict] = []
    seen_chars: set[str] = set()
    for word in ranked:
        # Light de-duplication so overlapping windows don't flood the list.
        if any(char in seen_chars for char in word) and len(results) >= max_keywords // 2:
            continue
        results.append({"word": word, "color": _KEYWORD_PALETTE[len(results) % len(_KEYWORD_PALETTE)]})
        seen_chars.update(word)
        if len(results) >= max_keywords:
            break
    return results


def _normalize_keyword_words(words: Optional[List[str] | set[str]]) -> set[str]:
    return {
        str(word).strip().casefold()
        for word in list(words or [])[:48]
        if str(word).strip() and len(str(word).strip()) <= 20
    }


def _keyword_limit(max_keywords: int, density: Optional[str]) -> int:
    requested = max(1, min(24, int(max_keywords or 8)))
    if density is None:
        return requested
    density_cap = {
        "low": 4,
        "standard": 8,
        "high": 12,
    }.get(str(density), 8)
    return min(requested, density_cap)


async def generate_image_prompts(
    llm_service,
    narrations: List[str],
    min_words: int = 30,
    max_words: int = 60,
    batch_size: int = 10,
    max_retries: int = 3,
    progress_callback: Optional[callable] = None,
    style_prefix: str = "",
    visual_focuses: Optional[List[str]] = None,
    text_anchors: Optional[List[List[str]]] = None,
) -> List[str]:
    """Generate one strict English visual prompt for every narration.

    Director rules are sent as a real system message. Only the current
    narration batch and count constraints are sent as user content.
    """
    from pixelle_video.prompts import (
        build_image_prompt_prompt,
        build_image_prompt_system_prompt,
    )

    if not narrations:
        return []
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    logger.info(
        "Generating image prompts for {} narrations (batch_size={})",
        len(narrations),
        batch_size,
    )
    batches = [narrations[i : i + batch_size] for i in range(0, len(narrations), batch_size)]
    focus_values = list(visual_focuses or [])
    if focus_values and len(focus_values) != len(narrations):
        raise ValueError("visual_focuses must align one-to-one with narrations")
    focus_batches = (
        [focus_values[i : i + batch_size] for i in range(0, len(focus_values), batch_size)]
        if focus_values
        else [[] for _ in batches]
    )
    anchor_values = list(text_anchors or [])
    if anchor_values and len(anchor_values) != len(narrations):
        raise ValueError("text_anchors must align one-to-one with narrations")
    anchor_batches = (
        [anchor_values[i : i + batch_size] for i in range(0, len(anchor_values), batch_size)]
        if anchor_values
        else [[] for _ in batches]
    )
    all_prompts: List[str] = []
    retry_limit = max(1, int(max_retries or 1))
    system_prompt = build_image_prompt_system_prompt(style_prefix)
    
    for batch_idx, batch_narrations in enumerate(batches, 1):
        logger.info(
            "Processing image prompt batch {}/{} ({} narrations)",
            batch_idx,
            len(batches),
            len(batch_narrations),
        )
        batch_focuses = focus_batches[batch_idx - 1]
        batch_anchors = anchor_batches[batch_idx - 1]
        for attempt in range(1, retry_limit + 1):
            try:
                prompt = build_image_prompt_prompt(
                    narrations=batch_narrations,
                    min_words=min_words,
                    max_words=max_words,
                    visual_focuses=batch_focuses,
                    text_anchors=batch_anchors,
                    batch_index=batch_idx,
                    batch_count=len(batches),
                    completed_count=len(all_prompts),
                )
                response = await llm_service(
                    system_prompt=system_prompt,
                    prompt=prompt,
                    temperature=0.7,
                    max_tokens=8192,
                )
                raw = str(response or "").strip()
                batch_prompts = _parse_image_prompt_response(raw)["image_prompts"]
                if len(batch_prompts) != len(batch_narrations):
                    raise ValueError(
                        f"image prompt count mismatch: expected {len(batch_narrations)}, "
                        f"got {len(batch_prompts)}"
                    )
                all_prompts.extend(batch_prompts)
                if progress_callback:
                    progress_callback(
                        len(all_prompts),
                        len(narrations),
                        f"Batch {batch_idx}/{len(batches)} completed",
                    )
                break
            except Exception as exc:
                logger.warning(
                    "Image prompt batch {}/{} attempt {}/{} failed: {}",
                    batch_idx,
                    len(batches),
                    attempt,
                    retry_limit,
                    exc,
                )
                if attempt >= retry_limit:
                    raise

    logger.info("Generated {} image prompts", len(all_prompts))
    return all_prompts


def _stringify_image_prompt_items(items: list) -> Optional[List[str]]:
    prompts: List[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            prompts.append(item.strip())
            continue
        if isinstance(item, dict):
            for key in ("image_prompt", "prompt", "visual_prompt", "text"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    prompts.append(value.strip())
                    break
            else:
                return None
            continue
        return None
    return prompts or None


def _coerce_image_prompt_list(payload) -> Optional[List[str]]:
    """Accept both ``{"image_prompts":[...]}`` and a bare JSON string array."""
    if isinstance(payload, list):
        return _stringify_image_prompt_items(payload)
    if not isinstance(payload, dict):
        return None
    for key in ("image_prompts", "prompts", "data", "images"):
        value = payload.get(key)
        if isinstance(value, list):
            return _stringify_image_prompt_items(value)
    return None


def _parse_image_prompt_response(text: str) -> dict[str, List[str]]:
    """Parse model output into ``{"image_prompts": [...]}``.

    Models frequently return a bare JSON array, omit commas between prompts,
    or wrap a valid array in a broken object. All of those must still work.
    """
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("empty image prompt response")
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()

    payload = None
    parse_error: Exception | None = None
    try:
        payload = _loads_model_json(raw)
    except json.JSONDecodeError as exc:
        parse_error = exc
        try:
            payload = _parse_json(raw)
        except json.JSONDecodeError:
            payload = None

    prompts = _coerce_image_prompt_list(payload)
    if not prompts:
        prompts = _recover_image_prompts(raw)
    if not prompts:
        logger.warning(
            "Image prompt JSON parse failed ({}); payload_type={}: {}",
            parse_error,
            type(payload).__name__,
            raw[:800],
        )
        raise ValueError(
            "画面提示词 JSON 无法解析。模型输出不是可用的提示词列表，请再试一次。"
        ) from parse_error
    return {"image_prompts": prompts}


def _repair_unescaped_json_quotes(text: str) -> str:
    """Repair quotes inside model-generated JSON string values.

    Image prompts often contain short quoted evidence such as ``"MONDAY"``.
    Models occasionally omit the backslash, making otherwise recoverable JSON
    fail with ``Expecting ',' delimiter``. A quote is a string terminator only
    when the next significant character is valid JSON structure; otherwise it
    is treated as literal prompt text and escaped.
    """
    source = str(text or "")
    output: list[str] = []
    in_string = False
    escaped = False
    for index, char in enumerate(source):
        if not in_string:
            output.append(char)
            if char == '"':
                in_string = True
            continue
        if escaped:
            output.append(char)
            escaped = False
            continue
        if char == "\\":
            output.append(char)
            escaped = True
            continue
        if char != '"':
            output.append(char)
            continue
        remainder = source[index + 1 :]
        # A structural quote is followed by JSON punctuation and, for a
        # comma/colon, another JSON token. This avoids mistaking prose such as
        # ``marked "MONDAY", then`` for the end of the surrounding string.
        # Adjacent long quoted spans ("prompt one"\n"prompt two") are also
        # structural: models often omit the comma between array strings.
        next_string = re.match(r'\s*"((?:\\.|[^"\\])*)"', remainder)
        next_looks_like_value = bool(
            next_string
            and (
                " " in next_string.group(1)
                or "," in next_string.group(1)
                or len(next_string.group(1)) >= 20
            )
        )
        structural = next_looks_like_value or bool(
            re.match(r'\s*(?:[}\]]|,\s*(?:["}\]])|:\s*(?:["\d{\[]))', remainder)
        )
        if structural:
            output.append(char)
            in_string = False
        else:
            output.append("\\\"")
    return "".join(output)


def _escape_control_chars_in_json_strings(text: str) -> str:
    """Escape raw newlines/tabs that models drop inside JSON string values."""
    output: list[str] = []
    in_string = False
    escaped = False
    for char in str(text or ""):
        if not in_string:
            output.append(char)
            if char == '"':
                in_string = True
            continue
        if escaped:
            output.append(char)
            escaped = False
            continue
        if char == "\\":
            output.append(char)
            escaped = True
            continue
        if char == '"':
            output.append(char)
            in_string = False
            continue
        if char == "\n":
            output.append("\\n")
            continue
        if char == "\r":
            output.append("\\r")
            continue
        if char == "\t":
            output.append("\\t")
            continue
        if ord(char) < 32:
            output.append(f"\\u{ord(char):04x}")
            continue
        output.append(char)
    return "".join(output)


def _insert_missing_commas_between_json_values(text: str) -> str:
    """Insert commas between adjacent JSON values, e.g. ``"a"\\n"b"`` -> ``"a","b"``.

    Some models pretty-print ``image_prompts`` one string per line and omit the
    comma. That surfaces as ``Expecting ',' delimiter: line N column 1``.
    """
    output: list[str] = []
    in_string = False
    escaped = False
    for char in str(text or ""):
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                in_string = False
            continue
        if char == '"':
            index = len(output) - 1
            while index >= 0 and output[index] in " \t\n\r":
                index -= 1
            if index >= 0 and output[index] in '"]}':
                output.append(",")
            in_string = True
            output.append(char)
            continue
        output.append(char)
    return "".join(output)


def _repair_model_json(text: str) -> str:
    repaired = _repair_unescaped_json_quotes(text)
    repaired = _escape_control_chars_in_json_strings(repaired)
    repaired = _insert_missing_commas_between_json_values(repaired)
    return re.sub(r",\s*([}\]])", r"\1", repaired)


def _recover_image_prompts(text: str) -> Optional[List[str]]:
    """Pull complete prompt strings out of a broken ``image_prompts`` array."""
    repaired = _repair_model_json(str(text or ""))
    marker = re.search(r'"image_prompts"\s*:\s*\[', repaired)
    if not marker:
        return None
    items: List[str] = []
    for match in re.finditer(r'"((?:\\.|[^"\\])*)"', repaired[marker.end() :]):
        value = match.group(1)
        try:
            value = json.loads(f'"{value}"')
        except json.JSONDecodeError:
            value = value.replace('\\"', '"').replace("\\n", "\n")
        value = str(value).strip()
        if not value or value == "image_prompts":
            continue
        items.append(value)
    return items or None


def _loads_model_json(text: str):
    """Load strict JSON first, then recover common LLM quoting mistakes."""
    raw = str(text or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as strict_error:
        repaired = _repair_model_json(raw)
        if repaired != raw:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
        raise strict_error


async def generate_video_prompts(
    llm_service,
    narrations: List[str],
    min_words: int = 30,
    max_words: int = 60,
    batch_size: int = 10,
    max_retries: int = 3,
    progress_callback: Optional[callable] = None
) -> List[str]:
    """
    Generate video prompts from narrations (with batching and retry)
    
    Args:
        llm_service: LLM service instance
        narrations: List of narrations
        min_words: Min video prompt length
        max_words: Max video prompt length
        batch_size: Max narrations per batch (default: 10)
        max_retries: Max retry attempts per batch (default: 3)
        progress_callback: Optional callback(completed, total, message) for progress updates
    
    Returns:
        List of video prompts (base prompts, without prefix applied)
    """
    from pixelle_video.prompts.video_generation import build_video_prompt_prompt
    
    logger.info(f"Generating video prompts for {len(narrations)} narrations (batch_size={batch_size})")
    
    # Split narrations into batches
    batches = [narrations[i:i + batch_size] for i in range(0, len(narrations), batch_size)]
    logger.info(f"Split into {len(batches)} batches")
    
    all_prompts = []
    
    # Process each batch
    for batch_idx, batch_narrations in enumerate(batches, 1):
        logger.info(f"Processing batch {batch_idx}/{len(batches)} ({len(batch_narrations)} narrations)")
        
        # Retry logic for this batch
        for attempt in range(1, max_retries + 1):
            try:
                # Generate prompts for this batch
                prompt = build_video_prompt_prompt(
                    narrations=batch_narrations,
                    min_words=min_words,
                    max_words=max_words
                )
                
                response = await llm_service(
                    prompt=prompt,
                    temperature=0.7,
                    max_tokens=8192
                )
                
                logger.debug(f"Batch {batch_idx} attempt {attempt}: LLM response length: {len(response)} chars")
                
                # Parse JSON
                result = _parse_json(response)
                
                if "video_prompts" not in result:
                    raise KeyError("Invalid response format: missing 'video_prompts'")
                
                batch_prompts = result["video_prompts"]
                
                # Validate batch result
                if len(batch_prompts) != len(batch_narrations):
                    raise ValueError(
                        f"Prompt count mismatch: expected {len(batch_narrations)}, got {len(batch_prompts)}"
                    )
                
                # Success - add to all_prompts
                all_prompts.extend(batch_prompts)
                logger.info(f"✓ Batch {batch_idx} completed: {len(batch_prompts)} video prompts")
                
                # Report progress
                if progress_callback:
                    completed = len(all_prompts)
                    total = len(narrations)
                    progress_callback(completed, total, f"Batch {batch_idx}/{len(batches)} completed")
                
                break  # Success, move to next batch
            
            except Exception as e:
                logger.warning(f"✗ Batch {batch_idx} attempt {attempt} failed: {e}")
                if attempt >= max_retries:
                    raise
                logger.info(f"Retrying batch {batch_idx}...")
    
    logger.info(f"✅ Generated {len(all_prompts)} video prompts")
    return all_prompts


def _narration_max_tokens(n_scenes: int) -> int:
    """Scale completion budget with item count; cap at common provider limits."""
    # ~80–120 completion tokens per short Chinese narration + JSON overhead.
    estimated = 512 + max(1, int(n_scenes)) * 120
    return max(1024, min(8192, estimated))


async def _request_narration_json(llm_service, prompt: str, n_scenes: int):
    """Request narration JSON, retrying when a provider omits final content.

    DeepSeek V4 thinking mode can consume the entire max_tokens budget as
    reasoning_tokens and return empty content. We disable thinking and size
    max_tokens by batch length so the final JSON answer is actually produced.
    """
    token_budget = _narration_max_tokens(n_scenes)
    compact_prompt = (
        f"请生成恰好 {n_scenes} 条适合短视频 TTS 的旁白。\n"
        f"主题/要求：见下方原始说明。\n"
        f"只输出 JSON 对象，格式严格为：{{\"narrations\":[\"旁白1\",\"旁白2\",...]}}\n"
        f"数组长度必须是 {n_scenes}；不要 Markdown、不要编号、不要解释。\n\n"
        f"原始要求：\n{prompt}"
    )
    retry_prompt = (
        f"{prompt}\n\n上一次响应未提供可解析的最终结果。请立即输出 {n_scenes} 条旁白，"
        '只能输出 JSON 对象：{"narrations":["..."]}，不要思考过程、Markdown 或解释。'
    )
    attempts = (
        (prompt, 0.7, token_budget),
        (compact_prompt, 0.3, token_budget),
        (retry_prompt, 0.1, min(8192, token_budget + 1024)),
    )
    last_error: Exception | None = None
    best_partial: Optional[List[str]] = None
    for attempt, (request_prompt, temperature, max_tokens) in enumerate(attempts, start=1):
        response = await llm_service(
            prompt=request_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking=False,
        )
        raw = str(response or "").strip()
        logger.debug(
            "LLM narration response (attempt {}, {} chars): {}",
            attempt,
            len(raw),
            raw[:200],
        )
        if not raw:
            last_error = ValueError("empty LLM content")
            logger.warning("Narration attempt {} returned empty content", attempt)
            continue
        try:
            parsed = _parse_json(raw)
            # Prefer a successful parse even if slightly short; top-up handles rest.
            try:
                items = _coerce_narration_list(parsed)
            except ValueError:
                return parsed
            if items:
                if len(items) >= n_scenes:
                    return {"narrations": items[:n_scenes]}
                # Any non-empty partial is usable — outer batch top-up fills the rest.
                logger.warning(
                    "Narration attempt {} returned partial list {}/{}",
                    attempt,
                    len(items),
                    n_scenes,
                )
                return {"narrations": items}
            return parsed
        except json.JSONDecodeError as exc:
            last_error = exc
            recovered = _recover_truncated_narration_json(raw)
            if recovered:
                if len(recovered) >= n_scenes:
                    return {"narrations": recovered[:n_scenes]}
                if best_partial is None or len(recovered) > len(best_partial):
                    best_partial = recovered
            fallback = _extract_narrations_fallback(raw, n_scenes)
            if fallback is not None:
                logger.warning(
                    "Narration attempt {} JSON parse failed; recovered {} lines via fallback",
                    attempt,
                    len(fallback),
                )
                if len(fallback) >= n_scenes:
                    return {"narrations": fallback[:n_scenes]}
                if best_partial is None or len(fallback) > len(best_partial):
                    best_partial = fallback
    if best_partial:
        logger.warning(
            "Returning best partial narration list ({} items, target {})",
            len(best_partial),
            n_scenes,
        )
        return {"narrations": best_partial}
    raise ValueError("LLM 未返回可解析的旁白 JSON，请检查模型配置或稍后重试") from last_error


def _recover_truncated_narration_json(text: str) -> Optional[List[str]]:
    """Recover complete string items from a truncated narrations JSON array."""
    raw = str(text or "")
    marker = re.search(r'"narrations"\s*:\s*\[', raw)
    if not marker:
        # Bare array of strings.
        bracket = raw.find("[")
        if bracket < 0:
            return None
        body = raw[bracket + 1 :]
    else:
        body = raw[marker.end() :]

    items: List[str] = []
    for match in re.finditer(r'"((?:\\.|[^"\\])*)"', body):
        # Stop if we hit a key-like token after the array should have ended.
        value = match.group(1)
        try:
            # Unescape JSON string content.
            value = json.loads(f'"{value}"')
        except json.JSONDecodeError:
            value = value.replace('\\"', '"').replace("\\n", "\n")
        value = str(value).strip()
        if not value:
            continue
        # Skip accidental keys if model continued after the array.
        if value in {"narrations", "text", "content"}:
            continue
        items.append(value)
    return items or None


def _extract_narrations_fallback(text: str, n_scenes: int) -> Optional[List[str]]:
    """Best-effort recovery when the model returns plain lines instead of JSON."""
    lines: List[str] = []
    for raw_line in str(text or "").splitlines():
        line = clean_narration_text(raw_line)
        if not line:
            continue
        # Skip obvious non-narration scaffolding
        if line.startswith("{") or line.startswith("}") or line.startswith("```"):
            continue
        if line.lower() in {"narrations", "json"}:
            continue
        lines.append(line)
    if len(lines) >= n_scenes:
        return lines[:n_scenes]
    # Accept any non-empty partial so batch top-up can fill the rest.
    if lines:
        return lines
    return None


def _parse_json(text: str):
    """
    Parse JSON from text, with fallback to extract JSON from markdown code blocks
    
    Args:
        text: Text containing JSON
        
    Returns:
        Parsed JSON dict
        
    Raises:
        json.JSONDecodeError: If no valid JSON found
    """
    raw = str(text or "").strip()
    if not raw:
        raise json.JSONDecodeError("No valid JSON found", raw, 0)

    # Normalize common model artifacts
    normalized = (
        raw.replace("\ufeff", "")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    candidates = [normalized, raw]
    candidates.extend(re.findall(r"```(?:json)?\s*([\s\S]+?)\s*```", normalized, re.IGNORECASE))
    # Prefer the largest {...} / [...] span when the model adds prose.
    for pattern in (r"(\{[\s\S]*\})", r"(\[[\s\S]*\])"):
        match = re.search(pattern, normalized)
        if match:
            candidates.append(match.group(1))

    decoder = json.JSONDecoder()
    seen = set()
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return _loads_model_json(candidate)
        except json.JSONDecodeError:
            pass
        # Trailing-comma repair (common model glitch)
        repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
        if repaired != candidate:
            try:
                return _loads_model_json(repaired)
            except json.JSONDecodeError:
                pass
        for index, char in enumerate(candidate):
            if char not in "[{":
                continue
            try:
                value, _ = decoder.raw_decode(candidate[index:])
                if isinstance(value, (dict, list)):
                    return value
            except json.JSONDecodeError:
                continue
    raise json.JSONDecodeError("No valid JSON found", raw, 0)
