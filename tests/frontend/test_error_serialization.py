from pathlib import Path


def test_global_toast_boundary_serializes_unknown_error_values():
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "formatApiErrorValue(text)" in app
    assert "const addToast = (text: unknown" in app


def test_quick_create_uses_shared_api_error_formatter_for_direct_responses():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "formatApiErrorValue(resData.detail)" in quick_create
    assert "formatApiErrorValue(data.detail)" in quick_create
    assert "new Error(data.detail || data.error" not in quick_create


def test_app_never_coerces_structured_api_errors_through_error_constructor():
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    assert "new Error(data.detail || data.error" not in app
    assert "formatApiErrorValue(data.detail)" in app
    assert "formatApiErrorValue(data.error)" in app
