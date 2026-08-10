"""Tests for batched narration generation and short-count top-up."""

from __future__ import annotations

import json

import pytest

from pixelle_video.utils import content_generators as cg


class ScriptedLLM:
    """Return scripted responses; record each call's n_scenes via prompt text."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.prompts: list[str] = []

    async def __call__(self, prompt, temperature=0.7, max_tokens=2000, thinking=None, **kwargs):
        self.calls += 1
        self.prompts.append(str(prompt))
        if not self.responses:
            raise AssertionError("LLM called more times than scripted responses")
        item = self.responses.pop(0)
        if callable(item):
            return item(prompt)
        return item


def _json_narrations(items: list[str]) -> str:
    return json.dumps({"narrations": items}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_large_n_uses_batches_and_returns_exact_count():
    # 25 scenes → batches of 12 + 12 + 1
    responses = [
        _json_narrations([f"批1-{i}" for i in range(12)]),
        _json_narrations([f"批2-{i}" for i in range(12)]),
        _json_narrations(["批3-0"]),
    ]
    llm = ScriptedLLM(responses)
    result = await cg.generate_narrations_from_topic(llm, topic="测试主题", n_scenes=25)
    assert len(result) == 25
    assert result[0] == "批1-0"
    assert result[-1] == "批3-0"
    assert llm.calls == 3


@pytest.mark.asyncio
async def test_short_batch_is_topped_up_instead_of_hard_fail():
    # First response short (8/12), second top-up supplies remaining 4.
    responses = [
        _json_narrations([f"主-{i}" for i in range(8)]),
        _json_narrations([f"补-{i}" for i in range(4)]),
    ]
    llm = ScriptedLLM(responses)
    result = await cg.generate_narrations_from_topic(
        llm,
        topic="补齐测试",
        n_scenes=12,
        batch_size=12,
    )
    assert len(result) == 12
    assert result[:8] == [f"主-{i}" for i in range(8)]
    assert result[8:] == [f"补-{i}" for i in range(4)]
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_content_mode_batching_works():
    responses = [
        _json_narrations([f"内容-{i}" for i in range(10)]),
        _json_narrations([f"内容-{i}" for i in range(10, 15)]),
    ]
    llm = ScriptedLLM(responses)
    result = await cg.generate_narrations_from_content(
        llm,
        content="用户长文案" * 20,
        n_scenes=15,
        batch_size=10,
    )
    assert len(result) == 15
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_recover_truncated_json_strings():
    raw = '{"narrations":["第一句","第二句","第三句"'  # truncated, no closing
    recovered = cg._recover_truncated_narration_json(raw)
    assert recovered == ["第一句", "第二句", "第三句"]


@pytest.mark.asyncio
async def test_request_returns_partial_when_short_for_topup():
    llm = ScriptedLLM([_json_narrations([f"x{i}" for i in range(5)])])
    result = await cg._request_narration_json(llm, prompt="只要部分", n_scenes=10)
    assert len(result["narrations"]) == 5


def test_narration_max_tokens_scales():
    assert cg._narration_max_tokens(3) >= 1024
    assert cg._narration_max_tokens(12) <= 8192
    assert cg._narration_max_tokens(12) > cg._narration_max_tokens(3)


@pytest.mark.asyncio
async def test_simulate_98_short_then_complete_with_batches():
    """Regression: 98 scenes must not hard-fail on a single short array."""
    import re

    state = {"primary_calls": 0}

    def _requested_count(prompt: str) -> int:
        patterns = [
            r"Generate EXACTLY\s+(\d+)",
            r"数组长度必须恰好是\s*(\d+)",
            r"数组长度必须是\s*(\d+)",
            r"请生成恰好\s*(\d+)\s*条",
            r"请再写恰好\s*(\d+)\s*条",
            r"create\s+(\d+)\s+video storyboards",
        ]
        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE)
            if match:
                return int(match.group(1))
        return 12

    def make_batch(prompt: str) -> str:
        need = _requested_count(prompt)
        is_topup = "补齐" in prompt or "请再写恰好" in prompt or "数组长度必须恰好是" in prompt
        if is_topup:
            return _json_narrations([f"补{state['primary_calls']}-{i}" for i in range(need)])
        state["primary_calls"] += 1
        # First primary batch intentionally short (10/12) → forces top-up.
        if state["primary_calls"] == 1:
            return _json_narrations([f"短{i}" for i in range(max(1, need - 2))])
        return _json_narrations([f"镜{state['primary_calls']}-{i}" for i in range(need)])

    llm = ScriptedLLM([make_batch] * 40)
    result = await cg.generate_narrations_from_topic(llm, topic="大项目", n_scenes=98)
    assert len(result) == 98
    assert llm.calls >= 9  # at least ceil(98/12) primary batches
