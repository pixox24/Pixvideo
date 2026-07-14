from pathlib import Path


def test_successful_llm_connection_persists_settings():
    component = Path("frontend/src/components/SystemSettingsTab.tsx").read_text(encoding="utf-8")

    assert 'if (service === "llm")' in component
    assert "await onSaveSettings(settings)" in component


def test_script_generation_shows_backend_error_detail():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "resData.detail" in component
    assert "formatApiErrorValue(resData.detail)" in component
    assert "formatApiErrorValue(resData.error)" in component
    assert '"脚本构思异常，请检查 LLM 设置。"' in component
