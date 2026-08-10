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


async def generate_narrations_from_topic(
    llm_service,
    topic: str,
    n_scenes: int = 5,
    min_words: int = 5,
    max_words: int = 20
) -> List[str]:
    """
    Generate narrations from topic using LLM
    
    Args:
        llm_service: LLM service instance
        topic: Topic/theme to generate narrations from
        n_scenes: Number of narrations to generate
        min_words: Minimum narration length
        max_words: Maximum narration length
    
    Returns:
        List of narration texts
    """
    from pixelle_video.prompts import build_topic_narration_prompt
    
    logger.info(f"Generating {n_scenes} narrations from topic: {topic}")
    
    prompt = build_topic_narration_prompt(
        topic=topic,
        n_storyboard=n_scenes,
        min_words=min_words,
        max_words=max_words
    )
    
    result = await _request_narration_json(llm_service, prompt, n_scenes)
    if isinstance(result, list):
        result = {"narrations": result}
    
    if "narrations" not in result:
        raise ValueError("Invalid response format: missing 'narrations' key")
    
    narrations = result["narrations"]
    
    # Validate count
    if len(narrations) > n_scenes:
        logger.warning(f"Got {len(narrations)} narrations, taking first {n_scenes}")
        narrations = narrations[:n_scenes]
    elif len(narrations) < n_scenes:
        raise ValueError(f"Expected {n_scenes} narrations, got only {len(narrations)}")
    
    narrations = _clean_narrations(narrations)
    logger.info(f"Generated {len(narrations)} narrations successfully")
    return narrations


async def generate_narrations_from_content(
    llm_service,
    content: str,
    n_scenes: int = 5,
    min_words: int = 5,
    max_words: int = 20
) -> List[str]:
    """
    Generate narrations from user-provided content using LLM
    
    Args:
        llm_service: LLM service instance
        content: User-provided content
        n_scenes: Number of narrations to generate
        min_words: Minimum narration length
        max_words: Maximum narration length
    
    Returns:
        List of narration texts
    """
    from pixelle_video.prompts import build_content_narration_prompt
    
    logger.info(f"Generating {n_scenes} narrations from content ({len(content)} chars)")
    
    prompt = build_content_narration_prompt(
        content=content,
        n_storyboard=n_scenes,
        min_words=min_words,
        max_words=max_words
    )
    
    result = await _request_narration_json(llm_service, prompt, n_scenes)
    if isinstance(result, list):
        result = {"narrations": result}
    
    if "narrations" not in result:
        raise ValueError("Invalid response format: missing 'narrations' key")
    
    narrations = result["narrations"]
    
    # Validate count
    if len(narrations) > n_scenes:
        logger.warning(f"Got {len(narrations)} narrations, taking first {n_scenes}")
        narrations = narrations[:n_scenes]
    elif len(narrations) < n_scenes:
        raise ValueError(f"Expected {n_scenes} narrations, got only {len(narrations)}")
    
    narrations = _clean_narrations(narrations)
    logger.info(f"Generated {len(narrations)} narrations successfully")
    return narrations


