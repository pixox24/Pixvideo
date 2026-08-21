from pathlib import Path


def test_api_task_mapping_keeps_backend_progress_metadata():
    api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")
    types = Path("frontend/src/types.ts").read_text(encoding="utf-8")

    assert "progressEventType" in types
    assert "progressFrameCurrent" in types
    assert "progressFrameTotal" in types
    assert "progressStep" in types
    assert "progressAction" in types
    assert "progressExtraInfo" in types

    assert "progressEventType: apiTask.progress?.event_type" in api
    assert "progressFrameCurrent: apiTask.progress?.frame_current" in api
    assert "progressFrameTotal: apiTask.progress?.frame_total" in api
    assert "progressStep: apiTask.progress?.step" in api
    assert "progressAction: apiTask.progress?.action" in api
    assert "progressExtraInfo: apiTask.progress?.extra_info" in api


def test_console_panel_uses_real_pipeline_order_and_current_stage():
    component = Path("frontend/src/components/ConsolePanel.tsx").read_text(encoding="utf-8")

    assert "GENERATION_PROGRESS_STEPS" in component
    assert "getProgressStageKey" in component
    assert "formatLiveProgressLabel" in component
    assert "当前步骤" in component
    assert "ui-chip" in component
    assert "text-[8px]" not in component
    assert "progressEventType" in component
    assert "progressAction" in component

    expected_order = [
        'key: "submit"',
        'key: "content"',
        'key: "title"',
        'key: "visuals"',
        'key: "audio"',
        'key: "media"',
        'key: "compose"',
        'key: "segment"',
        'key: "post"',
        'key: "completed"',
    ]
    positions = [component.index(item) for item in expected_order]
    assert positions == sorted(positions)

    assert "100 / steps.length" not in component
    assert "Math.floor(task.progress / stepThreshold)" not in component
