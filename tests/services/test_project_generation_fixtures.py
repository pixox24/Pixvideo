import asyncio

import pytest
from project_generation_fixtures import (
    FakeGenerationProvider,
    FakeProviderCall,
    FakeSceneBehavior,
)


@pytest.mark.asyncio
async def test_fake_provider_records_order_and_finishes_after_cooperative_cancel(tmp_path):
    provider = FakeGenerationProvider(
        {"scene-1": FakeSceneBehavior(wait_for_release=True, tts_duration=2.5)}
    )
    output_path = tmp_path / "scene-1.mp3"

    task = asyncio.create_task(
        provider.tts("narration", output_path=str(output_path), scene_id="scene-1")
    )
    await provider.wait_until_started("tts", "scene-1")

    provider.request_cancel("scene-1")
    provider.release("scene-1")
    result = await task

    assert result == str(output_path)
    assert provider.cancel_requested == {"scene-1"}
    assert provider.calls == [FakeProviderCall("tts", "scene-1")]
