from pathlib import Path


def test_batch_mode_expands_topics_into_independent_video_tasks():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "buildBatchTaskInputs" in quick_create
    assert "runWithConcurrency(taskInputs, 3" in quick_create
    assert "将创建" in quick_create and "个独立视频" in quick_create


def test_generation_submission_is_awaited_locked_and_confirmed():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "onGenerateTask: (taskInput: any) => Promise<boolean>" in quick_create
    assert "const [isSubmitting, setIsSubmitting]" in quick_create
    assert "const [reviewConfirmed, setReviewConfirmed]" in quick_create
    assert "disabled={isSubmitting || !reviewConfirmed}" in quick_create
    assert "await onGenerateTask" in quick_create
    assert "submissionLockRef.current" in quick_create
    assert "crypto.randomUUID()" in quick_create


def test_batch_submission_reports_partial_failures_truthfully():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "successfulSubmissions" in quick_create
    assert "taskInputs.length - successfulSubmissions" in quick_create
    assert "return true;" in app
    assert "return false;" in app


def test_generation_review_summarizes_critical_configuration():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    for label in ["视频数量", "分镜总数", "配音", "工作流", "画布", "字幕", "背景音乐", "预计旁白"]:
        assert label in quick_create
