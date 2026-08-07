"""Source-level smoke guard for responsive workbench controls.

Interactive browser verification is run against the local Vite server during
release checks; this script keeps its required accessibility hooks stable.
"""

from pathlib import Path

root = Path(__file__).parents[2]
workbench = (root / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
timeline = (root / "frontend/src/components/WorkbenchTimeline.tsx").read_text(encoding="utf-8")

assert "打开分镜面板" in workbench
assert "打开检查器" in workbench
assert "lg:grid-cols" in workbench
assert "overflow-x-auto" in timeline
assert "导出" in workbench
print("project workbench browser smoke passed")
