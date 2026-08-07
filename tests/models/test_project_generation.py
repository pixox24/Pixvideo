from pixelle_video.models.workbench import (
    GenerationPhase,
    GenerationRun,
    GenerationRunItem,
    GenerationRunItemStatus,
    GenerationRunStatus,
)


def test_generation_run_status_values_are_stable():
    assert {status.value for status in GenerationRunStatus} == {
        "queued",
        "running",
        "paused",
        "completed",
        "completed_with_failures",
        "cancelled",
        "failed",
    }


def test_generation_run_terminal_states_are_explicit():
    run = GenerationRun(project_id="p1", task_id="task-1", parameter_snapshot={})

    for status in (
        GenerationRunStatus.COMPLETED,
        GenerationRunStatus.COMPLETED_WITH_FAILURES,
        GenerationRunStatus.CANCELLED,
        GenerationRunStatus.FAILED,
    ):
        run.status = status
        assert run.is_terminal

    for status in (
        GenerationRunStatus.QUEUED,
        GenerationRunStatus.RUNNING,
        GenerationRunStatus.PAUSED,
    ):
        run.status = status
        assert not run.is_terminal


def test_generation_run_item_defaults_to_pending_phases():
    item = GenerationRunItem(
        run_id="run-1",
        scene_id="scene-1",
        position=0,
        narration_snapshot="Narration",
        prompt_snapshot="Prompt",
        narration_fingerprint="audio-fingerprint",
        image_fingerprint="image-fingerprint",
    )

    assert item.item_id
    assert item.status == GenerationRunItemStatus.QUEUED
    assert item.tts_status == GenerationPhase.PENDING
    assert item.image_status == GenerationPhase.PENDING
    assert not item.is_terminal


def test_candidate_review_is_terminal_for_scheduling():
    item = GenerationRunItem(
        run_id="run-1",
        scene_id="scene-1",
        position=0,
        narration_snapshot="Narration",
        prompt_snapshot="Prompt",
        narration_fingerprint="audio-fingerprint",
        image_fingerprint="image-fingerprint",
        status=GenerationRunItemStatus.CANDIDATE_REVIEW,
    )

    assert item.is_terminal
    assert {phase.value for phase in GenerationPhase} == {
        "pending",
        "running",
        "completed",
        "skipped",
        "failed",
        "cancelled",
    }
