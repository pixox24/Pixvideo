import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from api.routers.projects import _autofill_image_prompts, is_visual_prompt_same_as_narration
from pixelle_video.prompts.image_generation import (
    IMAGE_PROMPT_GENERATION_SYSTEM_PROMPT,
    build_image_prompt_prompt,
)
from pixelle_video.services.llm_service import LLMService
from pixelle_video.utils.content_generators import (
    _parse_image_prompt_response,
    _parse_json,
    generate_image_prompts,
)


def test_image_prompt_builder_keeps_director_rules_out_of_user_message():
    user_prompt = build_image_prompt_prompt(
        ["A person feels trapped by routine."],
        20,
        80,
        batch_index=2,
        batch_count=3,
        completed_count=10,
    )

    assert "A person feels trapped by routine." in user_prompt
    assert "hard-edged shadows" not in user_prompt
    assert "batch 2 of 3" in user_prompt
    assert "10 prompts from earlier batches" in user_prompt
    assert "A person feels trapped by routine." not in IMAGE_PROMPT_GENERATION_SYSTEM_PROMPT
    assert "hard-edged shadows" in IMAGE_PROMPT_GENERATION_SYSTEM_PROMPT
    assert "conditional text policy" in IMAGE_PROMPT_GENERATION_SYSTEM_PROMPT
    assert 'calendar marked "MONDAY"' in IMAGE_PROMPT_GENERATION_SYSTEM_PROMPT
    assert "reserved negative space for precise post-production overlay" in IMAGE_PROMPT_GENERATION_SYSTEM_PROMPT


def test_image_prompt_builder_accepts_aligned_visual_focus_hints():
    user_prompt = build_image_prompt_prompt(
        ["星期一开始准备发布会。"],
        20,
        80,
        visual_focuses=["calendar marked Monday"],
    )
    payload_start = user_prompt.index("{")
    payload_end = user_prompt.index("\n\nThis is")
    payload = json.loads(user_prompt[payload_start:payload_end])
    assert payload["narrations"] == ["星期一开始准备发布会。"]
    assert payload["visual_focuses"] == ["calendar marked Monday"]


def test_style_prefix_is_bound_as_style_only():
    from pixelle_video.prompts.image_generation import build_image_prompt_system_prompt

    system_prompt = build_image_prompt_system_prompt("90s flat editorial print, coral and teal")

    assert "90s flat editorial print, coral and teal" in system_prompt
    assert "not a subject, prop, narration, or text to render" in system_prompt
    assert "90s flat editorial print" not in build_image_prompt_prompt(["A person feels trapped by routine."], 20, 80)
    assert _parse_image_prompt_response('```json\n{"image_prompts":["  prompt  "]}\n```') == {
        "image_prompts": ["prompt"]
    }
    with pytest.raises(ValueError):
        _parse_image_prompt_response('{"image_prompts":{"0":"prompt"}}')
    with pytest.raises(ValueError):
        _parse_image_prompt_response('{"image_prompts":[""]}')


def test_empty_style_prefix_keeps_director_style_neutral():
    from pixelle_video.prompts.image_generation import build_image_prompt_system_prompt

    system_prompt = build_image_prompt_system_prompt("")

    assert "If it is absent, remain style-neutral" in system_prompt
    assert "User style lock" not in system_prompt


def test_image_prompt_parser_repairs_unescaped_quotes_inside_prompt_text():
    payload = '{"image_prompts":["Calendar marked "MONDAY" in red, hard light"]}'
    parsed = _parse_image_prompt_response(payload)
    assert parsed["image_prompts"] == ['Calendar marked "MONDAY" in red, hard light']


def test_image_prompt_parser_inserts_missing_commas_between_pretty_printed_prompts():
    payload = """{"image_prompts": [
  "In a dark bedroom, a lone figure lies awake"
  "A calendar marked Monday hangs over a desk"
  "Wide city lights smear across wet asphalt"
]}"""
    parsed = _parse_image_prompt_response(payload)
    assert parsed["image_prompts"] == [
        "In a dark bedroom, a lone figure lies awake",
        "A calendar marked Monday hangs over a desk",
        "Wide city lights smear across wet asphalt",
    ]


def test_image_prompt_parser_inserts_missing_commas_in_compact_arrays():
    payload = '{"image_prompts":["first prompt" "second prompt" "third prompt"]}'
    parsed = _parse_image_prompt_response(payload)
    assert parsed["image_prompts"] == ["first prompt", "second prompt", "third prompt"]


def test_image_prompt_parser_escapes_raw_newlines_inside_prompt_strings():
    payload = '{"image_prompts":["A figure stares into the dark\nwith one hand on the chest"]}'
    parsed = _parse_image_prompt_response(payload)
    assert parsed["image_prompts"] == [
        "A figure stares into the dark\nwith one hand on the chest"
    ]


