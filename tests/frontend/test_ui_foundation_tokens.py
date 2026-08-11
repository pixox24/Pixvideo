"""PR-A: Soft Dark foundation tokens and utility classes must exist in index.css."""

from pathlib import Path

CSS = Path("frontend/src/index.css").read_text(encoding="utf-8")


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
    ]:
        assert cls in CSS, f"missing class {cls}"


def test_a11y_foundation_preserved():
    assert ":focus-visible" in CSS
    assert "prefers-reduced-motion" in CSS
