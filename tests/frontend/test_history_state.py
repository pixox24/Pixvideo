from pathlib import Path


def test_history_and_console_render_cancelled_as_its_own_state():
    history = Path("frontend/src/components/HistoryList.tsx").read_text(encoding="utf-8")
    console = Path("frontend/src/components/ConsolePanel.tsx").read_text(encoding="utf-8")

    assert '"cancelled"' in history
    assert "已取消" in history
    assert 'task.status === "cancelled"' in console
    assert "已取消" in console
    assert 'task.status === "failed" || task.status === "cancelled"' not in console
    assert 'status === "cancelled"' in console
    assert "STOP" in console


def test_running_tasks_offer_a_visible_cancel_action():
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    console = Path("frontend/src/components/ConsolePanel.tsx").read_text(encoding="utf-8")
    history = Path("frontend/src/components/HistoryList.tsx").read_text(encoding="utf-8")

    assert "handleCancelTask" in app
    assert "cancelTask(task.id)" in app
    assert "onCancelTask" in console
    assert "取消任务" in console
    assert 'task.status !== "generating"' in history
