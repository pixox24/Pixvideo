import asyncio

import pytest
from project_generation_fixtures import (
    FakeGenerationProvider,
    FakeProjectGenerationCore,
    FakeSceneBehavior,
    FakeWorkbenchMediaStore,
)

from api.tasks.manager import TaskManager
from pixelle_video.models.workbench import (
    AssetSource,
    AssetVersion,
    GenerationRunItemStatus,
    GenerationRunStatus,
    Project,
    Scene,
)
from pixelle_video.services.project_generation_service import (
    ActiveGenerationRunError,
    ActiveSceneLockedError,
    ProjectGenerationService,
)
from pixelle_video.services.workbench_jobs import WorkbenchJobService
from pixelle_video.services.workbench_repository import WorkbenchRepository


def _setup(tmp_path, behaviors=None, scene_count=2):
    provider = FakeGenerationProvider(behaviors)
    core = FakeProjectGenerationCore(provider)
    media = FakeWorkbenchMediaStore(tmp_path / "projects")
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    core.workbench_media = media
    scenes = [
        Scene(
            project_id="project-1",
            scene_id=f"scene-{index}",
            position=index,
            narration=f"narration {index}",
            visual_prompt=f"prompt {index}",
            manual_hold_seconds=0.5 if index == 0 else 0.0,
        )
        for index in range(scene_count)
    ]
    repository.create_project(Project("Test", {}, project_id="project-1"), scenes)
    jobs = WorkbenchJobService(core, repository, media)
    manager = TaskManager()
    service = ProjectGenerationService(core, repository, jobs, manager)
    return provider, media, repository, manager, service, scenes


async def _wait_for_terminal(repository, run_id):
    for _ in range(200):
        run = repository.get_generation_run(run_id)
        if run and run.is_terminal:
            return run
        await asyncio.sleep(0.005)
    raise AssertionError("generation run did not finish")


@pytest.mark.asyncio
async def test_serial_tts_then_image_and_duration(tmp_path):
    """Default continuous delivery: one TTS pass, then per-scene images (fixture concurrency=1)."""
    provider, _, repository, _, service, scenes = _setup(tmp_path)
    run = await service.start("project-1")
    result = await _wait_for_terminal(repository, run.run_id)

    assert result.status == GenerationRunStatus.COMPLETED
    assert [(call.operation, call.scene_id) for call in provider.completed_calls] == [
        ("tts", "scene-0"),
        ("image", "scene-0"),
        ("image", "scene-1"),
    ]
    assert repository.get_scene(scenes[0].scene_id).duration_seconds == 1.5


@pytest.mark.asyncio
async def test_parallel_images_after_continuous_tts(tmp_path):
    """With scene_concurrency>1, image API calls for remaining scenes overlap."""
    provider, _, repository, _, service, _ = _setup(
        tmp_path,
        {
            "scene-0": FakeSceneBehavior(image_delay=0.05),
            "scene-1": FakeSceneBehavior(image_delay=0.05),
            "scene-2": FakeSceneBehavior(image_delay=0.05),
        },
        scene_count=3,
    )
    service.core.config["workbench"]["scene_concurrency"] = 3
    # Rebuild jobs semaphore to pick up new concurrency (service already built jobs).
    service.workbench_jobs._image_concurrency = 3
    service.workbench_jobs._image_semaphore = asyncio.Semaphore(3)

    run = await service.start("project-1")
    # After continuous TTS, all three image starts should appear before any finishes.
    for _ in range(200):
        image_starts = [c for c in provider.calls if c.operation == "image"]
        if len(image_starts) >= 3:
            break
        await asyncio.sleep(0.005)
    image_starts = [c for c in provider.calls if c.operation == "image"]
    assert {c.scene_id for c in image_starts} == {"scene-0", "scene-1", "scene-2"}
    # Not yet all completed at first simultaneous start window
    assert len(provider.completed_calls) < 1 + 3  # tts + 3 images eventually

    result = await _wait_for_terminal(repository, run.run_id)
    assert result.status == GenerationRunStatus.COMPLETED
    image_done = {c.scene_id for c in provider.completed_calls if c.operation == "image"}
    assert image_done == {"scene-0", "scene-1", "scene-2"}


