from pathlib import Path


def test_history_items_can_open_workbench():
    root = Path(__file__).parents[2]
    history = (root / "frontend/src/components/HistoryList.tsx").read_text(encoding="utf-8")
    app = (root / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "打开工作台" in history
    assert "onOpenWorkbench" in history
    assert "createProjectFromHistory" in app

