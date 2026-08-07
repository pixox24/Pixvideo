from pathlib import Path


def test_export_dialog_mentions_blocking_and_incomplete_export():
    source = (Path(__file__).parents[2] / "frontend/src/components/ExportDialog.tsx").read_text(encoding="utf-8")
    assert "导出检查" in source
    assert "只导出当前已完成版本" in source
    assert "二次确认" in source
    assert "blocking" in source
    assert "onLocateScene" in source
    assert "未确认的 AI" in source
    assert "当前版本" in source

