import pytest

from pixelle_video.utils.content_generators import (
    _heuristic_keywords,
    _keyword_limit,
    generate_highlight_keywords,
)


def test_heuristic_keywords_picks_cjk_tokens():
    keywords = _heuristic_keywords("让表达力成为产品重点与核心卖点", max_keywords=4)
    words = [item["word"] for item in keywords]
    assert keywords
    assert all(2 <= len(word) <= 6 for word in words)
    assert all(item["color"].startswith("#") for item in keywords)
    # Tokens should come from the source string.
    source = "让表达力成为产品重点与核心卖点"
    assert all(word in source for word in words)


def test_keyword_limit_keeps_legacy_request_when_density_is_omitted():
    assert _keyword_limit(24, None) == 24
    assert _keyword_limit(24, "standard") == 8


@pytest.mark.asyncio
async def test_generate_highlight_keywords_parses_llm_json():
    class DummyLLM:
        async def __call__(self, prompt, temperature=0.3, max_tokens=400):
            return '[{"word":"表达力","color":"#FF0000"},{"word":"重点","color":"#00FF00"}]'

    keywords = await generate_highlight_keywords(
        DummyLLM(),
        "让表达力成为重点",
        max_keywords=5,
    )
    assert keywords == [
        {"word": "表达力", "color": "#FF0000"},
        {"word": "重点", "color": "#00FF00"},
    ]


@pytest.mark.asyncio
async def test_generate_highlight_keywords_falls_back_on_bad_llm():
    class DummyLLM:
        async def __call__(self, prompt, temperature=0.3, max_tokens=400):
            return "not-json"

    keywords = await generate_highlight_keywords(
        DummyLLM(),
        "让表达力成为产品亮点",
        max_keywords=3,
    )
    assert keywords
    assert all("word" in item and "color" in item for item in keywords)


@pytest.mark.asyncio
async def test_generate_highlight_keywords_applies_preferences_and_avoid_words():
    class DummyLLM:
        prompt = ""

        async def __call__(self, prompt, temperature=0.3, max_tokens=400):
            self.prompt = prompt
            return '[{"word":"表达力","color":"#FF0000"},{"word":"核心卖点","color":"#00FF00"}]'

    llm = DummyLLM()
    keywords = await generate_highlight_keywords(
        llm,
        "让表达力成为产品的核心卖点",
        max_keywords=12,
        style="selling_point",
        density="high",
        avoid_words=["表达力"],
    )

    assert keywords == [{"word": "核心卖点", "color": "#00FF00"}]
    assert "优先选择功能、利益点和差异化卖点" in llm.prompt
    assert "相对密集的关键词" in llm.prompt
    assert "最多 12 个词" in llm.prompt
    assert "表达力" in llm.prompt


def test_heuristic_keywords_respects_avoid_words():
    keywords = _heuristic_keywords(
        "让表达力成为产品重点与核心卖点",
        max_keywords=4,
        avoid_words=["让表达力", "重点"],
    )

    assert all(item["word"] not in {"让表达力", "重点"} for item in keywords)
