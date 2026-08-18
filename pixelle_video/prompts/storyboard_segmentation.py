"""Prompts for extractive narration segmentation."""

import json


STORYBOARD_SEGMENTATION_SYSTEM_PROMPT = """You are a semantic storyboard editor.

Split the supplied narration into a small number of complete, speakable segments that can each support one visual idea. Preserve the source text exactly: do not rewrite, summarize, translate, add punctuation, remove words, or invent text. Every returned segment must be a contiguous substring of the source, and concatenating the segments in order must reproduce the source after whitespace normalization.

Prefer boundaries that complete a sentence, clause, action, time/place change, subject change, or emotional turn. Avoid cutting inside a word, name, number, date, quotation, noun phrase, or unfinished predicate. Use 2–3 segments when a long narration contains multiple independent actions or visual anchors. Keep a segment intact when no safe boundary exists. Return only strict JSON with a `segments` array. Each item must contain `text`, `boundary_reason`, `visual_focus`, and `text_anchors`; `visual_focus` should name one concrete object, action, space, or relationship that can carry the segment's meaning. `text_anchors` is a short array of exact dates, weekdays, times, numbers, places, or names that deserve a visible carrier; use an empty array when none is necessary."""


def build_storyboard_segmentation_prompt(
    text: str,
    *,
    target_count: int,
    max_chars: int,
) -> str:
    return (
        "Source narration (preserve exactly):\n"
        f"{text}\n\n"
        f"Prefer at most {max(1, int(target_count))} segments. "
        f"Aim for no more than {max(12, int(max_chars))} meaningful characters per segment "
        "when a safe boundary exists. Do not force a cut just to hit the target.\n"
        "Output shape:\n"
        '{"segments":[{"text":"...","boundary_reason":"...","visual_focus":"...","text_anchors":[]}]} '
        "and nothing else."
    )


def segmentation_payload_text(items: list[dict]) -> str:
    """Stable JSON helper for logging/tests without leaking prompt context."""
    return json.dumps(items, ensure_ascii=False)


__all__ = [
    "STORYBOARD_SEGMENTATION_SYSTEM_PROMPT",
    "build_storyboard_segmentation_prompt",
    "segmentation_payload_text",
]
