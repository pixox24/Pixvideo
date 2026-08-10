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
from pixelle_video.services.workbench_generation import (
    build_parameter_snapshot,
    normalize_tts_inference_mode,
)
from pixelle_video.utils.tts_audio_postprocess import postprocess_tts_clip, with_speaker_lock


class WorkbenchJobService:
    def __init__(self, core, repository, media_store):
        self.core = core
        self.repository = repository
        self.media_store = media_store
        concurrency = int(core.config.get("workbench", {}).get("scene_concurrency", 3))
        self._image_semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run_image_job_limited(self, project_id: str, scene_id: str, task_id: str, prompt_snapshot: str) -> None:
        async with self._image_semaphore:
            await self.run_image_job(project_id, scene_id, task_id, prompt_snapshot)

    async def run_scene_job(self, project_id: str, scene_id: str, task_id: str) -> None:
        scene = self._require_scene(scene_id, project_id)
        self._start(scene_id, task_id)
        try:
            await self.run_tts_job(project_id, scene_id, task_id, scene.narration)
            scene = self._require_scene(scene_id, project_id)
            await self.run_image_job(project_id, scene_id, task_id, scene.visual_prompt)
            self._finish(scene_id, task_id)
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
        """Generate and persist one image without changing job status."""
        scene = self._require_scene(scene_id, project_id)
        project = self.repository.get_project(project_id)
        project_config = (project.config if project else {}) or {}
        prefix = str(
            project_config.get("promptPrefix")
            or project_config.get("prompt_prefix")
            or ""
        ).strip()
        full_prompt = f"{prefix}, {prompt_snapshot}".strip(", ") if prefix else prompt_snapshot
        workflow = (
            project_config.get("workflowId")
            or project_config.get("workflow")
            or project_config.get("media_workflow")
            or self._workflow()
        )
        result = await self.core.media(
            prompt=full_prompt,
            media_type="image",
            workflow=workflow,
            width=self._width(project_id),
            height=self._height(project_id),
            scene_id=scene_id,
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
        has_current_version = scene.current_version_id is not None
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
        try:
            result = await self.core.tts(
                text=narration_snapshot,
                output_path=str(audio_path),
                scene_id=scene_id,
                **tts_kwargs,
            )
        except Exception as exc:
            # ComfyUI often unavailable in local installs; fall back to Edge TTS.
            if tts_kwargs.get("inference_mode") == "comfyui":
                logger.warning(
                    "ComfyUI TTS failed for project {}, falling back to Edge TTS: {}",
                    project_id,
                    exc,
                )
                result = await self.core.tts(
                    text=narration_snapshot,
                    output_path=str(audio_path),
                    scene_id=scene_id,
                    inference_mode="local",
                    voice="zh-CN-YunjianNeural",
                    speed=1.0,
                )
            else:
                raise
        if result and Path(str(result)).resolve() != audio_path.resolve() and Path(str(result)).is_file():
            shutil.copyfile(result, audio_path)
        if not audio_path.is_file():
            raise FileNotFoundError("TTS provider did not create an audio file")
        # Cross-scene consistency: loudness + short fades (does not re-synthesize).
        postprocess_tts_clip(audio_path)
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
        try:
            result = await self.core.tts(
                text=assembled.full_text,
                output_path=str(continuous_path),
                scene_id=anchor_scene_id,
                **tts_kwargs,
            )
        except Exception as exc:
            if tts_kwargs.get("inference_mode") == "comfyui":
                logger.warning(
                    "ComfyUI continuous TTS failed for project {}, falling back to Edge: {}",
                    project_id,
                    exc,
                )
                result = await self.core.tts(
                    text=assembled.full_text,
                    output_path=str(continuous_path),
                    scene_id=anchor_scene_id,
                    inference_mode="local",
                    voice="zh-CN-YunjianNeural",
                    speed=1.0,
                )
            else:
                raise

        if result and Path(str(result)).resolve() != continuous_path.resolve() and Path(str(result)).is_file():
            shutil.copyfile(result, continuous_path)
        if not continuous_path.is_file():
            raise FileNotFoundError("Continuous TTS provider did not create an audio file")

        # Light normalize on the whole track before cutting.
        postprocess_tts_clip(continuous_path)
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

        extract_audio_segments(
            continuous_path,
            [(path, start, end) for _scene_id, path, start, end, _rel in cut_jobs],
            batch_size=16,
        )

        for scene_id, audio_path, start, end, audio_relative in cut_jobs:
            duration = await self._audio_duration(audio_path)
            if duration <= 0:
                duration = max(0.05, float(end) - float(start))
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
            "Continuous TTS split done: project={} method={} scenes={}",
            project_id,
            slices[0].method if slices else "n/a",
            len(results),
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
        except Exception as exc:
            self._fail(scene_id, task_id, exc)
            raise

    async def run_export_job(self, project_id: str, export_id: str, task_id: str) -> None:
        revision = self.repository.get_export_revision(export_id)
        if revision is None or revision.project_id != project_id:
            raise ValueError("export revision not found")
        self.repository.update_export_revision(export_id, status=GenerationStatus.RUNNING)
        try:
            existing_assets = {}
            scenes = revision.snapshot.get("scenes") or []
            if not scenes:
                raise ValueError("export snapshot contains no complete scenes")
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
            result = await self.core.generate_video(**params)
            output_path = getattr(result, "video_path", None) or (result.get("video_path") if isinstance(result, dict) else None)
            if not output_path or not Path(output_path).is_file():
                raise ValueError("video pipeline did not produce an output file")
            output_relative = f"exports/{export_id}.mp4"
            destination = self.media_store.resolve(project_id, output_relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if Path(output_path).resolve() != destination.resolve():
                shutil.copyfile(output_path, destination)
            self.repository.update_export_revision(
                export_id,
                status=GenerationStatus.COMPLETED,
                output_relative_path=output_relative,
            )
        except Exception as exc:
            self.repository.update_export_revision(export_id, status=GenerationStatus.FAILED, error=str(exc))
            raise

    async def resume_active_exports(self, task_manager) -> list[str]:
        from api.tasks.models import TaskType

        task_ids = []
        for revision in self.repository.list_active_export_revisions():
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
        config = dict(snapshot.get("config") or {})
        scenes = list(snapshot.get("scenes") or [])
        bgm = config.get("bgm_path", config.get("bgm"))
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
        volume = config.get("bgm_volume", config.get("bgmVolume", 0.3))
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
        motion_enabled = bool(config.get("image_motion_enabled", config.get("enableMotion", True)))
        if purpose == "initial":
            motion_enabled = False

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
            "subtitle_enabled": config.get("subtitle_enabled", config.get("enableSubtitles", True)) is not False,
            "subtitle_style": config.get("subtitle_style", config.get("subtitleStyle")),
            "tts_inference_mode": normalize_tts_inference_mode(
                config.get("tts_inference_mode", config.get("ttsMode", "local"))
            ),
            "tts_voice": config.get("tts_voice", config.get("voice")),
            "tts_speed": config.get("tts_speed", config.get("speed")),
            "minimax_model": config.get("minimax_model", config.get("minimaxModel")),
            "minimax_emotion": config.get("minimax_emotion", config.get("emotion")),
            "media_workflow": config.get("media_workflow", config.get("workflowId")),
            "media_width": config.get("media_width", config.get("mediaWidth")),
            "media_height": config.get("media_height", config.get("mediaHeight")),
            "prompt_prefix": config.get("prompt_prefix", config.get("promptPrefix")),
            "bgm_path": bgm,
            "bgm_volume": max(0.0, min(1.0, volume)),
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
        return self._project_media_dimension(project_id, "mediaWidth", "media_width", 1024)

    def _height(self, project_id: str):
        return self._project_media_dimension(project_id, "mediaHeight", "media_height", 1536)

    @staticmethod
    def _new_version_id():
        from uuid import uuid4
        return uuid4().hex
