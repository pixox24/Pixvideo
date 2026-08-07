import json

import pytest
from PIL import Image

from pixelle_video.models.workbench import (
    AssetSource,
    AssetVersion,
    GenerationPhase,
    GenerationRun,
    GenerationRunItem,
    GenerationRunItemStatus,
    Project,
    Scene,
)
from pixelle_video.services.workbench_generation import (
    ProjectGenerationPlanner,
    build_parameter_snapshot,
    canonical_json,
    compute_image_fingerprint,
    compute_narration_fingerprint,
)
from pixelle_video.services.workbench_media import WorkbenchMediaStore
from pixelle_video.services.workbench_repository import WorkbenchRepository


def _setup(tmp_path, *, project_config=None, scene_count=1):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    media_store = WorkbenchMediaStore(tmp_path / "projects")
    project = Project("Planner project", project_config or {})
    scenes = [
        Scene(project.project_id, index, f"Narration {index}", f"Prompt {index}")
        for index in range(scene_count)
    ]
    repository.create_project(project, scenes)
    return repository, media_store, project, scenes


def _write_image(media_store, project_id, relative_path):
    path = media_store.resolve(project_id, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), "blue").save(path)


def test_canonical_json_and_fingerprint_are_stable():
    left = canonical_json({"b": " prompt ", "a": [" x ", 1]})
    right = canonical_json({"a": ["x", 1], "b": "prompt"})

    assert left == right
    assert compute_image_fingerprint("prompt", {"image": {"width": 1}}) == compute_image_fingerprint(
        " prompt ",
        {"image": {"width": 1}},
    )


def test_parameter_snapshot_merges_settings_and_redacts_secrets():
    project = Project(
        "Snapshot",
        {
            "ttsMode": "minimax",
            "voice": "voice-a",
            "speed": 1.1,
            "minimaxModel": "model-a",
            "mediaWidth": 1280,
            "mediaHeight": 720,
            "promptPrefix": "cinematic",
            "api_key": "project-secret",
        },
    )
    snapshot = build_parameter_snapshot(
        project,
        config_override={"speed": 1.2, "comfyui": {"runninghub_api_key": "runtime-secret"}},
    )

    assert snapshot["tts"] == {
        "provider": "minimax",
        "voice": "voice-a",
        "speed": 1.2,
        "emotion": None,
        "model": "model-a",
        "workflow": None,
    }
    assert snapshot["image"]["width"] == 1280
    assert snapshot["image"]["height"] == 720
    assert snapshot["image"]["stylePrefix"] == "cinematic"
    assert snapshot["config"]["api_key"] == "***"
    assert snapshot["config"]["comfyui"]["runninghub_api_key"] == "***"
    assert "project-secret" not in json.dumps(snapshot, ensure_ascii=False)
    assert "runtime-secret" not in json.dumps(snapshot, ensure_ascii=False)


def test_narration_and_image_fingerprints_are_independent():
    snapshot = {
        "tts": {"provider": "local", "voice": "voice-a", "speed": 1.0},
        "image": {"workflow": "workflow-a", "width": 1024, "height": 1536},
    }
    changed_narration = {
        **snapshot,
        "tts": {**snapshot["tts"], "voice": "voice-b"},
    }
    changed_image = {
        **snapshot,
        "image": {**snapshot["image"], "width": 720},
    }

    assert compute_narration_fingerprint("same", snapshot) != compute_narration_fingerprint(
        "same",
        changed_narration,
    )
    assert compute_narration_fingerprint("same", snapshot) == compute_narration_fingerprint(
        "same",
        changed_image,
    )
    assert compute_image_fingerprint("same", snapshot) != compute_image_fingerprint(
        "same",
        changed_image,
    )
    assert compute_image_fingerprint("same", snapshot) == compute_image_fingerprint(
        "same",
        changed_narration,
    )


def test_valid_audio_and_image_are_planned_as_skipped(tmp_path):
    repository, media_store, project, scenes = _setup(
        tmp_path,
        project_config={"voice": "voice-a", "mediaWidth": 512, "mediaHeight": 512},
    )
    scene = scenes[0]
    planner = ProjectGenerationPlanner(repository, media_store)
    snapshot = build_parameter_snapshot(project)
    audio_fingerprint = compute_narration_fingerprint(scene.narration, snapshot)
    image_fingerprint = compute_image_fingerprint(scene.visual_prompt, snapshot)
    audio_relative = f"assets/scenes/{scene.scene_id}/audio/current.mp3"
    image_relative = f"assets/scenes/{scene.scene_id}/current.png"
    media_store.resolve(project.project_id, audio_relative).parent.mkdir(parents=True, exist_ok=True)
    media_store.resolve(project.project_id, audio_relative).write_bytes(b"audio")
    _write_image(media_store, project.project_id, image_relative)
    repository.update_scene(
        scene.scene_id,
        audio_relative_path=audio_relative,
        audio_fingerprint=audio_fingerprint,
    )
    version = AssetVersion(
        project.project_id,
        scene.scene_id,
        AssetSource.AI,
        image_relative,
        parameters={"imageFingerprint": image_fingerprint},
    )
    repository.create_asset_version(version)
    repository.select_asset_version(project.project_id, scene.scene_id, version.version_id)

    items = planner.plan_items(project, [repository.get_scene(scene.scene_id)], snapshot)

    assert len(items) == 1
    assert items[0].status == GenerationRunItemStatus.SKIPPED
    assert items[0].tts_status == GenerationPhase.SKIPPED
    assert items[0].image_status == GenerationPhase.SKIPPED
    assert items[0].skip_reason == "up_to_date"
    repository.close()


