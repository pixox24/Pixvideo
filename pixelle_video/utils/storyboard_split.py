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

DraftSplitType = Literal["paragraph", "line", "sentence"]

STORYBOARD_SCENE_MIN = 1
STORYBOARD_SCENE_MAX = 100
SOFT_EXPAND_MIN_PART = 4

_TERMINAL = re.compile(r"[。！？.!?…]+$")
_PAUSE = re.compile(r"[，,；;]+$")


def clamp_scene_count(value: int, minimum: int = STORYBOARD_SCENE_MIN, maximum: int = STORYBOARD_SCENE_MAX) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = minimum
    return min(maximum, max(minimum, number))


def split_draft_by_rule(text: str, split_type: DraftSplitType = "line") -> list[str]:
    trimmed = str(text or "").strip()
    if not trimmed:
        return []

    if split_type == "paragraph":
        return [segment.strip() for segment in re.split(r"\n\s*\n", trimmed) if segment.strip()]

    if split_type == "sentence":
        # Keep terminal punctuation with the sentence.
        parts = re.findall(r"[^。！？.!?\n]+[。！？.!?]?", trimmed)
        return [part.strip() for part in parts if part.strip()]

    # line (default)
    return [line.strip() for line in re.split(r"\r?\n", trimmed) if line.strip()]


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
    sentence_openers = "神心他她你我其其其其这那其其其其"  # weak; use length heuristic
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
    split_type: DraftSplitType = "line",
    target_count: int = 5,
    *,
    soft_expand: bool = True,
    heal: bool = True,
) -> list[str]:
    units = split_draft_by_rule(text, split_type)
    if soft_expand:
        units = soft_expand_by_pause(units)
    packed = pack_semantic_units(units, target_count)
    if heal:
        packed = heal_mid_cuts(packed)
    return packed
