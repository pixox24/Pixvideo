"""Sequential, resumable orchestration for project generation runs."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from api.tasks.models import TaskType
from pixelle_video.models.workbench import (
    GenerationPhase,
    GenerationRun,
    GenerationRunItem,
    GenerationRunItemStatus,
    GenerationRunStatus,
    effective_scene_duration,
)
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

        task = self.task_manager.create_task(
            TaskType.WORKBENCH_PROJECT_RUN,
            request_params={
                "project_id": project_id,
                "scene_ids": list(scene_ids) if scene_ids is not None else None,
                "config_override": dict(config_override or {}),
            },
        )
        try:
            run, items = self.planner.plan_run(
                project_id,
                task_id=task.task_id,
                scene_ids=scene_ids,
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
        if run.pause_requested or run.status == GenerationRunStatus.PAUSED:
            return run
        changes: dict[str, Any] = {"pause_requested": True}
        if run.status == GenerationRunStatus.QUEUED:
            changes["status"] = GenerationRunStatus.PAUSED
        self.repository.update_generation_run(run_id, **changes)
        return self._require_run(run_id)

    async def request_resume(self, run_id: str) -> GenerationRun:
        run = self._require_run(run_id)
        if run.is_terminal:
            raise ValueError("generation run is already terminal")
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
            await self._ensure_task(run.run_id)
            scheduled.append(run.run_id)
        return scheduled

    def assert_scene_editable(self, project_id: str, scene_id: str) -> None:
        run = self.repository.get_active_generation_run(project_id)
        if run is None or run.current_scene_id != scene_id:
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
            item = next((candidate for candidate in items if not candidate.is_terminal), None)
            if item is None:
                self._finalize(run_id)
                return

            self.repository.update_generation_run(
                run_id,
                current_scene_id=item.scene_id,
            )
            self._recover_interrupted_item(item)
            try:
                await self._process_item(run_id, item)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._record_item_failure(item, exc)
            self.repository.recompute_generation_run_counts(run_id)
            self._publish_progress(run_id, f"scene {item.position + 1} finished")

    async def _process_item(self, run_id: str, item: GenerationRunItem) -> None:
        run = self._require_run(run_id)
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

    def _finalize(self, run_id: str) -> None:
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
