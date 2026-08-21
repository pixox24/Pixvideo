"""PR-A: Soft Dark foundation tokens and utility classes must exist in index.css."""

from pathlib import Path

ROOT = Path("frontend/src")
CSS = (ROOT / "index.css").read_text(encoding="utf-8")
SELECT = (ROOT / "components/Select.tsx").read_text(encoding="utf-8")


def test_surface_and_border_tokens_defined():
    for token in [
        "--color-surface-0",
        "--color-surface-1",
        "--color-surface-2",
        "--color-surface-3",
        "--color-surface-4",
        "--color-border-subtle",
        "--color-border-default",
        "--color-border-strong",
        "--color-brand-400",
        "--color-brand-500",
        "--radius-md",
        "--radius-lg",
        "--radius-xl",
        "--radius-card",
        "--shadow-soft",
        "--shadow-stage",
        "--shadow-cta",
    ]:
        assert token in CSS, f"missing token {token}"


def test_ui_foundation_classes_defined():
    for cls in [
        ".ui-card",
        ".ui-panel",
        ".ui-stage",
        ".ui-btn",
        ".ui-btn-primary",
        ".ui-btn-secondary",
        ".ui-btn-ghost",
        ".ui-btn-outline",
        ".ui-btn-danger",
        ".ui-input",
        ".ui-chip",
        ".ui-sticky-footer",
        ".ui-segment",
    ]:
        assert cls in CSS, f"missing class {cls}"


def test_ui_segment_uses_aria_pressed():
    assert '.ui-segment > button[aria-pressed="true"]' in CSS
    assert "data-selected" not in CSS


def test_a11y_foundation_preserved():
    assert ":focus-visible" in CSS
    assert "prefers-reduced-motion" in CSS


def test_advanced_fold_component_exists():
    fold = (ROOT / "components/quickCreate/AdvancedFold.tsx").read_text(encoding="utf-8")
    assert "aria-expanded" in fold
    assert "<details>" not in fold and "</details>" not in fold


def test_quick_create_honeycomb_classes_cleared():
    qc = (ROOT / "components/QuickCreate.tsx").read_text(encoding="utf-8")
    preview = (ROOT / "components/SubtitleStylePreview.tsx").read_text(encoding="utf-8")
    for hay in (qc, preview):
        assert "border-zinc-800" not in hay
        assert "border-zinc-850" not in hay
        assert "border-zinc-900" not in hay
        assert "text-[10px]" not in hay
        assert "text-[8px]" not in hay
        assert "bg-[#17181c]" not in hay
        assert "bg-[#101114]" not in hay
        assert "bg-[#0c0d10]" not in hay
    assert "高级配音" in qc


def test_select_drops_important_zinc_skin():
    assert "!bg-[#17181c]" not in SELECT
    assert "!border-zinc-700" not in SELECT
    assert "bg-[#17181c]/98" not in SELECT
    assert "bg-[var(--color-surface-3)]" in SELECT
    assert "bg-[var(--color-surface-2)]" in SELECT
