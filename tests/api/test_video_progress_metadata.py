from pathlib import Path


def test_video_router_forwards_progress_event_metadata_to_task_manager():
    router = Path("api/routers/video.py").read_text()

    assert "event_type=event.event_type" in router
    assert "frame_current=event.frame_current" in router
    assert "frame_total=event.frame_total" in router
    assert "step=event.step" in router
    assert "action=event.action" in router
    assert "extra_info=event.extra_info" in router
