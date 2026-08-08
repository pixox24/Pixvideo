import pytest

from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.pipelines.standard import StandardPipeline


class DummyCore:
    config = {"comfyui": {"image": {"prompt_prefix": ""}}}
    llm = object()
    tts = object()
    media = object()
    video = object()


@pytest.mark.asyncio
async def test_standard_pipeline_passes_composition_settings_to_storyboard_config():
    pipeline = StandardPipeline(DummyCore())
    ctx = PipelineContext(
        input_text="topic",
        params={
            "composition_mode": "plain_image",
            "image_motion_enabled": True,
            "subtitle_enabled": False,
            "image_motion_mode": "auto",
            "image_motion_strength": "subtle",
            "image_fit_mode": "cover",
            "media_width": 1080,
            "media_height": 1920,
            "media_workflow": "bizyair/image_o2.json",
        },
    )
    ctx.task_id = "task-1"
    ctx.title = "Title"
    ctx.narrations = ["第一段", "第二段"]
    ctx.image_prompts = ["prompt 1", "prompt 2"]

    await pipeline.initialize_storyboard(ctx)

    assert ctx.config.composition_mode == "plain_image"
    assert ctx.config.image_motion_enabled is True
    assert ctx.config.subtitle_enabled is False
    assert ctx.config.image_motion_mode == "auto"
    assert ctx.config.image_motion_strength == "subtle"
    assert ctx.config.image_fit_mode == "cover"


@pytest.mark.asyncio
async def test_existing_workbench_assets_set_effective_frame_duration():
    pipeline = StandardPipeline(DummyCore())
    ctx = PipelineContext(
        input_text="topic",
        params={
            "scenes": [{"sceneId": "scene-1"}],
            "existing_scene_assets": {
                "scene-1": {
                    "audio_path": "/tmp/audio.mp3",
                    "image_path": "/tmp/image.png",
                    "duration_seconds": 2.0,
                    "manual_hold_seconds": 1.5,
                },
            },
        },
    )
    ctx.task_id = "task-1"
    ctx.title = "Title"
    ctx.narrations = ["第一段"]
    ctx.image_prompts = ["prompt 1"]

    await pipeline.initialize_storyboard(ctx)

    frame = ctx.storyboard.frames[0]
    assert frame.audio_path == "/tmp/audio.mp3"
    assert frame.image_path == "/tmp/image.png"
    assert frame.duration == 3.5


@pytest.mark.asyncio
async def test_plain_image_mode_requires_visual_prompts_even_with_static_template(monkeypatch):
    pipeline = StandardPipeline(DummyCore())
    ctx = PipelineContext(
        input_text="topic",
        params={
            "composition_mode": "plain_image",
            "frame_template": "1080x1920/static_default.html",
            "prompt_prefix": "",
        },
    )
    ctx.narrations = ["第一段"]

    async def fake_generate_image_prompts(*args, **kwargs):
        return ["base prompt"]

    monkeypatch.setattr(
        "pixelle_video.pipelines.standard.generate_image_prompts",
        fake_generate_image_prompts,
    )

    await pipeline.plan_visuals(ctx)

    assert ctx.image_prompts == ["base prompt"]
