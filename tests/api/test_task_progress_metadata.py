from api.tasks.manager import TaskManager
from api.tasks.models import TaskType


def test_task_progress_keeps_structured_stage_fields():
    manager = TaskManager()
    task = manager.create_task(TaskType.VIDEO_GENERATION)

    manager.update_progress(
        task.task_id,
        42,
        100,
        "Frame 2/5 step 3: compose",
        event_type="frame_step",
        frame_current=2,
        frame_total=5,
        step=3,
        action="compose",
        extra_info="subtitle overlay",
    )

    progress = manager.get_task(task.task_id).progress
    assert progress.current == 42
    assert progress.total == 100
    assert progress.message == "Frame 2/5 step 3: compose"
    assert progress.event_type == "frame_step"
    assert progress.frame_current == 2
    assert progress.frame_total == 5
    assert progress.step == 3
    assert progress.action == "compose"
    assert progress.extra_info == "subtitle overlay"
