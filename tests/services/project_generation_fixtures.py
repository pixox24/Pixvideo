"""Deterministic providers used by project-generation tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from pixelle_video.services.workbench_media import WorkbenchMediaStore


@dataclass
class FakeSceneBehavior:
    """Controls one scene's fake TTS and image outcomes."""

    tts_delay: float = 0.0
    image_delay: float = 0.0
    tts_duration: float = 1.0
    tts_error: str | None = None
    image_error: str | None = None
    wait_for_release: bool = False
    _release_event: asyncio.Event | None = field(default=None, init=False, repr=False)

    def release(self) -> None:
        """Let a gated fake provider call finish naturally."""
        if self._release_event is None:
            self._release_event = asyncio.Event()
        self._release_event.set()

    async def wait(self, delay: float) -> None:
        if self.wait_for_release:
            if self._release_event is None:
                self._release_event = asyncio.Event()
            await self._release_event.wait()
        if delay:
            await asyncio.sleep(delay)


@dataclass(frozen=True)
class FakeProviderCall:
    operation: str
    scene_id: str


class FakeGenerationProvider:
    """Fake TTS/image provider with observable calls and cooperative cancellation."""

    def __init__(self, behaviors: dict[str, FakeSceneBehavior] | None = None):
        self.behaviors = behaviors or {}
        self.calls: list[FakeProviderCall] = []
        self.completed_calls: list[FakeProviderCall] = []
        self.cancel_requested: set[str] = set()
        self.audio_durations: dict[str, float] = {}
        self._started: dict[FakeProviderCall, asyncio.Event] = {}

    def behavior_for(self, scene_id: str) -> FakeSceneBehavior:
        return self.behaviors.setdefault(scene_id, FakeSceneBehavior())

    def request_cancel(self, scene_id: str) -> None:
        """Record cancellation without interrupting the external request."""
        self.cancel_requested.add(scene_id)

    def release(self, scene_id: str) -> None:
        self.behavior_for(scene_id).release()

    async def wait_until_started(self, operation: str, scene_id: str) -> None:
        call = FakeProviderCall(operation, scene_id)
        event = self._started.setdefault(call, asyncio.Event())
        await event.wait()

    async def tts(self, text: str, output_path: str | None = None, **kwargs: Any) -> str:
        scene_id = str(kwargs.get("scene_id") or "unknown")
        behavior = self.behavior_for(scene_id)
        call = FakeProviderCall("tts", scene_id)
        self._record_started(call)
        await behavior.wait(behavior.tts_delay)
        if behavior.tts_error:
            raise RuntimeError(behavior.tts_error)
        if output_path is None:
            raise ValueError("fake TTS requires output_path")
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"fake-audio:{text}".encode("utf-8"))
        # Continuous multi-scene scripts join scenes with newlines; scale duration.
        parts = [part for part in str(text).split("\n") if part.strip()]
        part_count = max(1, len(parts))
        self.audio_durations[str(path.resolve())] = behavior.tts_duration * part_count
        self.completed_calls.append(call)
        return str(path)

    async def media(self, **kwargs: Any) -> Any:
        scene_id = str(kwargs.get("scene_id") or "unknown")
        behavior = self.behavior_for(scene_id)
        call = FakeProviderCall("image", scene_id)
        self._record_started(call)
        await behavior.wait(behavior.image_delay)
        if behavior.image_error:
            raise RuntimeError(behavior.image_error)
        self.completed_calls.append(call)
        return type("FakeMediaResult", (), {"url": f"fake://image/{scene_id}"})()

    def _record_started(self, call: FakeProviderCall) -> None:
        self.calls.append(call)
        self._started.setdefault(call, asyncio.Event()).set()


class FakeFrameProcessor:
    """Frame processor facade that returns provider-controlled audio durations."""

    def __init__(self, provider: FakeGenerationProvider):
        self.provider = provider

    async def _get_audio_duration(self, path: str) -> float:
        return self.provider.audio_durations.get(str(Path(path).resolve()), 0.0)


class FakeProjectGenerationCore:
    """Small core facade compatible with WorkbenchJobService."""

    def __init__(self, provider: FakeGenerationProvider):
        self.provider = provider
        self.config = {
            "comfyui": {"image": {"default_workflow": "fake-workflow"}},
            "workbench": {"mediaWidth": 1024, "mediaHeight": 1536, "scene_concurrency": 1},
        }
        self.frame_processor = FakeFrameProcessor(provider)

    async def tts(self, text: str, output_path: str | None = None, **kwargs: Any) -> str:
        return await self.provider.tts(text, output_path=output_path, **kwargs)

    async def media(self, **kwargs: Any) -> Any:
        return await self.provider.media(**kwargs)


class FakeWorkbenchMediaStore(WorkbenchMediaStore):
    """Writes a tiny valid PNG for every fake image result."""

    async def download_result(
        self,
        project_id: str,
        scene_id: str,
        source_url: str,
        version_id: str,
    ) -> str:
        del source_url
        relative = f"assets/scenes/{scene_id}/generated/{version_id}.png"
        path = self.resolve(project_id, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (32, 32), "blue").save(path)
        return relative
