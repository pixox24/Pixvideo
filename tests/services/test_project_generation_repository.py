import sqlite3
from datetime import datetime, timezone

import pytest

from pixelle_video.models.workbench import (
    GenerationPhase,
    GenerationRun,
    GenerationRunItem,
    GenerationRunItemStatus,
    GenerationRunStatus,
    Project,
    Scene,
)
from pixelle_video.services.workbench_repository import WorkbenchRepository


def _project_with_scenes(repository: WorkbenchRepository, count: int = 2):
    project = Project(title="Generation project", config={"voice": "test"})
    scenes = [
        Scene(project.project_id, position, f"Narration {position}", f"Prompt {position}")
        for position in range(count)
    ]
    repository.create_project(project, scenes)
    return project, scenes


def _run_with_items(project: Project, scenes: list[Scene]):
    run = GenerationRun(
        project_id=project.project_id,
        task_id="task-1",
        parameter_snapshot={"voice": "test"},
        total_count=len(scenes),
    )
    items = [
        GenerationRunItem(
            run_id=run.run_id,
            scene_id=scene.scene_id,
            position=scene.position,
            narration_snapshot=scene.narration,
            prompt_snapshot=scene.visual_prompt,
            narration_fingerprint=f"audio-{scene.position}",
            image_fingerprint=f"image-{scene.position}",
        )
        for scene in scenes
    ]
    return run, items


def test_schema_adds_generation_tables_indexes_and_scene_fingerprints(tmp_path):
    db_path = tmp_path / "workbench.sqlite3"
    repository = WorkbenchRepository(db_path)
    repository.close()

    connection = sqlite3.connect(db_path)
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    scene_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(scenes)").fetchall()
    }
    run_indexes = {
        row[1] for row in connection.execute("PRAGMA index_list(generation_runs)").fetchall()
    }
    item_indexes = {
        row[1]
        for row in connection.execute("PRAGMA index_list(generation_run_items)").fetchall()
    }
    connection.close()

    assert {"generation_runs", "generation_run_items"}.issubset(tables)
    assert {"image_fingerprint", "audio_fingerprint"}.issubset(scene_columns)
    assert "idx_generation_runs_project_status" in run_indexes
    assert "idx_generation_run_items_run_position" in item_indexes


