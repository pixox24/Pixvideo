import pytest

from pixelle_video.prompts import build_content_narration_prompt, build_topic_narration_prompt
from pixelle_video.utils.content_generators import (
    clean_narration_text,
    generate_narrations_from_topic,
    split_narration_script,
)


def test_clean_narration_text_removes_speakable_numbering_prefixes():
    cases = [
        ("1. 这是第一句旁白", "这是第一句旁白"),
        ("01、这是第一句旁白", "这是第一句旁白"),
        ("（2）这是第二句旁白", "这是第二句旁白"),
        ("(3) This number should not be spoken", "This number should not be spoken"),
        ("第4句：这段不要读序号", "这段不要读序号"),
        ("第三段：这段也不要读序号", "这段也不要读序号"),
        ("Scene 5: This label should not be spoken", "This label should not be spoken"),
    ]

    for raw, expected in cases:
        assert clean_narration_text(raw) == expected


def test_clean_narration_text_keeps_real_content_numbers():
    assert clean_narration_text("2026年会是新的开始") == "2026年会是新的开始"
    assert clean_narration_text("3个方法可以让表达更自然") == "3个方法可以让表达更自然"


@pytest.mark.asyncio
async def test_generated_topic_narrations_are_cleaned_before_return():
    async def fake_llm_service(**kwargs):
        return '{"narrations": ["1. 第一句旁白", "第二句旁白"]}'

    narrations = await generate_narrations_from_topic(
        fake_llm_service,
        topic="表达训练",
        n_scenes=2,
    )

    assert narrations == ["第一句旁白", "第二句旁白"]


@pytest.mark.asyncio
async def test_split_narration_script_cleans_numbering_prefixes():
    narrations = await split_narration_script(
        "1. 第一段固定旁白\n2、第二段固定旁白",
        split_mode="line",
    )

    assert narrations == ["第一段固定旁白", "第二段固定旁白"]


def test_narration_prompts_warn_against_speakable_numbering_prefixes():
    topic_prompt = build_topic_narration_prompt("表达训练", 2, 5, 20)
    content_prompt = build_content_narration_prompt("表达训练", 2, 5, 20)

    for prompt in [topic_prompt, content_prompt]:
        assert "pure speakable narration text" in prompt
        assert "Do not start any narration string with" in prompt
        assert "1." in prompt
        assert "第一段" in prompt
