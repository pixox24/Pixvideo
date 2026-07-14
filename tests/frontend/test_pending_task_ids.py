import re
from pathlib import Path


def _app_block(name: str, next_marker: str) -> str:
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    match = re.search(
        rf"const {name} = async.*?^  {re.escape(next_marker)}",
        app,
        flags=re.S | re.M,
    )
    assert match is not None
    return match.group(0)


def test_pending_task_ids_are_identified_as_local_only_tasks():
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert 'const PENDING_TASK_ID_PREFIX = "pending-";' in app
    assert "taskId.startsWith(PENDING_TASK_ID_PREFIX)" in app
    assert "const tempTaskId = `${PENDING_TASK_ID_PREFIX}${crypto.randomUUID()}`;" in app


def test_pending_task_delete_never_calls_backend_history_delete():
    block = _app_block("handleDeleteTask", "const pollBackendTask")

    guard_index = block.index("isPendingTaskId(id)")
    backend_index = block.index("deleteHistoryTask(id)")

    assert guard_index < backend_index
    assert "return;" in block[guard_index:backend_index]


def test_pending_task_resume_never_calls_backend_history_resume():
    block = _app_block("handleResumeTask", "const handleSaveSettings")

    guard_index = block.index("isPendingTaskId(task.id)")
    backend_index = block.index("resumeHistoryTask(task.id)")

    assert guard_index < backend_index
    assert "return;" in block[guard_index:backend_index]


def test_pending_task_polling_never_calls_backend_task_fetch():
    block = _app_block("pollBackendTask", "// Launch new video generation task")

    guard_index = block.index("isPendingTaskId(taskId)")
    backend_index = block.index("fetchTask(taskId)")

    assert guard_index < backend_index
    assert "return;" in block[guard_index:backend_index]


def test_pending_task_cancel_is_forwarded_after_backend_id_arrives():
    cancel_block = _app_block("handleCancelTask", "const pollBackendTask")
    submit_block = _app_block("handleGenerateTask", "// Resume or Retry failed task")

    assert "pendingCancellationIdsRef.current.add(task.id)" in cancel_block
    assert "prev.filter((item) => item.id !== task.id)" not in cancel_block
    assert "pendingCancellationIdsRef.current.delete(tempTaskId)" in submit_block
    assert "await cancelTask(response.task_id)" in submit_block