@pytest.mark.asyncio
async def test_per_scene_tts_when_delivery_disabled(tmp_path):
    provider, _, repository, _, service, scenes = _setup(tmp_path)
    repository.update_project("project-1", config={"ttsDelivery": "per_scene"})
    run = await service.start("project-1")
    result = await _wait_for_terminal(repository, run.run_id)

    assert result.status == GenerationRunStatus.COMPLETED
    assert [(call.operation, call.scene_id) for call in provider.completed_calls] == [
        ("tts", "scene-0"),
        ("image", "scene-0"),
        ("tts", "scene-1"),
        ("image", "scene-1"),
    ]
    assert repository.get_scene(scenes[0].scene_id).duration_seconds == 1.5


@pytest.mark.asyncio
async def test_completed_run_creates_one_initial_export_and_is_idempotent(tmp_path):
    _, _, repository, manager, service, _ = _setup(tmp_path, scene_count=1)
    output = tmp_path / "pipeline" / "final.mp4"

    async def generate_video(**_kwargs):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake-video")
        return {"video_path": str(output)}

    service.core.generate_video = generate_video
    run = await service.start("project-1")
    result = await _wait_for_terminal(repository, run.run_id)
    for _ in range(100):
        revisions = repository.list_export_revisions("project-1")
        if revisions and revisions[0].status.value in {"completed", "failed"}:
            break
        await asyncio.sleep(0.005)

    revisions = repository.list_export_revisions("project-1")
    assert len(revisions) == 1
    assert revisions[0].snapshot["purpose"] == "initial"
    assert revisions[0].snapshot["createdFromRunId"] == result.run_id
    assert revisions[0].status.value == "completed"

    await service._finalize(run.run_id)
    assert len(repository.list_export_revisions("project-1")) == 1
    await manager.stop()


@pytest.mark.asyncio
async def test_failure_does_not_block_later_scene(tmp_path):
    provider, _, repository, _, service, _ = _setup(
        tmp_path,
        {"scene-0": FakeSceneBehavior(tts_error="bad tts")},
    )
    run = await service.start("project-1")
    result = await _wait_for_terminal(repository, run.run_id)
    items = repository.list_generation_run_items(run.run_id)

    assert result.status == GenerationRunStatus.COMPLETED_WITH_FAILURES
    assert items[0].status == GenerationRunItemStatus.FAILED
    assert items[1].status == GenerationRunItemStatus.COMPLETED
    assert [call.scene_id for call in provider.completed_calls] == ["scene-1", "scene-1"]


@pytest.mark.asyncio
async def test_existing_current_image_is_candidate_and_active_scene_is_locked(tmp_path):
    provider, media, repository, _, service, scenes = _setup(
        tmp_path,
        {"scene-0": FakeSceneBehavior(wait_for_release=True)},
        scene_count=1,
    )
    existing = media.resolve("project-1", "assets/scenes/scene-0/uploads/current.png")
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"placeholder")
    version = AssetVersion(
        "project-1", "scene-0", AssetSource.AI,
        "assets/scenes/scene-0/uploads/current.png",
        version_id="current-version",
    )
    repository.create_asset_version(version)
    repository.select_asset_version("project-1", "scene-0", version.version_id)

    run = await service.start("project-1")
    for _ in range(100):
        active = repository.get_generation_run(run.run_id)
        if active and active.current_scene_id:
            break
        await asyncio.sleep(0.005)
    with pytest.raises(ActiveSceneLockedError):
        service.assert_scene_editable("project-1", "scene-0")
    provider.release("scene-0")
    result = await _wait_for_terminal(repository, run.run_id)
    item = repository.list_generation_run_items(run.run_id)[0]
    assert result.status == GenerationRunStatus.COMPLETED
    assert item.status == GenerationRunItemStatus.CANDIDATE_REVIEW
    assert item.candidate_version_id
    assert repository.get_scene("scene-0").current_version_id == "current-version"