def test_stale_audio_only_queues_tts_but_skips_image(tmp_path):
    repository, media_store, project, scenes = _setup(tmp_path)
    scene = scenes[0]
    planner = ProjectGenerationPlanner(repository, media_store)
    snapshot = build_parameter_snapshot(project)
    image_fingerprint = compute_image_fingerprint(scene.visual_prompt, snapshot)
    audio_relative = f"assets/scenes/{scene.scene_id}/audio/current.mp3"
    image_relative = f"assets/scenes/{scene.scene_id}/current.png"
    media_store.resolve(project.project_id, audio_relative).parent.mkdir(parents=True, exist_ok=True)
    media_store.resolve(project.project_id, audio_relative).write_bytes(b"audio")
    _write_image(media_store, project.project_id, image_relative)
    repository.update_scene(
        scene.scene_id,
        audio_relative_path=audio_relative,
        audio_fingerprint="old-audio",
    )
    version = AssetVersion(
        project.project_id,
        scene.scene_id,
        AssetSource.AI,
        image_relative,
        parameters={"imageFingerprint": image_fingerprint},
    )
    repository.create_asset_version(version)
    repository.select_asset_version(project.project_id, scene.scene_id, version.version_id)

    item = planner.plan_items(project, [repository.get_scene(scene.scene_id)], snapshot)[0]

    assert item.status == GenerationRunItemStatus.QUEUED
    assert item.tts_status == GenerationPhase.PENDING
    assert item.image_status == GenerationPhase.SKIPPED
    assert item.skip_reason == "image_up_to_date"
    repository.close()


def test_upload_without_fingerprint_is_adopted_as_ready_baseline(tmp_path):
    repository, media_store, project, scenes = _setup(tmp_path)
    scene = scenes[0]
    image_relative = f"assets/scenes/{scene.scene_id}/uploads/current.png"
    _write_image(media_store, project.project_id, image_relative)
    version = AssetVersion(
        project.project_id,
        scene.scene_id,
        AssetSource.UPLOAD,
        image_relative,
    )
    repository.create_asset_version(version)
    repository.select_asset_version(project.project_id, scene.scene_id, version.version_id)
    planner = ProjectGenerationPlanner(repository, media_store)

    run, items = planner.plan_run(project.project_id, task_id="task-1")
    saved_scene = repository.get_scene(scene.scene_id)

    assert run.total_count == 1
    assert items[0].image_status == GenerationPhase.SKIPPED
    assert saved_scene.image_fingerprint == items[0].image_fingerprint
    repository.update_scene(scene.scene_id, visual_prompt="Changed prompt")
    changed_item = planner.plan_items(
        project,
        [repository.get_scene(scene.scene_id)],
        build_parameter_snapshot(project),
    )[0]
    assert changed_item.image_status == GenerationPhase.PENDING
    repository.close()


def test_missing_assets_are_queued(tmp_path):
    repository, media_store, project, scenes = _setup(tmp_path)
    planner = ProjectGenerationPlanner(repository, media_store)

    item = planner.plan_items(
        project,
        scenes,
        build_parameter_snapshot(project),
    )[0]

    assert item.status == GenerationRunItemStatus.QUEUED
    assert item.tts_status == GenerationPhase.PENDING
    assert item.image_status == GenerationPhase.PENDING
    assert item.skip_reason is None
    repository.close()


def test_retry_failed_plans_only_failed_scenes_from_current_state(tmp_path):
    repository, media_store, project, scenes = _setup(tmp_path, scene_count=2)
    failed_run = GenerationRun(project.project_id, "old-task", {}, total_count=2)
    failed_items = [
        GenerationRunItem(
            run_id=failed_run.run_id,
            scene_id=scenes[0].scene_id,
            position=0,
            narration_snapshot=scenes[0].narration,
            prompt_snapshot=scenes[0].visual_prompt,
            narration_fingerprint="old-audio",
            image_fingerprint="old-image",
            status=GenerationRunItemStatus.FAILED,
        ),
        GenerationRunItem(
            run_id=failed_run.run_id,
            scene_id=scenes[1].scene_id,
            position=1,
            narration_snapshot=scenes[1].narration,
            prompt_snapshot=scenes[1].visual_prompt,
            narration_fingerprint="done-audio",
            image_fingerprint="done-image",
            status=GenerationRunItemStatus.COMPLETED,
        ),
    ]
    repository.create_generation_run(failed_run, failed_items)
    planner = ProjectGenerationPlanner(repository, media_store)

    retry_run, retry_items = planner.plan_retry_failed(failed_run.run_id, task_id="retry-task")

    assert retry_run.project_id == project.project_id
    assert retry_run.task_id == "retry-task"
    assert [item.scene_id for item in retry_items] == [scenes[0].scene_id]
    assert retry_items[0].narration_snapshot == scenes[0].narration
    repository.close()


def test_planner_rejects_unknown_scene_and_empty_retry(tmp_path):
    repository, media_store, project, scenes = _setup(tmp_path)
    planner = ProjectGenerationPlanner(repository, media_store)

    with pytest.raises(ValueError, match="scene not found"):
        planner.plan_run(project.project_id, scene_ids=["missing"])

    run = GenerationRun(project.project_id, "task-1", {}, total_count=1)
    item = GenerationRunItem(
        run_id=run.run_id,
        scene_id=scenes[0].scene_id,
        position=0,
        narration_snapshot=scenes[0].narration,
        prompt_snapshot=scenes[0].visual_prompt,
        narration_fingerprint="audio",
        image_fingerprint="image",
        status=GenerationRunItemStatus.COMPLETED,
    )
    repository.create_generation_run(run, [item])
    with pytest.raises(ValueError, match="no failed items"):
        planner.plan_retry_failed(run.run_id)
    repository.close()
