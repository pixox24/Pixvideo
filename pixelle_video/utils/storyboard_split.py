"""Semantic storyboard packing — mirrors frontend/src/lib/storyboardSplit.ts.

Product rules:
- Scene count follows copy meaning, never equal character slicing.
- Never invent mid-word / mid-phrase hard cuts to hit a target count.
- Soft-expand on pause punctuation may create multi-clip sentences; callers
  using continuous TTS should prefer soft_expand=False.
"""

from __future__ import annotations

import re
from typing import Literal

DraftSplitType = Literal["auto", "paragraph", "line", "sentence"]

STORYBOARD_SCENE_MIN = 1
STORYBOARD_SCENE_MAX = 100
SOFT_EXPAND_MIN_PART = 4
AUTO_MAX_CHARS_PER_SEGMENT = 52
AUTO_MIN_CHARS_PER_SEGMENT = 12
RHYTHM_TARGET_CHARS = 36
RHYTHM_MAX_CHARS = 42

_TERMINAL = re.compile(r"[。！？.!?…]+$")
_PAUSE = re.compile(r"[，,；;]+$")
_ASCII_LETTER = re.compile(r"[A-Za-z]")
_SEMANTIC_BREAK = re.compile(
    r"(?:与此同时|这意味着|从而|并且|同时|而且|但是|不过|因此|所以|如果|虽然|随后|后来|其实|最终|此时|此后|只要|因为|不仅|以及|还是|并|而|但|却|让|把|将|进入|开始|最后|其中)"
)


def clamp_scene_count(value: int, minimum: int = STORYBOARD_SCENE_MIN, maximum: int = STORYBOARD_SCENE_MAX) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return min(maximum, max(minimum, number))


def split_draft_by_rule(text: str, split_type: DraftSplitType = "auto") -> list[str]:
    trimmed = str(text or "").strip()
    if not trimmed:
        return []

    if split_type == "auto":
        return auto_split_draft(trimmed)

    if split_type == "paragraph":
        return [segment.strip() for segment in re.split(r"\n\s*\n", trimmed) if segment.strip()]

    if split_type == "sentence":
        # Keep terminal punctuation with the sentence.
        return _split_sentence_units(trimmed)

    # Explicit line mode
    return [line.strip() for line in re.split(r"\r?\n", trimmed) if line.strip()]


def _meaningful_length(text: str) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def _split_sentence_units(text: str) -> list[str]:
    """Split at sentence punctuation without breaking decimal/date/domain tokens."""
    units: list[str] = []
    buffer: list[str] = []
    source = str(text or "")
    for index, char in enumerate(source):
        if char == "\n":
            if buffer:
                units.append("".join(buffer).strip())
                buffer = []
            continue
        buffer.append(char)
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if char in "。！？!?…":
            if next_char in "。！？!?…":
                continue
            units.append("".join(buffer).strip())
            buffer = []
        elif char == ".":
            # Decimal numbers, dates, domains, and version strings are not boundaries.
            if next_char.isdigit() or next_char == "." or _ASCII_LETTER.fullmatch(next_char or ""):
                continue
            units.append("".join(buffer).strip())
            buffer = []
    if buffer:
        units.append("".join(buffer).strip())
    return [unit for unit in units if unit]


def _split_long_sentence(sentence: str) -> list[str]:
    """Split long narration at pauses, semantic joins, then a bounded beat."""
    if _meaningful_length(sentence) <= RHYTHM_MAX_CHARS:
        return [sentence.strip()]

    pieces = [piece for piece in re.split(r"([，,；;：:]+)", sentence) if piece]
    parts: list[str] = []
    buffer = ""
    for piece in pieces:
        buffer = f"{buffer}{piece}".strip()
        if re.fullmatch(r"[，,；;：:]+", piece):
            parts.append(buffer)
            buffer = ""
    if buffer:
        parts.append(buffer)

    if len(parts) <= 1:
        return _split_by_rhythm(sentence)

    groups: list[str] = []
    buffer = ""
    for part in parts:
        candidate = f"{buffer}{part}".strip()
        if buffer and _meaningful_length(candidate) > RHYTHM_MAX_CHARS:
            groups.append(buffer)
            buffer = part
        else:
            buffer = candidate
    if buffer:
        groups.append(buffer)

    # Avoid creating a tiny tail when the preceding clause is a safe merge.
    if len(groups) > 1 and _meaningful_length(groups[-1]) < AUTO_MIN_CHARS_PER_SEGMENT:
        groups[-2] = f"{groups[-2]}{groups[-1]}"
        groups.pop()
    if any(_meaningful_length(group) > RHYTHM_MAX_CHARS for group in groups):
        return _split_by_rhythm(sentence)
    return groups or [sentence.strip()]


