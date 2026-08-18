"""Concurrent, resumable orchestration for project generation runs.

Scene items run in parallel waves (default concurrency from
``workbench.scene_concurrency``). Continuous TTS still runs once up front;
image API calls for pending scenes are issued together up to that limit.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from loguru import logger

from api.tasks.models import TaskType
from pixelle_video.models.workbench import (
    ExportRevision,
    GenerationPhase,
    GenerationRun,
    GenerationRunItem,
    GenerationRunItemStatus,
    GenerationRunStatus,
    effective_scene_duration,
)
from pixelle_video.services.continuous_tts import (
    ContinuousSceneSegment,
    should_use_continuous_tts,
)
from pixelle_video.services.continuous_tts.assemble import delivery_from_snapshot
from pixelle_video.services.workbench_generation import ProjectGenerationPlanner


class ActiveGenerationRunError(ValueError):
    def __init__(self, run: GenerationRun):
        super().__init__("project already has an active generation run")
        self.run = run


class ActiveSceneLockedError(ValueError):
    def __init__(self, run_id: str, scene_id: str):
        super().__init__("scene is locked by an active generation run")
        self.run_id = run_id
        self.scene_id = scene_id


class ProjectGenerationService:
    def __init__(
        self,
        core,
        repository,
        workbench_jobs,
        task_manager=None,
        planner: ProjectGenerationPlanner | None = None,
    ):
        if task_manager is None:
            from api.tasks import task_manager as default_task_manager

            task_manager = default_task_manager
        self.core = core
        self.repository = repository
        self.workbench_jobs = workbench_jobs
        self.task_manager = task_manager
        self.planner = planner or ProjectGenerationPlanner(
            repository,
            core.workbench_media,
            runtime_config=getattr(core, "config", {}),
        )
        self._run_locks: dict[str, asyncio.Lock] = {}
        self._run_events: dict[str, asyncio.Event] = {}

    async def start(
        self,
        project_id: str,
        config_override: Mapping[str, Any] | None = None,
        scene_ids: Sequence[str] | None = None,
    ) -> GenerationRun:
        active = self.repository.get_active_generation_run(project_id)
        if active is not None:
            raise ActiveGenerationRunError(active)

        # Explicit partial regeneration requests must never cross a user lock.
        # Initial runs without scene_ids still include every scene so a locked
        # draft can receive its first set of assets.
        effective_scene_ids = list(scene_ids) if scene_ids is not None else None
        if effective_scene_ids is not None:
            locked_ids = {
                scene.scene_id
                for scene in self.repository.list_project_scenes(project_id)
                if scene.locked
            }
            effective_scene_ids = [scene_id for scene_id in effective_scene_ids if scene_id not in locked_ids]
            if not effective_scene_ids:
                raise ValueError("所选分镜均已锁定，未启动重新生成")

        task = self.task_manager.create_task(
            TaskType.WORKBENCH_PROJECT_RUN,
            request_params={
                "project_id": project_id,
                "scene_ids": effective_scene_ids,
                "config_override": dict(config_override or {}),
            },
        )
        try:
            run, items = self.planner.plan_run(
                project_id,
                task_id=task.task_id,
                scene_ids=effective_scene_ids,
                config_override=config_override,
            )
            self.repository.create_generation_run(run, items)
        except Exception:
            await self.task_manager.cancel_task(task.task_id)
            raise
        await self.task_manager.execute_task(task.task_id, self.run, run.run_id)
        return self.repository.get_generation_run(run.run_id) or run

    async def run(self, run_id: str) -> None:
        lock = self._run_locks.setdefault(run_id, asyncio.Lock())
        async with lock:
            try:
                await self._run_locked(run_id)
            except asyncio.CancelledError:
                # Hard cancel (task manager / shutdown) must terminalize DB state.
                self._terminalize_run_cancelled(run_id, error="generation cancelled")
                raise
            except Exception as exc:
                run = self.repository.get_generation_run(run_id)
                if run is not None and not run.is_terminal:
                    self.repository.update_generation_run(
                        run_id,
                        status=GenerationRunStatus.FAILED,
                        current_scene_id=None,
                        error=str(exc),
                    )
                raise

    async def request_pause(self, run_id: str) -> GenerationRun:
        run = self._require_run(run_id)
        if run.is_terminal:
            raise ValueError("generation run is already terminal")
        if run.status not in {GenerationRunStatus.QUEUED, GenerationRunStatus.RUNNING}:
            raise ValueError(f"generation run cannot be paused from {run.status.value} state")
        if run.pause_requested:
            raise ValueError("generation run pause has already been requested")
        changes: dict[str, Any] = {"pause_requested": True}
        if run.status == GenerationRunStatus.QUEUED:
            changes["status"] = GenerationRunStatus.PAUSED
        self.repository.update_generation_run(run_id, **changes)
        return self._require_run(run_id)

    async def request_resume(self, run_id: str) -> GenerationRun:
        run = self._require_run(run_id)
        if run.is_terminal:
            raise ValueError("generation run is already terminal")
        if run.status != GenerationRunStatus.PAUSED:
            raise ValueError(f"generation run cannot be resumed from {run.status.value} state")
        self.repository.update_generation_run(
            run_id,
            pause_requested=False,
            status=GenerationRunStatus.RUNNING,
        )
        self._run_events.setdefault(run_id, asyncio.Event()).set()
        await self._ensure_task(run_id)
        return self._require_run(run_id)

    async def request_cancel(self, run_id: str) -> GenerationRun:
        run = self._require_run(run_id)
        if run.is_terminal:
            raise ValueError("generation run is already terminal")
        self.repository.update_generation_run(run_id, cancel_requested=True)
        self._run_events.setdefault(run_id, asyncio.Event()).set()
        if run.status in {GenerationRunStatus.QUEUED, GenerationRunStatus.PAUSED}:
            self.repository.mark_remaining_run_items_cancelled(run_id)
            self.repository.recompute_generation_run_counts(run_id)
            self.repository.update_generation_run(
                run_id,
                status=GenerationRunStatus.CANCELLED,
                current_scene_id=None,
            )
        return self._require_run(run_id)

    async def retry_failed(
        self,
        run_id: str,
        config_override: Mapping[str, Any] | None = None,
    ) -> GenerationRun:
        previous = self._require_run(run_id)
        if self.repository.get_active_generation_run(previous.project_id):
            raise ActiveGenerationRunError(
                self.repository.get_active_generation_run(previous.project_id)
            )
        task = self.task_manager.create_task(
            TaskType.WORKBENCH_PROJECT_RUN,
            request_params={"retry_failed_run_id": run_id},
        )
        try:
            new_run, items = self.planner.plan_retry_failed(
                run_id,
                task_id=task.task_id,
                config_override=config_override,
            )
            self.repository.create_generation_run(new_run, items)
        except Exception:
            await self.task_manager.cancel_task(task.task_id)
            raise
        await self.task_manager.execute_task(task.task_id, self.run, new_run.run_id)
        return self.repository.get_generation_run(new_run.run_id) or new_run

    async def resume_active_runs(self) -> list[str]:
        scheduled: list[str] = []
        for run in self.repository.list_active_generation_runs():
            if run.status == GenerationRunStatus.PAUSED and not run.cancel_requested:
                continue
            try:
                await self._ensure_task(run.run_id)
                scheduled.append(run.run_id)
            except Exception as exc:
                logger.warning(
                    "Failed to resume generation run {}; marking failed: {}",
                    run.run_id,
                    exc,
                )
                self.fail_active_run(
                    run.run_id,
                    error=f"Failed to resume after restart: {exc}",
                )
        return scheduled

    def fail_active_run(self, run_id: str, *, error: str) -> None:
        """Force a non-terminal generation run into FAILED (startup / resume safety)."""
        run = self.repository.get_generation_run(run_id)
        if run is None or run.is_terminal:
            return
        self.repository.mark_remaining_run_items_cancelled(run_id)
        # Re-mark remaining as failed message context via run error; items already cancelled.
        self.repository.recompute_generation_run_counts(run_id)
        self.repository.update_generation_run(
            run_id,
            status=GenerationRunStatus.FAILED,
            current_scene_id=None,
            error=error,
        )

    def fail_all_active_runs(self, *, error: str) -> int:
        count = 0
        for run in self.repository.list_active_generation_runs():
            self.fail_active_run(run.run_id, error=error)
            count += 1
        return count

    def _terminalize_run_cancelled(self, run_id: str, *, error: str) -> None:
        run = self.repository.get_generation_run(run_id)
        if run is None or run.is_terminal:
            return
        self.repository.mark_remaining_run_items_cancelled(run_id)
        # Also force mid-flight items (RUNNING_*) to terminal cancelled.
        for item in self.repository.list_generation_run_items(run_id):
            if item.is_terminal:
                continue
            self.repository.update_generation_run_item(
                item.item_id,
                status=GenerationRunItemStatus.CANCELLED,
                tts_status=(
                    GenerationPhase.CANCELLED
                    if item.tts_status in {GenerationPhase.PENDING, GenerationPhase.RUNNING}
                    else item.tts_status
                ),
                image_status=(
                    GenerationPhase.CANCELLED
                    if item.image_status in {GenerationPhase.PENDING, GenerationPhase.RUNNING}
                    else item.image_status
                ),
                error=error,
            )
            try:
                self.repository.update_scene(item.scene_id, status="cancelled")
            except Exception:
                pass
        self.repository.recompute_generation_run_counts(run_id)
        self.repository.update_generation_run(
            run_id,
            status=GenerationRunStatus.CANCELLED,
            current_scene_id=None,
            cancel_requested=True,
            error=error,
        )
        self._publish_progress(run_id, "generation cancelled")

    def assert_scene_editable(self, project_id: str, scene_id: str) -> None:
        """Lock any scene that still has a non-terminal generation item (supports parallel waves)."""
        run = self.repository.get_active_generation_run(project_id)
        if run is None:
            return
        item = next(
            (
                item
                for item in self.repository.list_generation_run_items(run.run_id)
                if item.scene_id == scene_id
            ),
            None,
        )
        if item and not item.is_terminal:
            raise ActiveSceneLockedError(run.run_id, scene_id)

    def _scene_concurrency(self) -> int:
        """Max scenes generating media at once (TTS+image item work)."""
        cfg = getattr(self.core, "config", {}) or {}
        workbench = cfg.get("workbench") if isinstance(cfg, dict) else {}
        if not isinstance(workbench, dict):
            workbench = {}
        raw = workbench.get("scene_concurrency", 6)
        try:
            return max(1, min(16, int(raw)))
        except (TypeError, ValueError):
            return 6

    async def _ensure_task(self, run_id: str) -> None:
        run = self._require_run(run_id)
        task = self.task_manager.get_task(run.task_id)
        if task is None or task.status.value in {"completed", "failed", "cancelled"}:
            self.task_manager.restore_task(
                run.task_id,
                TaskType.WORKBENCH_PROJECT_RUN,
                request_params={"project_id": run.project_id, "run_id": run.run_id},
            )
        await self.task_manager.execute_task(run.task_id, self.run, run.run_id)

    async def _run_locked(self, run_id: str) -> None:
        run = self._require_run(run_id)
        if run.is_terminal:
            return
        self.repository.recompute_generation_run_counts(run_id)
        continuous_tts_done = False
        concurrency = self._scene_concurrency()
        logger.info(
            "Generation run {} concurrency={} (parallel scene waves)",
            run_id,
            concurrency,
        )
        while True:
            run = self._require_run(run_id)
            if run.cancel_requested:
                self.repository.mark_remaining_run_items_cancelled(run_id)
                self.repository.recompute_generation_run_counts(run_id)
                self.repository.update_generation_run(
                    run_id,
                    status=GenerationRunStatus.CANCELLED,
                    current_scene_id=None,
                )
                self._publish_progress(run_id, "generation cancelled")
                return
            if run.pause_requested:
                self.repository.update_generation_run(
                    run_id,
                    status=GenerationRunStatus.PAUSED,
                )
                await self._wait_for_resume_or_cancel(run_id)
                continue

            if run.status != GenerationRunStatus.RUNNING:
                self.repository.update_generation_run(
                    run_id,
                    status=GenerationRunStatus.RUNNING,
                )
            items = self.repository.list_generation_run_items(run_id)

            # Phase-1 continuous TTS: one synth pass before per-scene image work.
            if not continuous_tts_done:
                continuous_tts_done = True
                try:
                    await self._maybe_run_continuous_tts(run_id, items)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # Continuous failure falls back to per-scene TTS for remaining items.
                    logger.warning(
                        "Continuous TTS failed for run {}; falling back to per-scene: {}",
                        run_id,
                        exc,
                    )
                    self._publish_progress(run_id, "continuous TTS failed; using per-scene")
                items = self.repository.list_generation_run_items(run_id)

            pending = [candidate for candidate in items if not candidate.is_terminal]
            if not pending:
                await self._finalize(run_id)
                return

            # Launch up to N non-terminal scenes together (images after continuous TTS).
            wave = pending[:concurrency]
            self.repository.update_generation_run(
                run_id,
                current_scene_id=wave[0].scene_id,
            )
            self._publish_progress(
                run_id,
                f"processing {len(wave)} scene(s) in parallel"
                if len(wave) > 1
                else f"scene {wave[0].position + 1} started",
            )
            await self._process_item_wave(run_id, wave)

    async def _process_item_wave(
        self,
        run_id: str,
        wave: Sequence[GenerationRunItem],
    ) -> None:
        """Process one or many scene items; multiple items run concurrently."""

        async def _one(item: GenerationRunItem) -> None:
            run_now = self._require_run(run_id)
            if run_now.cancel_requested:
                self.repository.update_generation_run_item(
                    item.item_id,
                    status=GenerationRunItemStatus.CANCELLED,
                    tts_status=(
                        GenerationPhase.CANCELLED
                        if item.tts_status
                        in {GenerationPhase.PENDING, GenerationPhase.RUNNING}
                        else item.tts_status
                    ),
                    image_status=(
                        GenerationPhase.CANCELLED
                        if item.image_status
                        in {GenerationPhase.PENDING, GenerationPhase.RUNNING}
                        else item.image_status
                    ),
                    error="cancelled",
                )
                try:
                    self.repository.update_scene(item.scene_id, status="cancelled")
                except Exception:
                    pass
                return

            self._recover_interrupted_item(item)
            try:
                await self._process_item(run_id, item)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._record_item_failure(item, exc)
            self.repository.recompute_generation_run_counts(run_id)
            self._publish_progress(run_id, f"scene {item.position + 1} finished")

        if len(wave) == 1:
            await _one(wave[0])
            return

        results = await asyncio.gather(
            *(_one(item) for item in wave),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException) and not isinstance(result, Exception):
                raise result
            # Per-item Exception already recorded inside _one; ignore here.
            # Unexpected BaseException subclasses other than CancelledError re-raised above.

    async def _maybe_run_continuous_tts(
        self,
        run_id: str,
        items: Sequence[GenerationRunItem],
    ) -> bool:
        """
        When delivery=continuous and 2+ scenes need TTS, synthesize once and split.

        Marks those items' tts_status COMPLETED so _process_item only does images.
        Returns True when continuous path executed.
        """
        run = self._require_run(run_id)
        delivery = delivery_from_snapshot(run.parameter_snapshot)
        provider = None
        tts_snapshot = run.parameter_snapshot.get("tts") if isinstance(run.parameter_snapshot, dict) else {}
        if isinstance(tts_snapshot, dict):
            provider = tts_snapshot.get("provider")

        pending = [
            item
            for item in items
            if item.tts_status in {GenerationPhase.PENDING, GenerationPhase.RUNNING}
            and item.status not in {
                GenerationRunItemStatus.FAILED,
                GenerationRunItemStatus.CANCELLED,
            }
        ]
        if not should_use_continuous_tts(
            delivery=delivery,
            scene_count=len(items),
            pending_tts_count=len(pending),
            provider=provider,
        ):
            return False

        # Recover interrupted RUNNING → treat as pending targets.
        for item in pending:
            if item.tts_status == GenerationPhase.RUNNING:
                self.repository.update_generation_run_item(
                    item.item_id,
                    tts_status=GenerationPhase.PENDING,
                    status=GenerationRunItemStatus.QUEUED,
                )
        pending = [
            item
            for item in self.repository.list_generation_run_items(run_id)
            if item.tts_status == GenerationPhase.PENDING
            and item.status not in {
                GenerationRunItemStatus.FAILED,
                GenerationRunItemStatus.CANCELLED,
            }
        ]
        if len(pending) < 2:
            return False

        segments = [
            ContinuousSceneSegment(
                scene_id=item.scene_id,
                item_id=item.item_id,
                position=item.position,
                narration=item.narration_snapshot,
                narration_fingerprint=item.narration_fingerprint,
            )
            for item in sorted(pending, key=lambda entry: entry.position)
        ]

        for item in pending:
            self.repository.update_generation_run_item(
                item.item_id,
                status=GenerationRunItemStatus.RUNNING_TTS,
                tts_status=GenerationPhase.RUNNING,
            )
        self.repository.update_generation_run(
            run_id,
            current_scene_id=segments[0].scene_id,
        )
        self._publish_progress(run_id, f"continuous TTS for {len(segments)} scenes")

        try:
            results = await self.workbench_jobs.generate_continuous_tts_assets(
                run.project_id,
                run_id,
                segments,
            )
        except Exception:
            # Reset to PENDING so per-scene path can retry.
            for item in pending:
                self.repository.update_generation_run_item(
                    item.item_id,
                    status=GenerationRunItemStatus.QUEUED,
                    tts_status=GenerationPhase.PENDING,
                )
            raise

        for item in pending:
            result = results.get(item.scene_id)
            if not result:
                self.repository.update_generation_run_item(
                    item.item_id,
                    status=GenerationRunItemStatus.QUEUED,
                    tts_status=GenerationPhase.PENDING,
                    error="continuous TTS missing scene slice",
                )
                continue
            await self._update_scene_duration(
                run.project_id,
                item.scene_id,
                float(result["duration_seconds"]),
            )
            self.repository.update_generation_run_item(
                item.item_id,
                tts_status=GenerationPhase.COMPLETED,
                # Keep item non-terminal so image phase can still run.
                status=GenerationRunItemStatus.QUEUED,
                error=None,
            )

        self._publish_progress(run_id, "continuous TTS split complete")
        return True

    async def _process_item(self, run_id: str, item: GenerationRunItem) -> None:
        run = self._require_run(run_id)
        # Refresh in case continuous phase completed TTS already.
        current_item = self.repository.get_generation_run_item(item.item_id) or item
        item = current_item
        if item.tts_status in {GenerationPhase.PENDING, GenerationPhase.RUNNING}:
            self.repository.update_generation_run_item(
                item.item_id,
                status=GenerationRunItemStatus.RUNNING_TTS,
                tts_status=GenerationPhase.RUNNING,
            )
            result = await self.workbench_jobs.generate_tts_asset(
                run.project_id,
                item.scene_id,
                self._child_task_id(item, "tts"),
                item.narration_snapshot,
                item.narration_fingerprint,
            )
            await self._update_scene_duration(
                run.project_id,
                item.scene_id,
                float(result["duration_seconds"]),
            )
            self.repository.update_generation_run_item(
                item.item_id,
                tts_status=GenerationPhase.COMPLETED,
            )
        elif item.tts_status == GenerationPhase.SKIPPED:
            await self._sync_existing_scene_duration(run.project_id, item.scene_id)
        # GenerationPhase.COMPLETED: continuous pass already applied hold via
        # _update_scene_duration; do not re-sync or hold is double-counted.

        # A cancellation may arrive while TTS is in flight. Let that provider
        # call return, but do not start the next phase for the same scene.
        current_run = self._require_run(run_id)
        if current_run.cancel_requested:
            self.repository.update_generation_run_item(
                item.item_id,
                tts_status=GenerationPhase.COMPLETED,
                image_status=GenerationPhase.CANCELLED,
                status=GenerationRunItemStatus.CANCELLED,
            )
            self.repository.update_scene(item.scene_id, status="cancelled")
            return

        current = self.repository.get_generation_run_item(item.item_id)
        if current is None:
            raise ValueError("generation run item not found")
        if current.image_status in {GenerationPhase.PENDING, GenerationPhase.RUNNING}:
            self.repository.update_generation_run_item(
                item.item_id,
                status=GenerationRunItemStatus.RUNNING_IMAGE,
                image_status=GenerationPhase.RUNNING,
            )
            result = await self.workbench_jobs.generate_image_asset(
                run.project_id,
                item.scene_id,
                self._child_task_id(item, "image"),
                item.prompt_snapshot,
                item.image_fingerprint,
            )
            self.repository.update_generation_run_item(
                item.item_id,
                image_status=GenerationPhase.COMPLETED,
                status=(
                    GenerationRunItemStatus.CANDIDATE_REVIEW
                    if result["candidate"]
                    else GenerationRunItemStatus.COMPLETED
                ),
                candidate_version_id=(
                    result["version_id"] if result["candidate"] else None
                ),
            )
        elif current.image_status == GenerationPhase.SKIPPED:
            self.repository.update_generation_run_item(
                item.item_id,
                status=(
                    GenerationRunItemStatus.COMPLETED
                    if current.status == GenerationRunItemStatus.QUEUED
                    else current.status
                ),
            )
        self.repository.update_scene(item.scene_id, status="completed")

    async def _sync_existing_scene_duration(self, project_id: str, scene_id: str) -> None:
        duration = await self.workbench_jobs.get_audio_duration(project_id, scene_id)
        scene = self.repository.get_scene(scene_id)
        if scene is None:
            raise ValueError("scene not found")
        if duration <= 0:
            duration = scene.duration_seconds
        await self._update_scene_duration(project_id, scene_id, duration)

    async def _update_scene_duration(
        self,
        project_id: str,
        scene_id: str,
        audio_duration: float,
    ) -> None:
        del project_id
        scene = self.repository.get_scene(scene_id)
        if scene is None:
            raise ValueError("scene not found")
        self.repository.update_scene(
            scene_id,
            duration_seconds=effective_scene_duration(
                audio_duration,
                scene.manual_hold_seconds,
            ),
        )

    def _record_item_failure(self, item: GenerationRunItem, error: Exception) -> None:
        current = self.repository.get_generation_run_item(item.item_id) or item
        changes: dict[str, Any] = {
            "status": GenerationRunItemStatus.FAILED,
            "error": str(error),
        }
        if current.status == GenerationRunItemStatus.RUNNING_TTS:
            changes["tts_status"] = GenerationPhase.FAILED
        elif current.status == GenerationRunItemStatus.RUNNING_IMAGE:
            changes["image_status"] = GenerationPhase.FAILED
        self.repository.update_generation_run_item(item.item_id, **changes)
        self.repository.update_scene(item.scene_id, status="failed")

    def _recover_interrupted_item(self, item: GenerationRunItem) -> None:
        changes: dict[str, Any] = {}
        if item.tts_status == GenerationPhase.RUNNING:
            changes["tts_status"] = GenerationPhase.PENDING
        if item.image_status == GenerationPhase.RUNNING:
            changes["image_status"] = GenerationPhase.PENDING
        if changes:
            changes["status"] = GenerationRunItemStatus.QUEUED
            self.repository.update_generation_run_item(item.item_id, **changes)

    async def _wait_for_resume_or_cancel(self, run_id: str) -> None:
        event = self._run_events.setdefault(run_id, asyncio.Event())
        while True:
            run = self._require_run(run_id)
            if not run.pause_requested or run.cancel_requested:
                return
            await event.wait()
            event.clear()

    async def _finalize(self, run_id: str) -> None:
        run = self.repository.recompute_generation_run_counts(run_id)
        status = (
            GenerationRunStatus.COMPLETED_WITH_FAILURES
            if run.failed_count
            else GenerationRunStatus.COMPLETED
        )
        self.repository.update_generation_run(
            run_id,
            status=status,
            current_scene_id=None,
        )
        self._publish_progress(run_id, "generation completed")
        if status == GenerationRunStatus.COMPLETED:
            await self._create_initial_export(run)

    async def _create_initial_export(self, run: GenerationRun) -> None:
        """Create one immutable first-draft export after a fully successful run."""
        if self.repository.get_export_revision_for_run(run.project_id, run.run_id):
            return
        scenes = self.repository.list_project_scenes(run.project_id)
        snapshot_scenes = []
        for scene in scenes:
            version = (
                self.repository.get_asset_version(scene.current_version_id)
                if scene.current_version_id
                else None
            )
            if version is None or not scene.audio_relative_path:
                return
            snapshot_scenes.append({
                "sceneId": scene.scene_id,
                "position": scene.position,
                "narration": scene.narration,
                "visualPrompt": scene.visual_prompt,
                "durationSeconds": scene.duration_seconds,
                "manualHoldSeconds": scene.manual_hold_seconds,
                "versionId": version.version_id,
                "imagePath": version.relative_path,
                "audioPath": scene.audio_relative_path,
            })
        project = self.repository.get_project(run.project_id)
        if project is None:
            return
        # Snapshot a lighter config for the automatic first draft so post-generation
        # wait is dominated by scene TTS, not multi-minute motion re-encode.
        draft_config = dict(project.config or {})
        draft_config["enableMotion"] = False
        draft_config["image_motion_enabled"] = False
        # Avoid stacking auto-draft export on top of a manual export already running.
        active = [
            rev
            for rev in self.repository.list_active_export_revisions()
            if rev.project_id == run.project_id
        ]
        if active:
            logger.info(
                "Skip initial draft export for run {}; project already has active export {}",
                run.run_id,
                active[0].export_id,
            )
            return

        if self.workbench_jobs and hasattr(self.workbench_jobs, "run_export_job"):
            task = self.task_manager.create_task(
                TaskType.WORKBENCH_EXPORT,
                request_params={
                    "project_id": run.project_id,
                    "purpose": "initial",
                    "createdFromRunId": run.run_id,
                },
            )
            revision = ExportRevision(run.project_id, {
                "projectId": run.project_id,
                "purpose": "initial",
                "createdFromRunId": run.run_id,
                "sceneOrder": [scene["sceneId"] for scene in snapshot_scenes],
                "scenes": snapshot_scenes,
                "config": draft_config,
                "allowIncomplete": False,
                "taskId": task.task_id,
            })
            self.repository.create_export_revision(revision)
            # Fire-and-forget: generation run is already COMPLETED; do not make
            # the worker appear stuck on the last scene while FFmpeg runs.
            await self.task_manager.execute_task(
                task.task_id,
                self.workbench_jobs.run_export_job,
                run.project_id,
                revision.export_id,
                task.task_id,
            )
            self._publish_progress(run.run_id, "scenes ready; initial draft export started")
        else:
            revision = ExportRevision(run.project_id, {
                "projectId": run.project_id,
                "purpose": "initial",
                "createdFromRunId": run.run_id,
                "sceneOrder": [scene["sceneId"] for scene in snapshot_scenes],
                "scenes": snapshot_scenes,
                "config": draft_config,
                "allowIncomplete": False,
            })
            self.repository.create_export_revision(revision)

    def _publish_progress(self, run_id: str, message: str) -> None:
        run = self.repository.get_generation_run(run_id)
        if run is None:
            return
        current = run.completed_count + run.skipped_count + run.failed_count + run.candidate_review_count
        self.task_manager.update_progress(
            run.task_id,
            current=current,
            total=run.total_count,
            message=message,
        )

    @staticmethod
    def _child_task_id(item: GenerationRunItem, phase: str) -> str:
        return f"{item.run_id}-{item.item_id}-{phase}"

    def _require_run(self, run_id: str) -> GenerationRun:
        run = self.repository.get_generation_run(run_id)
        if run is None:
            raise ValueError("generation run not found")
        return run