@pytest.mark.asyncio
async def test_pause_resume_and_cooperative_cancel(tmp_path):
    behavior = {"scene-0": FakeSceneBehavior(wait_for_release=True)}
    provider, _, repository, _, service, _ = _setup(tmp_path, behavior, scene_count=2)
    run = await service.start("project-1")
    await provider.wait_until_started("tts", "scene-0")
    await service.request_pause(run.run_id)
    provider.release("scene-0")
    for _ in range(100):
        if repository.get_generation_run(run.run_id).status == GenerationRunStatus.PAUSED:
            break
        await asyncio.sleep(0.005)
    assert repository.get_generation_run(run.run_id).status == GenerationRunStatus.PAUSED
    await service.request_resume(run.run_id)
    result = await _wait_for_terminal(repository, run.run_id)
    assert result.status == GenerationRunStatus.COMPLETED

    provider2, _, repository2, _, service2, _ = _setup(
        tmp_path / "cancel", {"scene-0": FakeSceneBehavior(wait_for_release=True)}
    )
    run2 = await service2.start("project-1")
    await provider2.wait_until_started("tts", "scene-0")
    await service2.request_cancel(run2.run_id)
    provider2.release("scene-0")
    cancelled = await _wait_for_terminal(repository2, run2.run_id)
    assert cancelled.status == GenerationRunStatus.CANCELLED


@pytest.mark.asyncio
async def test_pause_and_resume_reject_invalid_states(tmp_path):
    _, _, repository, _, service, _ = _setup(tmp_path, scene_count=1)
    run = await service.start("project-1")
    repository.update_generation_run(run.run_id, status=GenerationRunStatus.PAUSED, pause_requested=True)
    with pytest.raises(ValueError, match="cannot be paused"):
        await service.request_pause(run.run_id)

    repository.update_generation_run(run.run_id, status=GenerationRunStatus.RUNNING, pause_requested=False)
    with pytest.raises(ValueError, match="cannot be resumed"):
        await service.request_resume(run.run_id)


@pytest.mark.asyncio
async def test_cancel_after_tts_does_not_start_image_phase(tmp_path):
    provider, _, repository, _, service, _ = _setup(
        tmp_path,
        {"scene-0": FakeSceneBehavior(wait_for_release=True)},
        scene_count=1,
    )
    run = await service.start("project-1")
    await provider.wait_until_started("tts", "scene-0")
    await service.request_cancel(run.run_id)
    provider.release("scene-0")
    cancelled = await _wait_for_terminal(repository, run.run_id)
    assert cancelled.status == GenerationRunStatus.CANCELLED
    assert [(call.operation, call.scene_id) for call in provider.completed_calls] == [("tts", "scene-0")]


@pytest.mark.asyncio
async def test_active_run_conflict_and_resume_after_restart(tmp_path):
    behavior = {"scene-0": FakeSceneBehavior(wait_for_release=True)}
    provider, _, repository, manager, service, _ = _setup(tmp_path, behavior, scene_count=1)
    run = await service.start("project-1")
    await provider.wait_until_started("tts", "scene-0")
    with pytest.raises(ActiveGenerationRunError):
        await service.start("project-1")
    await service.request_cancel(run.run_id)
    provider.release("scene-0")
    await _wait_for_terminal(repository, run.run_id)

    restart_behavior = {"scene-0": FakeSceneBehavior(wait_for_release=True)}
    provider3, media3, repository3, manager3, service3, _ = _setup(
        tmp_path / "restart", restart_behavior, scene_count=1
    )
    queued = await service3.start("project-1")
    await provider3.wait_until_started("tts", "scene-0")
    await manager3.stop()
    provider3.release("scene-0")
    repository3.close()
    repository4 = WorkbenchRepository(tmp_path / "restart" / "workbench.sqlite3")
    core4 = FakeProjectGenerationCore(provider3)
    core4.workbench_media = media3
    jobs4 = WorkbenchJobService(core4, repository4, media3)
    manager4 = TaskManager()
    service4 = ProjectGenerationService(core4, repository4, jobs4, manager4)
    await service4.resume_active_runs()
    result = await _wait_for_terminal(repository4, queued.run_id)
    assert result.status == GenerationRunStatus.COMPLETED
