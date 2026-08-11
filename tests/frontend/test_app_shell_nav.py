"""PR-B: App shell navigation labels and soft-dark chrome."""

from pathlib import Path

APP = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
CONSOLE = Path("frontend/src/components/ConsolePanel.tsx").read_text(encoding="utf-8")
TOAST = Path("frontend/src/components/Toast.tsx").read_text(encoding="utf-8")


def test_nav_display_labels_are_creation_oriented():
    assert ">开始创作<" in APP or "开始创作" in APP
    assert ">精修<" in APP or "精修" in APP
    assert ">作品库<" in APP or "作品库" in APP
    assert ">设置<" in APP
    # ActiveTab keys must remain stable
    assert '"quick-create"' in APP
    assert '"project-workbench"' in APP
    assert '"history"' in APP
    assert '"settings"' in APP


def test_sidebar_uses_soft_dark_surface_tokens():
    assert "bg-[var(--color-surface-1)]" in APP
    assert "border-[var(--color-border-subtle)]" in APP
    assert "w-60" in APP
    assert "ring-1 ring-amber-500/20" in APP
    assert "statusExpanded" in APP
    assert "useState(false)" in APP  # collapsed by default (includes statusExpanded)


def test_mobile_overlay_uses_backdrop_blur():
    assert "backdrop-blur-sm" in APP


def test_console_and_toast_soft_chrome():
    assert "border-[var(--color-border-subtle)]" in CONSOLE
    assert "bg-[var(--color-surface-1)]" in CONSOLE
    assert "shadow-[var(--shadow-soft)]" in TOAST
