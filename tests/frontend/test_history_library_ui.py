"""PR-E: History list as library card grid."""

from pathlib import Path

HISTORY = Path("frontend/src/components/HistoryList.tsx").read_text(encoding="utf-8")
EMPTY = Path("frontend/src/components/EmptyState.tsx").read_text(encoding="utf-8")


def test_history_uses_card_grid_and_library_title():
    assert "作品库" in HISTORY
    assert "grid-cols-1" in HISTORY
    assert "sm:grid-cols-2" in HISTORY
    assert "lg:grid-cols-3" in HISTORY
    assert "ui-card" in HISTORY


def test_history_preserves_actions():
    for marker in [
        "onOpenWorkbench",
        "onDeleteTask",
        "onResumeTask",
        "onCancelTask",
        "复制为项目",
        "download",
        "重试",
        "取消",
    ]:
        assert marker in HISTORY


def test_empty_state_uses_ui_card():
    assert "ui-card" in EMPTY
