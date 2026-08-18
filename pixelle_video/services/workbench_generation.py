"""Planning and freshness checks for project-level workbench generation."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from pixelle_video.models.workbench import (
    AssetSource,
    GenerationPhase,
    GenerationRun,
    GenerationRunItem,
    GenerationRunItemStatus,
    Project,
    Scene,
)
from pixelle_video.services.continuous_tts.assemble import normalize_tts_delivery

_SECRET_EXACT_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
}
_SECRET_SUFFIXES = ("_api_key", "_apikey", "_password", "_secret", "_token")


def _normalize_for_json(value: Any, *, key: str | None = None) -> Any:
    if key and _is_secret_key(key):
        return "***"
    if isinstance(value, Mapping):
        return {
            str(child_key): _normalize_for_json(child_value, key=str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_for_json(child) for child in value]
    if isinstance(value, set):
        return sorted(_normalize_for_json(child) for child in value)
    if hasattr(value, "value") and not isinstance(value, (str, bytes)):
        return _normalize_for_json(value.value, key=key)
    if hasattr(value, "isoformat") and not isinstance(value, (str, bytes)):
        return value.isoformat()
    if isinstance(value, str):
        return value.strip()
    return value


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in _SECRET_EXACT_KEYS or normalized.endswith(_SECRET_SUFFIXES)


def canonical_json(value: Any) -> str:
    """Serialize JSON-compatible values deterministically for fingerprints."""
    return json.dumps(
        _normalize_for_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _lookup(config: Mapping[str, Any], *paths: str | tuple[str, ...]) -> Any:
    for path in paths:
        parts = (path,) if isinstance(path, str) else path
        current: Any = config
        for part in parts:
            if not isinstance(current, Mapping) or part not in current:
                current = None
                break
            current = current[part]
        if current is not None:
            return current
    return None


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_tts_inference_mode(mode: Any) -> str:
    """Map frontend/backend TTS labels to the TTS service mode names."""
    value = str(mode or "local").strip().lower()
    if value in {"edge", "local"}:
        return "local"
    if value in {"minimax", "mimo", "qwen_audio", "comfyui"}:
        return value
    return "local"


def _looks_like_edge_voice(voice: str | None) -> bool:
    text = str(voice or "")
    return text.startswith("zh-") or "Neural" in text


def build_parameter_snapshot(
    project: Project,
    config_override: Mapping[str, Any] | None = None,
    runtime_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a complete, desensitized and stable snapshot for one run."""
    merged = _deep_merge(runtime_config or {}, project.config or {})
    if config_override:
        merged = _deep_merge(merged, config_override)

    tts_mode = normalize_tts_inference_mode(
        _lookup(
            merged,
            "ttsMode",
            "tts_mode",
            "tts_inference_mode",
            ("comfyui", "tts", "inference_mode"),
        )
        or "local"
    )
    default_voice = (
        "male-qn-qingse"
        if tts_mode == "minimax"
        else "mimo_default"
        if tts_mode == "mimo"
        else "Cherry"
        if tts_mode == "qwen_audio"
        else "zh-CN-YunjianNeural"
    )
    default_speed = 1.0 if tts_mode in {"minimax", "mimo"} else 1.2
    voice = _lookup(
        merged,
        "voice",
        "tts_voice",
        "voice_id",
        ("comfyui", "tts", "local", "voice"),
        ("comfyui", "tts", "minimax", "voice_id"),
        ("comfyui", "tts", "mimo", "voice_id"),
    ) or default_voice
    # Avoid feeding MiniMax/MiMo voice IDs into Edge TTS.
    if tts_mode == "local" and not _looks_like_edge_voice(str(voice)):
        voice = "zh-CN-YunjianNeural"
    speed = _lookup(
        merged,
        "speed",
        "tts_speed",
        ("comfyui", "tts", "local", "speed"),
        ("comfyui", "tts", "minimax", "speed"),
    )
    emotion = _lookup(
        merged,
        "emotion",
        "minimax_emotion",
        ("comfyui", "tts", "minimax", "emotion"),
    )
    # Model must match provider. Frontend always sends both minimaxModel and mimoModel;
    # looking up MiniMax first caused MiMo calls to receive speech-2.8-turbo.
    if tts_mode == "mimo":
        tts_model = _lookup(
            merged,
            "mimoModel",
            "mimo_model",
            ("comfyui", "tts", "mimo", "model"),
        ) or "mimo-v2.5-tts"
    elif tts_mode == "minimax":
        tts_model = _lookup(
            merged,
            "minimaxModel",
            "minimax_model",
            ("comfyui", "tts", "minimax", "model"),
        ) or "speech-2.8-turbo"
    elif tts_mode == "qwen_audio":
        tts_model = _lookup(merged, "qwenAudioModel", "qwen_audio_model", ("comfyui", "tts", "qwen_audio", "model")) or "qwen3-tts-flash"
    else:
        tts_model = None
    mimo_style = _lookup(
        merged,
        "mimoStyle",
        "mimo_style",
        ("comfyui", "tts", "mimo", "style"),
    )
    tts_workflow = _lookup(
        merged,
        "ttsWorkflow",
        "tts_workflow",
        ("comfyui", "tts", "comfyui", "default_workflow"),
    )
    # Phase-1 recommended default: continuous multi-scene synth + split.
    tts_delivery = normalize_tts_delivery(
        _lookup(
            merged,
            "ttsDelivery",
            "tts_delivery",
            ("comfyui", "tts", "delivery"),
        )
        or "continuous"
    )

    image_workflow = _lookup(
        merged,
        "workflow",
        "workflowId",
        "media_workflow",
        ("comfyui", "image", "default_workflow"),
    )
    image_model = _lookup(
        merged,
        "imageModel",
        "image_model",
        ("image_generation", "model"),
    )
    prompt_prefix = _lookup(
        merged,
        "promptPrefix",
        "prompt_prefix",
        ("comfyui", "image", "prompt_prefix"),
    ) or ""
    # Snapshot uses mapped API whitelist size (not raw canvas), so fingerprints
    # match the actual image-gen request dimensions.
    from pixelle_video.utils.video_canvas import image_gen_size_from_config

    gen_w, gen_h = image_gen_size_from_config(
        {
            "mediaWidth": _lookup(merged, "mediaWidth", "media_width", "imageWidth"),
            "mediaHeight": _lookup(merged, "mediaHeight", "media_height", "imageHeight"),
        }
    )

    return {
        "config": _normalize_for_json(merged),
        "tts": {
            "provider": tts_mode,
            "voice": str(voice),
            "speed": _number(speed, default_speed),
            "emotion": str(emotion).strip() if emotion not in (None, "") else None,
            "model": str(tts_model).strip() if tts_model not in (None, "") else None,
            "style": str(mimo_style).strip() if mimo_style not in (None, "") else None,
            "workflow": str(tts_workflow).strip() if tts_workflow not in (None, "") else None,
            "delivery": tts_delivery,
        },
        "image": {
            "provider": str(_lookup(merged, "imageProvider", "image_provider") or "comfyui"),
            "model": str(image_model).strip() if image_model is not None else None,
            "workflow": str(image_workflow).strip() if image_workflow is not None else None,
            "width": int(gen_w),
            "height": int(gen_h),
            "stylePrefix": str(prompt_prefix).strip(),
        },
    }


