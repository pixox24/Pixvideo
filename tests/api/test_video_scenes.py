import pytest
from pydantic import ValidationError

from api.routers.video import _build_video_params
from api.schemas.video import VideoGenerateRequest
from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


def test_video_request_accepts_100_explicit_scenes():
    request = VideoGenerateRequest(
        text="long project",
        mode="fixed",
        scenes=[{"narration": f"scene {index}"} for index in range(100)],
    )
    assert len(request.scenes) == 100


def test_video_request_rejects_101_explicit_scenes():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="long project",
            mode="fixed",
            scenes=[{"narration": str(index)} for index in range(101)],
        )


class ScenePersistence:
    async def save_task_metadata(self, *_args):
        return None

    async def save_storyboard(self, *_args):
        return None


class SceneCore:
    def __init__(self):
        self.config = {"comfyui": {"image": {"prompt_prefix": "global style"}}}
        self.llm = object()
        self.tts = object()
        self.media = object()
        self.video = object()
        self.persistence = ScenePersistence()


def test_video_request_forwards_structured_scenes(monkeypatch):
    monkeypatch.setattr("api.routers.video._resolve_media_size", lambda _request: (1080, 1920))
    request = VideoGenerateRequest(
        text="第一段\n\n第二段",
        mode="fixed",
        scenes=[
            {"narration": "第一段", "visual_prompt": "first visual"},
            {"narration": "第二段", "visual_prompt": "second visual"},
        ],
    )

    params = _build_video_params(request)

    assert params["scenes"] == [
        {"narration": "第一段", "visual_prompt": "first visual"},
        {"narration": "第二段", "visual_prompt": "second visual"},
    ]


def test_video_request_forwards_asset_reuse_source(monkeypatch):
    monkeypatch.setattr("api.routers.video._resolve_media_size", lambda _request: (1080, 1920))
    request = VideoGenerateRequest(
        text="第一段",
        mode="fixed",
        scenes=[{"narration": "第一段", "visual_prompt": "visual"}],
        reuse_assets_from_task_id="completed-task-id",
    )

    params = _build_video_params(request)

    assert params["reuse_assets_from_task_id"] == "completed-task-id"


def test_video_request_rejects_whitespace_only_scene_narration():
    with pytest.raises(ValidationError):
        VideoGenerateRequest(
            text="fallback",
            mode="fixed",
            scenes=[{"narration": "   ", "visual_prompt": "visual"}],
        )


@pytest.mark.asyncio
async def test_standard_pipeline_uses_scene_narrations_without_resplitting():
    pipeline = StandardPipeline(SceneCore())
    ctx = PipelineContext(
        input_text="ignored merged text",
        params={
            "mode": "fixed",
            "scenes": [
                {"narration": "第一段", "visual_prompt": "first visual"},
                {"narration": "第二段", "visual_prompt": "second visual"},
            ],
        },
    )

    await pipeline.generate_content(ctx)

    assert ctx.narrations == ["第一段", "第二段"]


@pytest.mark.asyncio
async def test_standard_pipeline_preserves_provided_prompts_and_generates_only_missing(monkeypatch):
    generated_for = []

    async def fake_generate_image_prompts(_llm, narrations, **_kwargs):
        generated_for.extend(narrations)
        return ["generated missing visual"]

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_image_prompts",
        fake_generate_image_prompts,
    )
    pipeline = StandardPipeline(SceneCore())
    ctx = PipelineContext(
        input_text="ignored",
        params={
            "composition_mode": "plain_image",
            "scenes": [
                {"narration": "第一段", "visual_prompt": "provided visual"},
                {"narration": "第二段", "visual_prompt": ""},
            ],
        },
    )
    ctx.narrations = ["第一段", "第二段"]

    await pipeline.plan_visuals(ctx)

    assert generated_for == ["第二段"]
    assert "provided visual" in ctx.image_prompts[0]
    assert "generated missing visual" in ctx.image_prompts[1]