def _split_by_rhythm(text: str) -> list[str]:
    """Guarantee bounded units when copy omitted punctuation.

    Connector boundaries preserve source text and usually match a natural
    visual change. The final fixed-width fallback is deliberately bounded so
    a 60-character unpunctuated sentence cannot become a 14-second scene.
    """
    source = str(text or "").strip()
    if _meaningful_length(source) <= RHYTHM_MAX_CHARS:
        return [source] if source else []

    result: list[str] = []
    cursor = 0
    while _meaningful_length(source[cursor:]) > RHYTHM_MAX_CHARS:
        limit = min(len(source), cursor + RHYTHM_MAX_CHARS)
        candidates: list[int] = []
        for match in re.finditer(r"[，,；;：:。！？!?…]+", source[cursor:limit]):
            position = cursor + match.end()
            if position < limit and len(source) - position >= AUTO_MIN_CHARS_PER_SEGMENT:
                candidates.append(position)
        for match in _SEMANTIC_BREAK.finditer(source, cursor + AUTO_MIN_CHARS_PER_SEGMENT, limit + 1):
            position = match.start()
            if position >= limit or len(source) - position < AUTO_MIN_CHARS_PER_SEGMENT:
                continue
            previous = source[position - 1] if position else ""
            first = source[position] if position < len(source) else ""
            if previous.isascii() and previous.isalnum() and first.isascii() and first.isalnum():
                continue
            candidates.append(position)

        if candidates:
            cut = min(candidates, key=lambda position: abs((position - cursor) - RHYTHM_TARGET_CHARS))
        else:
            # Keep a meaningful tail while staying below the 10-second rhythm
            # threshold used by the analysis warning.
            # ponytail: fixed-width CJK fallback; replace with a tokenizer only if cut quality is measured as a problem.
            cut = min(cursor + RHYTHM_TARGET_CHARS, len(source) - _minimum_tail_length(source, cursor))
            cut = max(cursor + AUTO_MIN_CHARS_PER_SEGMENT, min(cut, limit))
            cut = _move_off_ascii_word(source, cut, cursor + AUTO_MIN_CHARS_PER_SEGMENT, limit)

        if cut <= cursor:
            cut = min(limit, cursor + RHYTHM_TARGET_CHARS)
        result.append(source[cursor:cut].strip())
        cursor = cut

    tail = source[cursor:].strip()
    if tail:
        result.append(tail)
    return result or [source]


def _minimum_tail_length(source: str, cursor: int) -> int:
    """Return a tail size without adding another public tuning parameter."""
    return max(AUTO_MIN_CHARS_PER_SEGMENT, len(source) - cursor - RHYTHM_TARGET_CHARS)


def _move_off_ascii_word(source: str, cut: int, minimum: int, maximum: int) -> int:
    if cut <= 0 or cut >= len(source):
        return cut
    if not (source[cut - 1].isascii() and source[cut - 1].isalnum() and source[cut].isascii() and source[cut].isalnum()):
        return cut
    for candidate in range(cut - 1, minimum - 1, -1):
        if not (source[candidate - 1].isascii() and source[candidate - 1].isalnum() and source[candidate].isascii() and source[candidate].isalnum()):
            return candidate
    for candidate in range(cut + 1, maximum + 1):
        if not (source[candidate - 1].isascii() and source[candidate - 1].isalnum() and source[candidate].isascii() and source[candidate].isalnum()):
            return candidate
    return cut


def auto_split_draft(text: str) -> list[str]:
    """Create safe, duration-aware narration units without rewriting source text."""
    trimmed = str(text or "").strip()
    if not trimmed:
        return []

    sentences = _split_sentence_units(trimmed)
    units: list[str] = []
    for sentence in sentences:
        clean = sentence.strip()
        if clean:
            units.extend(_split_long_sentence(clean))
    return units or [trimmed]