def compute_narration_fingerprint(
    narration: str,
    parameter_snapshot: Mapping[str, Any],
) -> str:
    return sha256_fingerprint(
        {
            "kind": "tts",
            "text": narration,
            "settings": parameter_snapshot.get("tts", {}),
        }
    )


def compute_image_fingerprint(
    visual_prompt: str,
    parameter_snapshot: Mapping[str, Any],
) -> str:
    return sha256_fingerprint(
        {
            "kind": "image",
            "prompt": visual_prompt,
            "settings": parameter_snapshot.get("image", {}),
        }
    )


@dataclass(frozen=True)
class _SceneFreshness:
    audio_ready: bool
    image_ready: bool


class ProjectGenerationPlanner:
    """Create immutable project generation plans without calling providers."""

    def __init__(self, repository, media_store, runtime_config: Mapping[str, Any] | None = None):
        self.repository = repository
        self.media_store = media_store
        self.runtime_config = copy.deepcopy(dict(runtime_config or {}))

    def plan_items(
        self,
        project: Project,
        scenes: Sequence[Scene],
        parameter_snapshot: Mapping[str, Any],
        scene_ids: Sequence[str] | None = None,
    ) -> list[GenerationRunItem]:
        selected = sorted(scenes, key=lambda scene: scene.position)
        if scene_ids is not None:
            requested = set(scene_ids)
            available = {scene.scene_id for scene in selected}
            unknown = requested - available
            if unknown:
                raise ValueError(f"scene not found: {sorted(unknown)[0]}")
            selected = [scene for scene in selected if scene.scene_id in requested]

        delivery = normalize_tts_delivery(
            (parameter_snapshot.get("tts") or {}).get("delivery")
            if isinstance(parameter_snapshot.get("tts"), Mapping)
            else "continuous"
        )
        items = []
        freshness_by_scene: dict[str, _SceneFreshness] = {}
        for scene in selected:
            narration_fingerprint = compute_narration_fingerprint(
                scene.narration,
                parameter_snapshot,
            )
            image_fingerprint = compute_image_fingerprint(
                scene.visual_prompt,
                parameter_snapshot,
            )
            freshness = self._freshness(
                project.project_id,
                scene,
                narration_fingerprint,
                image_fingerprint,
            )
            freshness_by_scene[scene.scene_id] = freshness
            items.append(
                {
                    "scene": scene,
                    "narration_fingerprint": narration_fingerprint,
                    "image_fingerprint": image_fingerprint,
                    "freshness": freshness,
                }
            )

        # Continuous delivery + multi-scene: default re-synth whole track when any
        # narration is stale so every cut comes from the same synthesis pass.
        force_full_tts = False
        if delivery == "continuous" and len(selected) > 1:
            force_full_tts = any(
                not entry["freshness"].audio_ready for entry in items
            )

        planned: list[GenerationRunItem] = []
        for entry in items:
            scene = entry["scene"]
            freshness = entry["freshness"]
            audio_ready = freshness.audio_ready and not force_full_tts
            tts_status = (
                GenerationPhase.SKIPPED
                if audio_ready
                else GenerationPhase.PENDING
            )
            image_status = (
                GenerationPhase.SKIPPED
                if freshness.image_ready
                else GenerationPhase.PENDING
            )
            if audio_ready and freshness.image_ready:
                status = GenerationRunItemStatus.SKIPPED
                skip_reason = "up_to_date"
            else:
                status = GenerationRunItemStatus.QUEUED
                ready_parts = []
                if audio_ready:
                    ready_parts.append("audio_up_to_date")
                elif force_full_tts and freshness.audio_ready:
                    ready_parts.append("audio_resync_continuous")
                if freshness.image_ready:
                    ready_parts.append("image_up_to_date")
                skip_reason = ",".join(ready_parts) or None
            planned.append(
                GenerationRunItem(
                    run_id="",
                    scene_id=scene.scene_id,
                    position=scene.position,
                    narration_snapshot=scene.narration,
                    prompt_snapshot=scene.visual_prompt,
                    narration_fingerprint=entry["narration_fingerprint"],
                    image_fingerprint=entry["image_fingerprint"],
                    tts_status=tts_status,
                    image_status=image_status,
                    status=status,
                    skip_reason=skip_reason,
                )
            )
        return planned

    def plan_run(
        self,
        project_id: str,
        task_id: str | None = None,
        scope: str = "incomplete",
        scene_ids: Sequence[str] | None = None,
        config_override: Mapping[str, Any] | None = None,
    ) -> tuple[GenerationRun, list[GenerationRunItem]]:
        if scope not in {"incomplete", "all"}:
            raise ValueError("scope must be incomplete or all")
        project = self.repository.get_project(project_id)
        if project is None:
            raise ValueError("project not found")
        scenes = self.repository.list_project_scenes(project_id)
        snapshot = build_parameter_snapshot(
            project,
            config_override=config_override,
            runtime_config=self.runtime_config,
        )
        items = self.plan_items(project, scenes, snapshot, scene_ids)
        run_id = uuid4().hex
        for item in items:
            item.run_id = run_id
        self._adopt_upload_baselines(project, scenes, items)
        run = GenerationRun(
            project_id=project_id,
            task_id=task_id or f"planner-{run_id}",
            parameter_snapshot=snapshot,
            run_id=run_id,
            total_count=len(items),
        )
        return run, items

    def plan_retry_failed(
        self,
        run_id: str,
        task_id: str | None = None,
        config_override: Mapping[str, Any] | None = None,
    ) -> tuple[GenerationRun, list[GenerationRunItem]]:
        previous = self.repository.get_generation_run(run_id)
        if previous is None:
            raise ValueError("generation run not found")
        failed_scene_ids = [
            item.scene_id
            for item in self.repository.list_generation_run_items(run_id)
            if item.status == GenerationRunItemStatus.FAILED
        ]
        if not failed_scene_ids:
            raise ValueError("generation run has no failed items")
        return self.plan_run(
            previous.project_id,
            task_id=task_id,
            scene_ids=failed_scene_ids,
            config_override=config_override,
        )

    def _freshness(
        self,
        project_id: str,
        scene: Scene,
        narration_fingerprint: str,
        image_fingerprint: str,
    ) -> _SceneFreshness:
        audio_ready = False
        if scene.audio_relative_path:
            try:
                audio_ready = (
                    self.media_store.resolve(project_id, scene.audio_relative_path).is_file()
                    and scene.audio_fingerprint == narration_fingerprint
                )
            except (OSError, ValueError):
                audio_ready = False

        image_ready = False
        if scene.current_version_id:
            version = self.repository.get_asset_version(scene.current_version_id)
            if version and version.project_id == project_id and version.scene_id == scene.scene_id:
                try:
                    file_exists = self.media_store.resolve(
                        project_id,
                        version.relative_path,
                    ).is_file()
                except (OSError, ValueError):
                    file_exists = False
                stored_fingerprint = (
                    version.parameters.get("imageFingerprint")
                    or version.parameters.get("image_fingerprint")
                    or scene.image_fingerprint
                )
                image_ready = file_exists and (
                    stored_fingerprint == image_fingerprint
                    or (
                        version.source == AssetSource.UPLOAD
                        and stored_fingerprint is None
                    )
                )
        return _SceneFreshness(audio_ready=audio_ready, image_ready=image_ready)

    def _adopt_upload_baselines(
        self,
        project: Project,
        scenes: Sequence[Scene],
        items: Sequence[GenerationRunItem],
    ) -> None:
        scenes_by_id = {scene.scene_id: scene for scene in scenes}
        for item in items:
            scene = scenes_by_id[item.scene_id]
            if scene.image_fingerprint is not None or item.image_status != GenerationPhase.SKIPPED:
                continue
            if not scene.current_version_id:
                continue
            version = self.repository.get_asset_version(scene.current_version_id)
            if version and version.source == AssetSource.UPLOAD:
                self.repository.update_scene(
                    scene.scene_id,
                    image_fingerprint=item.image_fingerprint,
                )


WorkbenchGenerationPlanner = ProjectGenerationPlanner
