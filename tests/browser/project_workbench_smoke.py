"""Source-level smoke guard for responsive workbench controls."""

from pathlib import Path

root = Path(__file__).parents[2]
workbench = (root / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
panel = (root / "frontend/src/components/ProgressObservatory.tsx").read_text(encoding="utf-8")
timeline = (root / "frontend/src/components/WorkbenchTimeline.tsx").read_text(encoding="utf-8")

assert 'aria-label="打开分镜面板"' in workbench
assert 'aria-label="打开检查器"' in workbench
assert "lg:grid-cols" in workbench
assert "WorkbenchTimeline" in workbench or "pixelsPerSecond" in timeline
assert "ProgressObservatory" in workbench
assert "开始生成" in panel
assert "配音" in panel and "编码" in panel
print("project workbench browser smoke passed")
