import pytest

from pixelle_video.utils.content_generators import (
    _heuristic_keywords,
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
