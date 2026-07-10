from types import SimpleNamespace

import pytest

from api.routers import workbench


def _valid_llm_config():
    return {"api_key": "key", "base_url": "https://example.test/v1", "model": "deepseek-v4-pro"}


@pytest.mark.asyncio
async def test_generate_copy_draft_returns_segmented_editable_text(monkeypatch):
    monkeypatch.setattr(workbench.config_manager, "get_llm_config", _valid_llm_config)
    async def fake_narrations(**_kwargs):
        return ["第一段旁白", "第二段旁白"]

    monkeypatch.setattr(workbench, "generate_narrations_from_topic", fake_narrations)

    request = workbench.GenerateCopyDraftRequest(
        topic="未来城市",
        sceneCount=2,
        draftMode="segmented",
        splitType="line",
        targetCharCount=120,
        charCountMode="around",
    )

    result = await workbench.generate_copy_draft(request, SimpleNamespace(llm=object()))

    assert result == {
        "success": True,
        "draftMode": "segmented",
        "draftText": "第一段旁白\n\n第二段旁白",
    }


@pytest.mark.asyncio
async def test_generate_copy_draft_full_mode_includes_total_character_target(monkeypatch):
    monkeypatch.setattr(workbench.config_manager, "get_llm_config", _valid_llm_config)
    captured = {}

    async def fake_llm(prompt: str, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return "这是一段完整口播稿。"

    request = workbench.GenerateCopyDraftRequest(
        topic="未来城市",
        sceneCount=10,
        draftMode="full",
        targetCharCount=120,
        charCountMode="within",
    )

    result = await workbench.generate_copy_draft(request, SimpleNamespace(llm=fake_llm))

    assert result["success"] is True
    assert result["draftText"] == "这是一段完整口播稿。"
    assert "120 字以内" in captured["prompt"]
    assert "10 个分镜" in captured["prompt"]


@pytest.mark.asyncio
async def test_generate_script_uses_confirmed_segmented_copy_without_regenerating_narration(monkeypatch):
    monkeypatch.setattr(workbench.config_manager, "get_llm_config", _valid_llm_config)

    async def fail_if_topic_generation_is_used(**_kwargs):
        raise AssertionError("confirmed segmented copy should be split directly")

    async def fake_image_prompts(**kwargs):
        return [f"visual {index + 1}" for index, _ in enumerate(kwargs["narrations"])]

    monkeypatch.setattr(workbench, "generate_narrations_from_topic", fail_if_topic_generation_is_used)
    monkeypatch.setattr(workbench, "generate_image_prompts", fake_image_prompts)

    request = workbench.GenerateScriptRequest(
        topic="未来城市",
        sceneCount=2,
        splitType="line",
        draftMode="segmented",
        confirmedText="1. 第一段旁白\n2. 第二段旁白",
    )

    result = await workbench.generate_script(request, SimpleNamespace(llm=object()))

    assert result["success"] is True
    assert result["data"] == [
        {"id": 1, "ttsText": "第一段旁白", "visualPrompt": "visual 1"},
        {"id": 2, "ttsText": "第二段旁白", "visualPrompt": "visual 2"},
    ]
