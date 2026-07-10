from pathlib import Path


def test_workspace_shell_is_centered_for_large_displays():
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "max-w-[1680px]" in app
    assert "justify-center" in app
    assert "h-full flex min-w-0" in app


def test_quick_create_and_console_are_wider_on_large_screens():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    console = Path("frontend/src/components/ConsolePanel.tsx").read_text(encoding="utf-8")

    assert "max-w-[1240px]" in quick_create
    assert "mx-auto" in quick_create
    assert "lg:w-96" in console
    assert "xl:w-[400px]" in console
    assert "lg:w-80" not in console