def rebalance_long_units(units: list[str]) -> list[str]:
    """Re-split packed custom units without allowing a long tail to return."""
    result: list[str] = []
    for unit in units:
        clean = str(unit or "").strip()
        if not clean:
            continue
        result.extend(_split_long_sentence(clean) if _meaningful_length(clean) > RHYTHM_MAX_CHARS else [clean])
    return result


def soft_expand_by_pause(units: list[str]) -> list[str]:
    """
    Soft-expand on ，； only when both sides are substantial.

    Preserves the pause mark on the *left* segment so continuous TTS / hold
    boundaries still read as natural clause ends (not mid-word hard cuts).
    """
    expanded: list[str] = []
    for unit in units:
        trimmed = unit.strip()
        if not trimmed:
            continue
        # Split while keeping delimiters
        pieces = re.split(r"([，,；;]+)", trimmed)
        # pieces: [text, delim, text, delim, text, ...]
        parts: list[str] = []
        buf = ""
        for piece in pieces:
            if not piece:
                continue
            if re.fullmatch(r"[，,；;]+", piece):
                buf = (buf + piece).strip()
                if buf:
                    parts.append(buf)
                    buf = ""
            else:
                buf = (buf + piece).strip()
        if buf:
            parts.append(buf)

        if (
            len(parts) > 1
            and all(len(re.sub(r"\s+", "", part)) >= SOFT_EXPAND_MIN_PART for part in parts)
        ):
            expanded.extend(parts)
        else:
            expanded.append(trimmed)
    return expanded


def pack_semantic_units(units: list[str], target_count: int) -> list[str]:
    clean = [unit.strip() for unit in units if unit and unit.strip()]
    if not clean:
        return []

    target = clamp_scene_count(target_count or len(clean))
    if len(clean) == target:
        return clean

    if len(clean) > target:
        packed: list[str] = []
        for index in range(target):
            start = (index * len(clean)) // target
            end = ((index + 1) * len(clean)) // target
            chunk = "".join(clean[start : max(end, start + 1)]).strip()
            if chunk:
                packed.append(chunk)
        return packed

    # Fewer units than target: never invent mid-sentence character cuts.
    return clean


def heal_mid_cuts(segments: list[str]) -> list[str]:
    """
    Merge adjacent segments that look like hard mid-word / mid-phrase cuts.

    Example: ``科学家发`` + ``现，光速…`` → one segment.
    Does not merge when left already ends with terminal or pause punctuation.
    """
    clean = [segment.strip() for segment in segments if segment and segment.strip()]
    if len(clean) < 2:
        return clean

    merged: list[str] = []
    index = 0
    while index < len(clean):
        current = clean[index]
        while index + 1 < len(clean):
            nxt = clean[index + 1]
            if _should_merge_mid_cut(current, nxt):
                current = f"{current}{nxt}"
                index += 1
                continue
            break
        merged.append(current)
        index += 1
    return merged


def _should_merge_mid_cut(left: str, right: str) -> bool:
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return False
    if _TERMINAL.search(left) or _PAUSE.search(left):
        return False
    # Left ends mid-flow without punctuation; right continues CJK/alnum.
    left_end = left[-1]
    right_start = right[0]
    cjk = "\u4e00" <= left_end <= "\u9fff" and "\u4e00" <= right_start <= "\u9fff"
    alnum = (left_end.isalnum() and right_start.isalnum() and left_end.isascii() and right_start.isascii())
    if not (cjk or alnum):
        return False
    # Avoid merging two full independent sentences that merely lack periods
    # (both long and right looks like a new sentence start with known openers).
    if len(left) >= 24 and len(right) >= 24 and right_start in "这那其他她你我神心其其":
        # Ambiguous — do not force merge long pairs
        return False
    # Short left tail without punct is almost always a hard cut ("发"+"现")
    if len(left) <= 40 or len(right) <= 12:
        return True
    # Medium: merge when right starts with continuation-like chars
    if right_start in "现得着过了们到上下中里出来去着过":
        return True
    return len(left) < 16


def build_storyboard_narrations(
    text: str,
    split_type: DraftSplitType = "auto",
    target_count: int = 5,
    *,
    soft_expand: bool = True,
    heal: bool = True,
) -> list[str]:
    units = split_draft_by_rule(text, split_type)
    if soft_expand:
        units = soft_expand_by_pause(units)
    packed = pack_semantic_units(units, target_count)
    packed = rebalance_long_units(packed)
    if heal:
        packed = heal_mid_cuts(packed)
    return packed
