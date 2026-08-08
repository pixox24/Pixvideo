"""Progressive generation jobs for workbench scenes."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from pixelle_video.models.workbench import AssetSource, AssetVersion, GenerationStatus


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
        result = await self.core.media(
            prompt=prompt_snapshot,
            media_type="image",
            workflow=self._workflow(),
            width=self._width(),
            height=self._height(),
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
        result = await self.core.tts(
            text=narration_snapshot,
            output_path=str(audio_path),
            scene_id=scene_id,
        )
        if result and Path(str(result)).resolve() != audio_path.resolve() and Path(str(result)).is_file():
            shutil.copyfile(result, audio_path)
        if not audio_path.is_file():
            raise FileNotFoundError("TTS provider did not create an audio file")
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
            "image_motion_enabled": bool(config.get("image_motion_enabled", config.get("enableMotion", True))),
            "subtitle_enabled": config.get("subtitle_enabled", config.get("enableSubtitles", True)) is not False,
            "subtitle_style": config.get("subtitle_style", config.get("subtitleStyle")),
            "tts_inference_mode": config.get("tts_inference_mode", config.get("ttsMode", "local")),
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

    def _width(self):
        return int(self.core.config.get("workbench", {}).get("mediaWidth", 1024))

    def _height(self):
        return int(self.core.config.get("workbench", {}).get("mediaHeight", 1536))

    @staticmethod
    def _new_version_id():
        from uuid import uuid4
        return uuid4().hex