def test_existing_scene_table_is_migrated_without_losing_rows(tmp_path):
    db_path = tmp_path / "legacy.sqlite3"
    timestamp = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE projects (
          project_id TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL,
          source_history_task_id TEXT UNIQUE, config_json TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE scenes (
          scene_id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
          position INTEGER NOT NULL, narration TEXT NOT NULL,
          visual_prompt TEXT NOT NULL DEFAULT '', current_version_id TEXT,
          audio_relative_path TEXT, subtitle_alignment_json TEXT NOT NULL DEFAULT '[]',
          duration_seconds REAL NOT NULL DEFAULT 0,
          manual_hold_seconds REAL NOT NULL DEFAULT 0,
          duration_mode TEXT NOT NULL DEFAULT 'audio',
          status TEXT NOT NULL DEFAULT 'pending', updated_at TEXT NOT NULL,
          UNIQUE(project_id, position)
        );
        """
    )
    connection.execute(
        "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("p1", "Legacy", "quick-create", None, "{}", timestamp, timestamp),
    )
    connection.execute(
        "INSERT INTO scenes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("s1", "p1", 0, "Narration", "Prompt", None, None, "[]", 0, 0, "audio", "pending", timestamp),
    )
    connection.commit()
    connection.close()

    repository = WorkbenchRepository(db_path)
    scene = repository.get_scene("s1")

    assert scene is not None
    assert scene.narration == "Narration"
    assert scene.image_fingerprint is None
    assert scene.audio_fingerprint is None
    repository.close()


def test_generation_run_and_items_round_trip_after_reopening(tmp_path):
    db_path = tmp_path / "workbench.sqlite3"
    repository = WorkbenchRepository(db_path)
    project, scenes = _project_with_scenes(repository)
    run, items = _run_with_items(project, scenes)

    repository.create_generation_run(run, items)
    repository.update_generation_run(
        run.run_id,
        status=GenerationRunStatus.RUNNING,
        current_scene_id=scenes[0].scene_id,
        pause_requested=True,
    )
    repository.update_generation_run_item(
        items[0].item_id,
        status=GenerationRunItemStatus.RUNNING_TTS,
        tts_status=GenerationPhase.RUNNING,
    )
    repository.update_scene(
        scenes[0].scene_id,
        image_fingerprint="saved-image-fingerprint",
        audio_fingerprint="saved-audio-fingerprint",
    )
    repository.close()

    reopened = WorkbenchRepository(db_path)
    loaded_run = reopened.get_generation_run(run.run_id)
    loaded_items = reopened.list_generation_run_items(run.run_id)
    loaded_scene = reopened.get_scene(scenes[0].scene_id)

    assert loaded_run is not None
    assert loaded_run.status == GenerationRunStatus.RUNNING
    assert loaded_run.parameter_snapshot == {"voice": "test"}
    assert loaded_run.pause_requested is True
    assert loaded_items[0].status == GenerationRunItemStatus.RUNNING_TTS
    assert loaded_items[0].tts_status == GenerationPhase.RUNNING
    assert loaded_scene.image_fingerprint == "saved-image-fingerprint"
    assert loaded_scene.audio_fingerprint == "saved-audio-fingerprint"
    assert [item.scene_id for item in loaded_items] == [
        scenes[0].scene_id,
        scenes[1].scene_id,
    ]
    reopened.close()


def test_generation_run_creation_rolls_back_when_any_item_fails(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    project, scenes = _project_with_scenes(repository, count=1)
    run, items = _run_with_items(project, scenes)
    duplicate = GenerationRunItem(
        run_id=run.run_id,
        scene_id=scenes[0].scene_id,
        position=1,
        narration_snapshot="Duplicate",
        prompt_snapshot="Duplicate",
        narration_fingerprint="duplicate-audio",
        image_fingerprint="duplicate-image",
    )

    with pytest.raises(sqlite3.IntegrityError):
        repository.create_generation_run(run, [items[0], duplicate])

    assert repository.get_generation_run(run.run_id) is None
    assert repository.list_generation_run_items(run.run_id) == []
    repository.close()


def test_active_run_ignores_terminal_runs(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    project, scenes = _project_with_scenes(repository, count=1)
    completed, completed_items = _run_with_items(project, scenes)
    completed.task_id = "task-completed"
    completed.status = GenerationRunStatus.COMPLETED
    active, active_items = _run_with_items(project, scenes)
    active.task_id = "task-active"

    repository.create_generation_run(completed, completed_items)
    repository.create_generation_run(active, active_items)

    assert repository.get_active_generation_run(project.project_id).run_id == active.run_id
    repository.update_generation_run(active.run_id, status=GenerationRunStatus.CANCELLED)
    assert repository.get_active_generation_run(project.project_id) is None
    repository.close()


def test_recompute_counts_keeps_candidate_review_separate(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    project, scenes = _project_with_scenes(repository, count=4)
    run, items = _run_with_items(project, scenes)
    repository.create_generation_run(run, items)
    statuses = [
        GenerationRunItemStatus.COMPLETED,
        GenerationRunItemStatus.SKIPPED,
        GenerationRunItemStatus.FAILED,
        GenerationRunItemStatus.CANDIDATE_REVIEW,
    ]
    for item, status in zip(items, statuses, strict=True):
        repository.update_generation_run_item(item.item_id, status=status)

    updated = repository.recompute_generation_run_counts(run.run_id)

    assert updated.completed_count == 1
    assert updated.skipped_count == 1
    assert updated.failed_count == 1
    assert updated.candidate_review_count == 1
    repository.close()


def test_mark_remaining_items_cancelled_only_changes_queued_items(tmp_path):
    repository = WorkbenchRepository(tmp_path / "workbench.sqlite3")
    project, scenes = _project_with_scenes(repository)
    run, items = _run_with_items(project, scenes)
    repository.create_generation_run(run, items)
    repository.update_generation_run_item(
        items[0].item_id,
        status=GenerationRunItemStatus.COMPLETED,
        tts_status=GenerationPhase.COMPLETED,
        image_status=GenerationPhase.COMPLETED,
    )

    repository.mark_remaining_run_items_cancelled(run.run_id)
    loaded = repository.list_generation_run_items(run.run_id)

    assert loaded[0].status == GenerationRunItemStatus.COMPLETED
    assert loaded[1].status == GenerationRunItemStatus.CANCELLED
    assert loaded[1].tts_status == GenerationPhase.CANCELLED
    assert loaded[1].image_status == GenerationPhase.CANCELLED
    repository.close()