def test_image_prompt_parser_accepts_bare_json_array():
    parsed = _parse_image_prompt_response(
        '["In a dark empty room, a lone figure sits on the floor hugging knees", "A calendar marked Monday hangs over a desk"]'
    )
    assert parsed["image_prompts"] == [
        "In a dark empty room, a lone figure sits on the floor hugging knees",
        "A calendar marked Monday hangs over a desk",
    ]


def test_image_prompt_parser_accepts_pretty_printed_bare_array_without_commas():
    payload = """[
  "In a dark empty room, a lone figure sits on the floor hugging knees"
  "A calendar marked Monday hangs over a wooden desk in hard light"
]"""
    parsed = _parse_image_prompt_response(payload)
    assert parsed["image_prompts"] == [
        "In a dark empty room, a lone figure sits on the floor hugging knees",
        "A calendar marked Monday hangs over a wooden desk in hard light",
    ]


def test_image_prompt_parser_uses_inner_array_when_object_parse_yields_list():
    # Broken object that still contains a valid prompt array. The fallback JSON
    # extractor may return that array instead of the wrapper object.
    payload = (
        'Note:\n{"image_prompts": ["In a dark empty room, a lone figure sits on the floor hugging knees", '
        '"A calendar marked Monday hangs over a desk"]}\n'
    )
    parsed = _parse_image_prompt_response(payload)
    assert len(parsed["image_prompts"]) == 2
    assert parsed["image_prompts"][0].startswith("In a dark empty room")


def test_generic_model_json_parser_repairs_unescaped_quotes_in_segmentation_payload():
    payload = '{"segments":[{"text":"星期一的早晨","visual_focus":"calendar marked "MONDAY""}]}'
    parsed = _parse_json(payload)
    assert parsed["segments"][0]["visual_focus"] == 'calendar marked "MONDAY"'


@pytest.mark.asyncio
async def test_image_prompt_generation_sends_system_message_and_batch_context():
    calls = []

    class FakeLLM:
        async def __call__(self, **kwargs):
            calls.append(kwargs)
            input_text = kwargs["prompt"].split("Input narrations (one per requested image, in order):\n", 1)[1]
            input_text = input_text.split("\n\nThis is", 1)[0]
            narrations = json.loads(input_text)
            return json.dumps({
                "image_prompts": [f"English visual prompt for {item}" for item in narrations["narrations"]]
            })

    result = await generate_image_prompts(
        FakeLLM(),
        ["first narration", "second narration"],
        batch_size=1,
    )

    assert len(result) == 2
    assert all(call["system_prompt"] == IMAGE_PROMPT_GENERATION_SYSTEM_PROMPT for call in calls)
    assert calls[0]["prompt"] != calls[1]["prompt"]
    assert result[0] not in calls[1]["prompt"]


class _OutputModel(BaseModel):
    answer: str


class _FakeCompletions:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"answer":"ok"}'))]
        )


class _FakeClient:
    base_url = "https://example.test"

    def __init__(self):
        self.completions = _FakeCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


@pytest.mark.asyncio
async def test_llm_service_sends_optional_system_message_for_standard_and_structured(monkeypatch):
    client = _FakeClient()
    service = LLMService({})
    monkeypatch.setattr(service, "_create_client", lambda **_: client)
    monkeypatch.setattr(
        service,
        "_get_config_value",
        lambda key, default=None: {"model": "test-model"}.get(key, default),
    )

    await service(prompt="user text", system_prompt="director rules")
    assert [item["role"] for item in client.completions.kwargs["messages"]] == ["system", "user"]
    assert client.completions.kwargs["messages"][0]["content"] == "director rules"

    result = await service(
        prompt="structured user text",
        system_prompt="structured rules",
        response_type=_OutputModel,
    )
    assert result.answer == "ok"
    assert [item["role"] for item in client.completions.kwargs["messages"]] == ["system", "user"]
    assert client.completions.kwargs["messages"][0]["content"] == "structured rules"


def test_narration_equals_visual_prompt_is_legacy_contamination():
    assert is_visual_prompt_same_as_narration("  Same words  ", "same words") is True
    assert is_visual_prompt_same_as_narration("different visual", "same words") is False
    assert is_visual_prompt_same_as_narration("", "same words") is False


@pytest.mark.asyncio
async def test_autofill_failure_is_explicit_and_never_silent():
    scene = SimpleNamespace(narration="Narration", visual_prompt="Narration")
    core = SimpleNamespace(llm=None)

    with pytest.raises(HTTPException) as exc_info:
        await _autofill_image_prompts(core, [scene])

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "visual_prompt_generation_failed"
    assert scene.visual_prompt == ""
