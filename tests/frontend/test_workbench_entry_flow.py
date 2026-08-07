from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_quick_create_exposes_project_entry_callback():
    source = (ROOT / "frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    assert "onCreateProject" in source
    assert "onGenerateTask" in source
    assert 'handleTriggerRender(true)' in source
    assert "直接生成成片" in source
    assert "进入剪辑工作台" in source


def test_app_registers_project_workbench_tab():
    source = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert 'activeTab === "project-workbench"' in source
    assert "activeProjectId" in source