async def split_narration_script(
    script: str,
    split_mode: Literal["paragraph", "line", "sentence"] = "paragraph",
) -> List[str]:
    """
    Split user-provided narration script into segments
    
    Args:
        script: Fixed narration script
        split_mode: Splitting strategy
            - "paragraph": Split by double newline (\\n\\n), preserve single newlines within paragraphs
            - "line": Split by single newline (\\n), each line is a segment
            - "sentence": Split by sentence-ending punctuation (。.!?！？)
    
    Returns:
        List of narration segments
    """
    logger.info(f"Splitting script (mode={split_mode}, length={len(script)} chars)")
    
    narrations = []
    
    if split_mode == "paragraph":
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
        # Use regex to split while keeping sentences intact
        cleaned = re.sub(r'\s+', ' ', script.strip())
        # Split on sentence-ending punctuation, keeping the punctuation with the sentence
        sentences = re.split(r'(?<=[。.!?！？])\s*', cleaned)
        narrations = [s.strip() for s in sentences if s.strip()]
        logger.info(f"✅ Split script into {len(narrations)} segments (by sentence)")
    
    else:
        # Fallback to line mode
        logger.warning(f"Unknown split_mode '{split_mode}', falling back to 'line'")
        narrations = [line.strip() for line in script.split('\n') if line.strip()]
    
    narrations = _clean_narrations(narrations)

    # Log statistics
    if narrations:
        lengths = [len(s) for s in narrations]
        logger.info(f"   Min: {min(lengths)} chars, Max: {max(lengths)} chars, Avg: {sum(lengths)//len(lengths)} chars")
    
    return narrations


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
    progress_callback: Optional[callable] = None
) -> List[str]:
    """
    Generate image prompts from narrations (with batching and retry)
    
    Args:
        llm_service: LLM service instance
        narrations: List of narrations
        min_words: Min image prompt length
        max_words: Max image prompt length
        batch_size: Max narrations per batch (default: 10)
        max_retries: Max retry attempts per batch (default: 3)
        progress_callback: Optional callback(completed, total, message) for progress updates
    
    Returns:
        List of image prompts (base prompts, without prefix applied)
    """
    from pixelle_video.prompts import build_image_prompt_prompt
    
    logger.info(f"Generating image prompts for {len(narrations)} narrations (batch_size={batch_size})")
    
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
                prompt = build_image_prompt_prompt(
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
                
                if "image_prompts" not in result:
                    raise KeyError("Invalid response format: missing 'image_prompts'")
                
                batch_prompts = result["image_prompts"]
                
                # Validate count
                if len(batch_prompts) != len(batch_narrations):
                    error_msg = (
                        f"Batch {batch_idx} prompt count mismatch (attempt {attempt}/{max_retries}):\n"
                        f"  Expected: {len(batch_narrations)} prompts\n"
                        f"  Got: {len(batch_prompts)} prompts"
                    )
                    logger.warning(error_msg)
                    
                    if attempt < max_retries:
                        logger.info(f"Retrying batch {batch_idx}...")
                        continue
                    else:
                        raise ValueError(error_msg)
                
                # Success!
                logger.info(f"✅ Batch {batch_idx} completed successfully ({len(batch_prompts)} prompts)")
                all_prompts.extend(batch_prompts)
                
                # Report progress
                if progress_callback:
                    progress_callback(
                        len(all_prompts),
                        len(narrations),
                        f"Batch {batch_idx}/{len(batches)} completed"
                    )
                
                break
                
            except json.JSONDecodeError as e:
                logger.error(f"Batch {batch_idx} JSON parse error (attempt {attempt}/{max_retries}): {e}")
                if attempt >= max_retries:
                    raise
                logger.info(f"Retrying batch {batch_idx}...")
    
    logger.info(f"✅ Generated {len(all_prompts)} image prompts")
    return all_prompts


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


async def _request_narration_json(llm_service, prompt: str, n_scenes: int):
    """Request narration JSON, retrying once when a provider omits final content."""
    retry_prompt = (
        f"{prompt}\n\n上一次响应未提供可解析的最终结果。请立即输出 {n_scenes} 条旁白，"
        '只能输出 JSON 对象：{"narrations":["..."]}，不要思考过程、Markdown 或解释。'
    )
    last_error = None
    for attempt, request_prompt in enumerate((prompt, retry_prompt)):
        response = await llm_service(
            prompt=request_prompt,
            temperature=0.8 if attempt == 0 else 0.2,
            max_tokens=2000 if attempt == 0 else 4000,
        )
        raw = str(response or "").strip()
        logger.debug("LLM narration response (attempt %s, %s chars): %s", attempt + 1, len(raw), raw[:200])
        try:
            return _parse_json(raw)
        except json.JSONDecodeError as exc:
            last_error = exc
    raise ValueError("LLM 未返回可解析的旁白 JSON，请检查模型配置或稍后重试") from last_error


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
    candidates = [raw]
    candidates.extend(re.findall(r"```(?:json)?\s*([\s\S]+?)\s*```", raw, re.IGNORECASE))
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            return json.loads(candidate)
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
