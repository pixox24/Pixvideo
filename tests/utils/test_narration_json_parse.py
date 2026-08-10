import json

import pytest

from pixelle_video.services.llm_service import LLMService
from pixelle_video.utils import content_generators as cg


def test_parse_json_from_markdown_fence():
    raw = """```json
{"narrations": ["第一句", "第二句"]}
```"""
    assert cg._parse_json(raw) == {"narrations": ["第一句", "第二句"]}


def test_parse_json_with_prose_and_trailing_comma():
    raw = '这是结果：\n{"narrations": ["a", "b",],}\n请使用'
    data = cg._parse_json(raw)
    assert data["narrations"] == ["a", "b"]


def test_extract_narrations_fallback_lines():
    raw = "1. 第一段旁白\n2. 第二段旁白\n3. 第三段旁白"
    assert cg._extract_narrations_fallback(raw, 3) == ["第一段旁白", "第二段旁白", "第三段旁白"]


def test_deepseek_v4_thinking_disabled_by_default():
    kwargs = LLMService._apply_thinking_control("deepseek-v4-flash", {}, thinking=None)
    assert kwargs["extra_body"]["thinking"] == {"type": "disabled"}


def test_thinking_can_be_explicitly_enabled():
    kwargs = LLMService._apply_thinking_control("deepseek-v4-flash", {}, thinking=True)
    assert kwargs["extra_body"]["thinking"] == {"type": "enabled"}


def test_non_deepseek_models_do_not_inject_thinking():
    kwargs = LLMService._apply_thinking_control("gpt-4o-mini", {}, thinking=None)
    assert "extra_body" not in kwargs


def test_message_text_prefers_content_over_reasoning():
    class Msg:
        content = '{"narrations":["ok"]}'
        reasoning_content = "long chain of thought without answer"

    assert LLMService._message_text(Msg()) == '{"narrations":["ok"]}'


def test_message_text_ignores_plain_reasoning_without_json():
    class Msg:
        content = ""
        reasoning_content = "I am thinking about narrations but never output JSON"

    assert LLMService._message_text(Msg()) == ""


@pytest.mark.asyncio
async def test_request_narration_json_retries_on_empty_then_succeeds():
    calls = {"n": 0}

    class FakeLLM:
        async def __call__(self, prompt, temperature=0.7, max_tokens=2000, thinking=None, **kwargs):
            calls["n"] += 1
            assert thinking is False
            if calls["n"] == 1:
                return ""
            return json.dumps({"narrations": [f"旁白{i}" for i in range(1, 4)]}, ensure_ascii=False)

    result = await cg._request_narration_json(FakeLLM(), prompt="主题", n_scenes=3)
    assert result["narrations"] == ["旁白1", "旁白2", "旁白3"]
    assert calls["n"] == 2
