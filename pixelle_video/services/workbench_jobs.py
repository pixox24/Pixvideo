"""Progressive generation jobs for workbench scenes."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from loguru import logger

from pixelle_video.models.workbench import AssetSource, AssetVersion, GenerationStatus
from pixelle_video.services.continuous_tts import (
    ContinuousSceneSegment,
    assemble_continuous_script,
    extract_audio_segments,
    plan_scene_slices,
)
from pixelle_video.services.generation_core import generate_scene_image, synthesize_speech
from pixelle_video.services.workbench_generation import (
    build_parameter_snapshot,
    normalize_tts_inference_mode,
)
from pixelle_video.utils.bookend import normalize_bookend_config
from pixelle_video.utils.project_config import normalize_project_config, pick_config
from pixelle_video.utils.tts_audio_postprocess import postprocess_tts_clip, with_speaker_lock
from pixelle_video.utils.video_canvas import (
    DEFAULT_VIDEO_HEIGHT,
    DEFAULT_VIDEO_WIDTH,
    image_gen_size_from_config,
    normalize_video_canvas,
)

_ORPHAN_JOB_ERROR = (
    "Job abandoned after server restart or cancel (was still pending/running). "
    "Retry the scene action if needed."
)


class WorkbenchJobService:
    def __init__(self, core, repository, media_store):
        self.core = core
        self.repository = repository
        self.media_store = media_store
        try:
            concurrency = int(core.config.get("workbench", {}).get("scene_concurrency", 6))
        except (TypeError, ValueError):
            concurrency = 6
        self._image_concurrency = max(1, min(16, concurrency))
        self._image_semaphore = asyncio.Semaphore(self._image_concurrency)

    async def run_image_job_limited(self, project_id: str, scene_id: str, task_id: str, prompt_snapshot: str) -> None:
        # Semaphore lives inside generate_image_asset so generation-run + batch share it.
        await self.run_image_job(project_id, scene_id, task_id, prompt_snapshot)

    async def run_scene_job(self, project_id: str, scene_id: str, task_id: str) -> None:
        scene = self._require_scene(scene_id, project_id)
        self._start(scene_id, task_id)
        try:
            await self.run_tts_job(project_id, scene_id, task_id, scene.narration)
            scene = self._require_scene(scene_id, project_id)
            await self.run_image_job(project_id, scene_id, task_id, scene.visual_prompt)
            self._finish(scene_id, task_id)
        except asyncio.CancelledError:
            self._cancel(scene_id, task_id)
            raise
        except Exception as exc:
            self._fail(scene_id, task_id, exc)
            raise

    async def generate_image_asset(
        self,
        project_id: str,
        scene_id: str,
        task_id: str,
        prompt_snapshot: str,
        image_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        """Generate and persist one image without changing job status.

        Concurrent callers share ``_image_semaphore`` so generation runs and
        batch regenerate do not stampede the image API.
        """
        async with self._image_semaphore:
            return await self._generate_image_asset_unlocked(
                project_id,
                scene_id,
                task_id,
                prompt_snapshot,
                image_fingerprint,
            )

    async def _generate_image_asset_unlocked(
        self,
        project_id: str,
        scene_id: str,
        task_id: str,
        prompt_snapshot: str,
        image_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        del task_id  # reserved for cancel/tracking identity
        scene = self._require_scene(scene_id, project_id)
        del scene
        project = self.repository.get_project(project_id)
        project_config = (project.config if project else {}) or {}
        prefix = str(
            project_config.get("promptPrefix")
            or project_config.get("prompt_prefix")
            or ""
        ).strip()
        workflow = (
            project_config.get("workflowId")
            or project_config.get("workflow")
            or project_config.get("media_workflow")
            or self._workflow()
        )
        # Image gen maps to API whitelist; mediaWidth/Height remain the video canvas.
        gen_w, gen_h = image_gen_size_from_config(project_config)
        use_api_raw = pick_config(project_config, "useApiImage", "use_api_image", default=False)
        if isinstance(use_api_raw, str):
            use_api_image = use_api_raw.strip().lower() in {"1", "true", "yes", "on", "api"}
        else:
            use_api_image = bool(use_api_raw)
        result = await generate_scene_image(
            self.core,
            prompt=prompt_snapshot,
            prefix=prefix,
            workflow=workflow,
            width=gen_w,
            height=gen_h,
            scene_id=scene_id,
            use_api_image=use_api_image,
        )
        source_url = result.url if hasattr(result, "url") else result
        version_id = self._new_version_id()
        relative_path = await self.media_store.download_result(
            project_id,
            scene_id,
            source_url,
            version_id,
        )
        absolute_path = self.media_store.resolve(project_id, relative_path)
        thumbnail = self.media_store.create_thumbnail(absolute_path, relative_path)
        parameters = {}
        if image_fingerprint:
            parameters["imageFingerprint"] = image_fingerprint
        version = AssetVersion(
            project_id,
            scene_id,
            AssetSource.AI,
            relative_path,
            prompt_snapshot=prompt_snapshot,
            version_id=version_id,
            thumbnail_relative_path=thumbnail,
            parameters=parameters,
        )
        self.repository.create_asset_version(version)
        # Re-read after long media await — user may have selected/uploaded meanwhile.
        fresh = self.repository.get_scene(scene_id)
        has_current_version = bool(fresh and fresh.current_version_id)
        if not has_current_version:
            self.repository.select_asset_version(project_id, scene_id, version_id)
            if image_fingerprint:
                self.repository.update_scene(
                    scene_id,
                    image_fingerprint=image_fingerprint,
                )
        return {
            "version_id": version_id,
            "relative_path": relative_path,
            "thumbnail_relative_path": thumbnail,
            "candidate": has_current_version,
        }

    async def run_image_job(self, project_id: str, scene_id: str, task_id: str, prompt_snapshot: str) -> None:
        self._require_scene(scene_id, project_id)
        self._start(scene_id, task_id)
        try:
            await self.generate_image_asset(
                project_id,
                scene_id,
                task_id,
                prompt_snapshot,
            )
            self._finish(scene_id, task_id)
        except asyncio.CancelledError:
            self._cancel(scene_id, task_id)
            raise
        except Exception as exc:
            self._fail(scene_id, task_id, exc)
            raise

    async def generate_tts_asset(
        self,
        project_id: str,
        scene_id: str,
        task_id: str,
        narration_snapshot: str,
        narration_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        """Generate and persist one audio asset without changing job status."""
        self._require_scene(scene_id, project_id)
        audio_relative = f"assets/scenes/{scene_id}/audio/{task_id}.mp3"
        audio_path = self.media_store.resolve(project_id, audio_relative)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        tts_kwargs = self._tts_kwargs_for_project(project_id)
        await synthesize_speech(
            self.core,
            text=narration_snapshot,
            output_path=str(audio_path),
            scene_id=scene_id,
            **tts_kwargs,
        )
        # TTS providers already post-process; keep a thread-offloaded pass for
        # paths that skip provider postprocess (e.g. copied external files).
        # Never block the asyncio event loop with sync ffmpeg.
        await asyncio.to_thread(postprocess_tts_clip, audio_path)
        duration = await self._audio_duration(audio_path)
        changes = {
            "narration": narration_snapshot,
            "audio_relative_path": audio_relative,
            "duration_seconds": duration,
        }
        if narration_fingerprint:
            changes["audio_fingerprint"] = narration_fingerprint
        self.repository.update_scene(scene_id, **changes)
        return {
            "audio_relative_path": audio_relative,
            "duration_seconds": duration,
        }

    async def generate_continuous_tts_assets(
        self,
        project_id: str,
        run_id: str,
        segments: list[ContinuousSceneSegment],
    ) -> dict[str, dict[str, Any]]:
        """
        Synthesize one continuous track for multi-scene narration, then split.

        Returns mapping scene_id -> {audio_relative_path, duration_seconds, split_method}.
        """
        if len(segments) < 2:
            raise ValueError("continuous TTS requires at least two scenes")

        assembled = assemble_continuous_script(segments)
        continuous_relative = f"assets/runs/{run_id}/continuous.mp3"
        continuous_path = self.media_store.resolve(project_id, continuous_relative)
        continuous_path.parent.mkdir(parents=True, exist_ok=True)

        tts_kwargs = self._tts_kwargs_for_project(project_id)
        # Use the first scene id so provider fakes / logs stay scene-addressable.
        anchor_scene_id = assembled.segments[0].scene_id
        logger.info(
            "Continuous TTS: project={} run={} scenes={} chars={}",
            project_id,
            run_id,
            len(assembled.segments),
            len(assembled.full_text),
        )
        await synthesize_speech(
            self.core,
            text=assembled.full_text,
            output_path=str(continuous_path),
            scene_id=anchor_scene_id,
            **tts_kwargs,
        )

        # Do NOT re-run loudnorm on the full continuous track here:
        # - Edge / MiniMax / MiMo already post-process the file they write
        # - a second full-track loudnorm can take minutes and used to block the
        #   FastAPI event loop, leaving the workbench stuck on「正在生成素材」
        total_duration = await self._audio_duration(continuous_path)
        if total_duration <= 0:
            # Fake / non-media fixtures: scale by scene count for proportional split.
            total_duration = float(len(assembled.segments))

        slices = plan_scene_slices(
            assembled.scene_ids,
            list(assembled.scene_texts),
            continuous_audio_path=continuous_path,
            total_duration=total_duration,
        )
        results: dict[str, dict[str, Any]] = {}
        fingerprint_by_scene = {
            segment.scene_id: segment.narration_fingerprint for segment in assembled.segments
        }
        narration_by_scene = {
            segment.scene_id: segment.narration for segment in assembled.segments
        }

        # Batch-cut in OS temp via few ffmpeg processes, then Python-move into project.
        # Skip per-scene loudnorm/fade: the continuous track was already post-processed.
        cut_jobs: list[tuple[str, Path, float, float, str]] = []
        for slice_info in slices:
            scene_id = slice_info.scene_id
            self._require_scene(scene_id, project_id)
            audio_relative = f"assets/scenes/{scene_id}/audio/{run_id}-continuous.mp3"
            audio_path = self.media_store.resolve(project_id, audio_relative)
            cut_jobs.append(
                (scene_id, audio_path, slice_info.start, slice_info.end, audio_relative)
            )

        # Sync ffmpeg batch cut — offload so polling/API stay responsive.
        cut_specs = [(path, start, end) for _scene_id, path, start, end, _rel in cut_jobs]
        await asyncio.to_thread(
            lambda: extract_audio_segments(continuous_path, cut_specs, batch_size=16)
        )

        # Slice full-track Edge/MiniMax alignment onto each scene clip (export burn).
        from pixelle_video.services.subtitle_alignment import (
            load_alignment,
            write_sliced_alignment_sidecar,
        )

        full_cues = load_alignment(continuous_path)
        aligned_sidecars = 0

        for scene_id, audio_path, start, end, audio_relative in cut_jobs:
            duration = await self._audio_duration(audio_path)
            if duration <= 0:
                duration = max(0.05, float(end) - float(start))
            if full_cues:
                try:
                    written = write_sliced_alignment_sidecar(
                        continuous_path,
                        audio_path,
                        start,
                        end,
                        cues=full_cues,
                    )
                    if written:
                        aligned_sidecars += 1
                except Exception as align_exc:
                    logger.debug(
                        "Failed to slice continuous alignment for scene {}: {}",
                        scene_id,
                        align_exc,
                    )
            changes = {
                "narration": narration_by_scene.get(scene_id, ""),
                "audio_relative_path": audio_relative,
                "duration_seconds": duration,
            }
            fingerprint = fingerprint_by_scene.get(scene_id)
            if fingerprint:
                changes["audio_fingerprint"] = fingerprint
            self.repository.update_scene(scene_id, **changes)
            results[scene_id] = {
                "audio_relative_path": audio_relative,
                "duration_seconds": duration,
                "split_method": next(
                    (s.method for s in slices if s.scene_id == scene_id),
                    "proportional",
                ),
                "slice_start": start,
                "slice_end": end,
            }

        logger.info(
            "Continuous TTS split done: project={} method={} scenes={} alignment_sidecars={}",
            project_id,
            slices[0].method if slices else "n/a",
            len(results),
            aligned_sidecars,
        )
        return results

    def _tts_kwargs_for_project(self, project_id: str) -> dict[str, Any]:
        """Resolve project/run TTS settings instead of relying on global ComfyUI defaults."""
        project = self.repository.get_project(project_id)
        runtime_config = getattr(self.core, "config", {}) or {}
        snapshot = build_parameter_snapshot(
            project or type("P", (), {"config": {}})(),
            runtime_config=runtime_config if isinstance(runtime_config, dict) else {},
        )
        tts = snapshot.get("tts") or {}
        mode = normalize_tts_inference_mode(tts.get("provider") or "local")
        scene_count = 0
        if project is not None:
            try:
                scene_count = len(self.repository.list_project_scenes(project_id))
            except Exception:
                scene_count = 0
        multi_scene = scene_count > 1
        kwargs: dict[str, Any] = {
            "inference_mode": mode,
            "voice": tts.get("voice"),
            "speed": tts.get("speed"),
        }
        if mode == "minimax":
            model = tts.get("model")
            # Guard: never send MiMo model names to MiniMax.
            if model and not str(model).startswith("mimo"):
                kwargs["minimax_model"] = model
            # Lock emotion for multi-scene: empty string means "no emotion switch".
            emotion = tts.get("emotion")
            if emotion:
                kwargs["minimax_emotion"] = emotion
            elif multi_scene:
                # Prefer neutral continuity over random emotion sampling when unset.
                kwargs["minimax_emotion"] = None
        elif mode == "mimo":
            project_config = (project.config if project else {}) or {}
            model = (
                project_config.get("mimoModel")
                or project_config.get("mimo_model")
                or tts.get("model")
                or "mimo-v2.5-tts"
            )
            # Guard: MiniMax speech-* models must never be sent to MiMo.
            if str(model).startswith("speech-") or str(model).startswith("Speech"):
                model = "mimo-v2.5-tts"
            kwargs["mimo_model"] = model
            style = tts.get("style") or project_config.get("mimoStyle") or project_config.get("mimo_style")
            is_voice_design = "voicedesign" in str(model).lower()
            # Multi-scene: pin the same speaker-lock phrase into every call.
            locked = with_speaker_lock(
                style,
                multi_scene=multi_scene,
                force=is_voice_design and multi_scene,
            )
            if locked:
                kwargs["mimo_style"] = locked
            if multi_scene and is_voice_design:
                logger.info(
                    "MiMo voice-design multi-scene: applying locked style for project {}",
                    project_id,
                )
        elif mode == "qwen_audio":
            project_config = (project.config if project else {}) or {}
            model = project_config.get("qwenAudioModel") or project_config.get("qwen_audio_model") or tts.get("model") or "qwen3-tts-flash"
            kwargs["qwen_audio_model"] = model
            kwargs["qwen_audio_mode"] = project_config.get("qwenAudioMode") or project_config.get("qwen_audio_mode") or tts.get("qwen_mode") or "preset"
            instruction = project_config.get("qwenAudioInstruction") or project_config.get("qwen_audio_instruction") or tts.get("qwen_instruction")
            if instruction:
                kwargs["qwen_audio_instruction"] = instruction
            ref_audio = project_config.get("qwenAudioRefAudio") or project_config.get("qwen_audio_ref_audio") or tts.get("qwen_ref_audio")
            if ref_audio:
                kwargs["qwen_audio_ref_audio"] = ref_audio
        elif mode == "comfyui" and tts.get("workflow"):
            kwargs["workflow"] = tts.get("workflow")
        # Drop only missing keys; keep explicit None for emotion lock path handled above.
        return {key: value for key, value in kwargs.items() if value is not None}

    async def run_tts_job(self, project_id: str, scene_id: str, task_id: str, narration_snapshot: str) -> None:
        self._require_scene(scene_id, project_id)
        self._start(scene_id, task_id)
        try:
            await self.generate_tts_asset(
                project_id,
                scene_id,
                task_id,
                narration_snapshot,
            )
            self.repository.update_scene(scene_id, status="completed")
            self._job_update(task_id, status=GenerationStatus.COMPLETED, progress=100)
        except asyncio.CancelledError:
            self._cancel(scene_id, task_id)
            raise
        except Exception as exc:
            self._fail(scene_id, task_id, exc)
            raise

    async def run_export_job(self, project_id: str, export_id: str, task_id: str) -> None:
        revision = self.repository.get_export_revision(export_id)
        if revision is None or revision.project_id != project_id:
            raise ValueError("export revision not found")
        self.repository.update_export_revision(export_id, status=GenerationStatus.RUNNING)
        scenes = revision.snapshot.get("scenes") or []
        segment_rows = [
            {
                "sceneId": str(item.get("sceneId") or ""),
                "position": int(item.get("position") if item.get("position") is not None else index),
                "status": "queued",
            }
            for index, item in enumerate(scenes)
        ]
        progress_state: dict[str, Any] = {
            "stage": "prepare",
            "segmentCurrent": 0,
            "segmentTotal": len(segment_rows),
            "segments": segment_rows,
            "updatedAt": None,
        }

        def publish_progress(*, stage: str | None = None, job_progress: float | None = None) -> None:
            if stage:
                progress_state["stage"] = stage
            from datetime import datetime, timezone

            progress_state["updatedAt"] = datetime.now(timezone.utc).isoformat()
            if hasattr(self.repository, "update_export_progress"):
                self.repository.update_export_progress(export_id, progress_state)
            if job_progress is not None:
                self._job_update(
                    task_id,
                    status=GenerationStatus.RUNNING,
                    progress=max(0.0, min(100.0, float(job_progress))),
                )

        def on_pipeline_progress(event) -> None:
            """Map standard pipeline ProgressEvent → per-scene segment status."""
            try:
                event_type = str(getattr(event, "event_type", "") or "")
                frame_current = getattr(event, "frame_current", None)
                frame_total = getattr(event, "frame_total", None) or len(segment_rows)
                action = str(getattr(event, "action", "") or "")
                raw_progress = float(getattr(event, "progress", 0) or 0)

                if event_type in {"processing_frame", "frame_step"} and frame_current:
                    idx = max(0, int(frame_current) - 1)
                    for i, row in enumerate(segment_rows):
                        if i < idx:
                            row["status"] = "ready"
                        elif i == idx:
                            row["status"] = "running"
                        elif row.get("status") not in {"ready", "failed"}:
                            row["status"] = "queued"
                    progress_state["segmentCurrent"] = int(frame_current)
                    progress_state["segmentTotal"] = int(frame_total)
                    # 10–85% reserved for segment encodes
                    pct = 10.0 + (max(0, idx) / max(1, int(frame_total))) * 70.0
                    if action == "video":
                        pct = min(85.0, pct + 2.0)
                    publish_progress(stage="segments", job_progress=pct)
                elif event_type == "concatenating":
                    for row in segment_rows:
                        if row.get("status") != "failed":
                            row["status"] = "ready"
                    progress_state["segmentCurrent"] = len(segment_rows)
                    publish_progress(stage="concat", job_progress=90.0)
                elif event_type == "completed":
                    for row in segment_rows:
                        if row.get("status") != "failed":
                            row["status"] = "ready"
                    publish_progress(stage="done", job_progress=98.0)
                else:
                    # Keep heartbeat on other events so UI stall detection stays fresh.
                    pct = 10.0 + max(0.0, min(1.0, raw_progress)) * 75.0
                    publish_progress(job_progress=pct)
            except Exception as exc:  # never break encode for progress UI
                logger.debug("export progress callback ignored error: {}", exc)

        try:
            existing_assets = {}
            if not scenes:
                raise ValueError("export snapshot contains no complete scenes")
            publish_progress(stage="prepare", job_progress=5.0)
            for item in scenes:
                image_path = item.get("imagePath")
                audio_path = item.get("audioPath")
                if not image_path or not audio_path:
                    raise ValueError("export snapshot contains an incomplete scene")
                image_absolute = self.media_store.resolve(project_id, image_path)
                if not image_absolute.is_file():
                    raise ValueError("export image is missing")
                audio_absolute = self.media_store.resolve(project_id, audio_path)
                if not audio_absolute.is_file():
                    raise ValueError("export audio is missing")
                existing_assets[item["sceneId"]] = {
                    "image_path": str(image_absolute),
                    "audio_path": str(audio_absolute),
                    "duration_seconds": max(
                        0.0,
                        float(item.get("durationSeconds") or 0)
                        - float(item.get("manualHoldSeconds") or 0),
                    ),
                    "manual_hold_seconds": max(0.0, float(item.get("manualHoldSeconds") or 0)),
                }
            if not hasattr(self.core, "generate_video") or self.core.generate_video is None:
                raise ValueError("video pipeline is unavailable")
            params = self._export_pipeline_params(project_id, task_id, revision.snapshot, existing_assets)
            params["progress_callback"] = on_pipeline_progress
            publish_progress(stage="segments", job_progress=10.0)
            result = await self.core.generate_video(**params)
            output_path = getattr(result, "video_path", None) or (result.get("video_path") if isinstance(result, dict) else None)
            if not output_path or not Path(output_path).is_file():
                raise ValueError("video pipeline did not produce an output file")
            publish_progress(stage="finalize", job_progress=95.0)
            output_relative = f"exports/{export_id}.mp4"
            destination = self.media_store.resolve(project_id, output_relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if Path(output_path).resolve() != destination.resolve():
                shutil.copyfile(output_path, destination)
            for row in segment_rows:
                if row.get("status") != "failed":
                    row["status"] = "ready"
            progress_state["segmentCurrent"] = len(segment_rows)
            publish_progress(stage="done", job_progress=100.0)
            self.repository.update_export_revision(
                export_id,
                status=GenerationStatus.COMPLETED,
                output_relative_path=output_relative,
            )
            self._job_update(task_id, status=GenerationStatus.COMPLETED, progress=100)
        except asyncio.CancelledError:
            for row in segment_rows:
                if row.get("status") == "running":
                    row["status"] = "failed"
            progress_state["error"] = "export cancelled"
            try:
                publish_progress(stage="failed", job_progress=None)
            except Exception:
                pass
            self.repository.update_export_revision(
                export_id,
                status=GenerationStatus.CANCELLED,
                error="export cancelled",
            )
            self._job_update(task_id, status=GenerationStatus.CANCELLED, error="export cancelled")
            raise
        except Exception as exc:
            # Mark current running segment failed when possible
            for row in segment_rows:
                if row.get("status") == "running":
                    row["status"] = "failed"
            progress_state["error"] = str(exc)
            publish_progress(stage="failed", job_progress=None)
            self.repository.update_export_revision(export_id, status=GenerationStatus.FAILED, error=str(exc))
            self._job_update(task_id, status=GenerationStatus.FAILED, error=str(exc))
            raise

    def abandon_orphan_scene_jobs(self, *, error: str = _ORPHAN_JOB_ERROR) -> int:
        """
        Mark non-terminal image/tts/scene jobs (and stuck scenes) as failed.

        Called on API startup — in-memory task manager does not resume these jobs.
        """
        abandoned = 0
        for job in self.repository.list_active_generation_jobs():
            self.repository.update_generation_job(
                job.job_id,
                status=GenerationStatus.FAILED,
                error=error,
            )
            if job.scene_id:
                scene = self.repository.get_scene(job.scene_id)
                # Only clear mid-flight scene status; leave idle pending scenes alone.
                if scene is not None and scene.status == "running":
                    self.repository.update_scene(job.scene_id, status="failed")
            abandoned += 1
        for scene in self.repository.list_scenes_by_status("running"):
            self.repository.update_scene(scene.scene_id, status="failed")
            abandoned += 1
        if abandoned:
            logger.warning("Abandoned {} orphan workbench job/scene record(s) on startup", abandoned)
        return abandoned

    async def resume_active_exports(self, task_manager) -> list[str]:
        from datetime import datetime, timezone, timedelta
        from api.tasks.models import TaskType

        task_ids = []
        # Exports stuck "running" across a crash/hang longer than this are abandoned
        # rather than auto-resumed into another multi-minute block on startup.
        stale_after = timedelta(minutes=20)
        now = datetime.now(timezone.utc)
        for revision in self.repository.list_active_export_revisions():
            updated = revision.updated_at
            if updated is not None and updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age = (now - updated) if updated is not None else timedelta(0)
            if age > stale_after:
                logger.warning(
                    "Skipping stale export {} (age {}); marking failed for manual retry",
                    revision.export_id,
                    age,
                )
                self.repository.update_export_revision(
                    revision.export_id,
                    status=GenerationStatus.FAILED,
                    error=(
                        f"Export abandoned after server restart "
                        f"(was active for {int(age.total_seconds() // 60)} min). "
                        "Click retry export."
                    ),
                )
                continue
            self.repository.update_export_revision(
                revision.export_id,
                status=GenerationStatus.PENDING,
                error=None,
            )
            task = task_manager.create_task(
                TaskType.WORKBENCH_EXPORT,
                request_params={
                    "project_id": revision.project_id,
                    "export_id": revision.export_id,
                    "resumed": True,
                },
            )
            await task_manager.execute_task(
                task.task_id,
                self.run_export_job,
                revision.project_id,
                revision.export_id,
                task.task_id,
            )
            task_ids.append(task.task_id)
        return task_ids

    @staticmethod
    def _export_pipeline_params(
        project_id: str,
        task_id: str,
        snapshot: dict[str, Any],
        existing_assets: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Translate a project snapshot into the existing standard pipeline contract."""
        # Prefer camel (editor) when both casings exist — history imports leave snake keys.
        config = normalize_project_config(dict(snapshot.get("config") or {}))
        scenes = list(snapshot.get("scenes") or [])
        bgm = pick_config(config, "bgm", "bgm_path")
        if not bgm or str(bgm).strip() in {"none", "bgm-none"}:
            bgm = None
        else:
            bgm = str(bgm).strip()
            relative_bgm = bgm
            for prefix in ("custom-bgm/", "data/bgm/", "bgm/"):
                if bgm.startswith(prefix):
                    relative_bgm = bgm.removeprefix(prefix)
                    break
            if (
                Path(relative_bgm).name != relative_bgm
                or "\\" in relative_bgm
                or Path(relative_bgm).suffix.lower() not in {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}
            ):
                raise ValueError("unsupported BGM reference in export snapshot")
        volume = pick_config(config, "bgmVolume", "bgm_volume", default=0.3)
        try:
            volume = float(volume)
            if volume > 1:
                volume /= 100
        except (TypeError, ValueError):
            volume = 0.3
        normalized_scenes = [
            {
                "sceneId": item.get("sceneId"),
                "narration": str(item.get("narration") or "").strip(),
                "visual_prompt": str(item.get("visualPrompt", item.get("visual_prompt")) or "").strip(),
            }
            for item in scenes
        ]
        # Initial auto-draft prioritizes speed so users don't feel "last scene stuck"
        # while FFmpeg re-encodes every frame with motion. Manual export keeps full quality.
        purpose = str(snapshot.get("purpose") or "").strip().lower()
        motion_enabled = bool(
            pick_config(config, "enableMotion", "image_motion_enabled", default=True)
        )
        if purpose == "initial":
            motion_enabled = False

        tts_delivery = str(
            pick_config(config, "ttsDelivery", "tts_delivery", "ttsDeliveryMode", default="")
            or ""
        ).strip().lower().replace("-", "_")
        # continuous (default for workbench multi-scene): rebuild speech from pure
        # narration files, pad each clip to its segment length so manual holds
        # become inter-clip silence (matches workbench preview).
        continuous_av_hold_split = tts_delivery in {
            "",
            "continuous",
            "cont",
            "1",
            "true",
        } or tts_delivery not in {"per_scene", "perscene", "segment", "scene", "legacy", "sequential"}
        # Explicit per_scene uses segment-embedded audio via legacy concat.
        if tts_delivery in {"per_scene", "perscene", "segment", "scene", "legacy", "sequential"}:
            continuous_av_hold_split = False
        # continuous always prefers the pure-speech re-mux path.
        if not continuous_av_hold_split and tts_delivery in {"continuous", "cont"}:
            continuous_av_hold_split = True

        canvas = normalize_video_canvas(config)
        subtitle_enabled = pick_config(config, "enableSubtitles", "subtitle_enabled", default=True)
        subtitle_enabled = subtitle_enabled is not False

        return {
            "pipeline": "standard",
            "text": str(config.get("title") or project_id),
            "title": str(config.get("title") or project_id),
            "task_id": task_id,
            "mode": "fixed",
            "scenes": normalized_scenes,
            "asset_reuse": True,
            "existing_scene_assets": existing_assets,
            "composition_mode": config.get("composition_mode", "plain_image"),
            "image_motion_enabled": motion_enabled,
            "subtitle_enabled": subtitle_enabled,
            "subtitle_style": pick_config(config, "subtitleStyle", "subtitle_style"),
            "tts_inference_mode": normalize_tts_inference_mode(
                pick_config(config, "ttsMode", "tts_inference_mode", default="local")
            ),
            "tts_voice": pick_config(config, "voice", "tts_voice"),
            "tts_speed": pick_config(config, "speed", "tts_speed"),
            "minimax_model": pick_config(config, "minimaxModel", "minimax_model"),
            "minimax_emotion": pick_config(config, "emotion", "minimax_emotion"),
            "media_workflow": pick_config(config, "workflowId", "media_workflow", "workflow"),
            "media_width": canvas["width"],
            "media_height": canvas["height"],
            "video_fps": canvas["fps"],
            "prompt_prefix": pick_config(config, "promptPrefix", "prompt_prefix"),
            "bgm_path": bgm,
            "bgm_volume": max(0.0, min(1.0, volume)),
            "continuous_av_hold_split": continuous_av_hold_split,
            "tts_delivery": tts_delivery or "continuous",
            "bookend": normalize_bookend_config(config),
        }

    def _require_scene(self, scene_id, project_id):
        scene = self.repository.get_scene(scene_id)
        if scene is None or scene.project_id != project_id:
            raise ValueError("scene not found")
        return scene

    def _start(self, scene_id, task_id):
        self.repository.update_scene(scene_id, status="running")
        self._job_update(task_id, status=GenerationStatus.RUNNING, progress=0)

    def _finish(self, scene_id, task_id):
        self.repository.update_scene(scene_id, status="completed")
        self._job_update(task_id, status=GenerationStatus.COMPLETED, progress=100)

    def _fail(self, scene_id, task_id, exc):
        self.repository.update_scene(scene_id, status="failed")
        self._job_update(task_id, status=GenerationStatus.FAILED, error=str(exc))

    def _cancel(self, scene_id, task_id):
        self.repository.update_scene(scene_id, status="cancelled")
        self._job_update(task_id, status=GenerationStatus.CANCELLED, error="cancelled")

    def _job_update(self, task_id, **changes):
        updater = getattr(self.repository, "update_generation_job_by_task_id", None)
        if updater:
            updater(task_id, **changes)

    async def _audio_duration(self, path: Path) -> float:
        processor = getattr(self.core, "frame_processor", None)
        if processor and hasattr(processor, "_get_audio_duration"):
            return float(await processor._get_audio_duration(str(path)))
        return 0.0

    async def get_audio_duration(self, project_id: str, scene_id: str) -> float:
        scene = self._require_scene(scene_id, project_id)
        if not scene.audio_relative_path:
            return 0.0
        path = self.media_store.resolve(project_id, scene.audio_relative_path)
        if not path.is_file():
            return 0.0
        return await self._audio_duration(path)

    def _workflow(self):
        return self.core.config.get("comfyui", {}).get("image", {}).get("default_workflow")

    def _project_media_dimension(self, project_id: str, camel_key: str, snake_key: str, default: int) -> int:
        project = self.repository.get_project(project_id)
        project_config = project.config if project is not None else {}
        value = project_config.get(camel_key, project_config.get(snake_key))
        if value is None:
            workbench_config = self.core.config.get("workbench", {})
            value = workbench_config.get(camel_key, workbench_config.get(snake_key, default))
        return int(value)

    def _width(self, project_id: str):
        """Video canvas width (export). Prefer mediaWidth; default 1080."""
        return self._project_media_dimension(
            project_id, "mediaWidth", "media_width", DEFAULT_VIDEO_WIDTH
        )

    def _height(self, project_id: str):
        """Video canvas height (export). Prefer mediaHeight; default 1920."""
        return self._project_media_dimension(
            project_id, "mediaHeight", "media_height", DEFAULT_VIDEO_HEIGHT
        )

    @staticmethod
    def _new_version_id():
        from uuid import uuid4
        return uuid4().hex
