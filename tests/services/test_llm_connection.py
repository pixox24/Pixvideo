from pixelle_video.utils import llm_util


def test_llm_connection_accepts_selected_model(monkeypatch):
    monkeypatch.setattr(
        llm_util,
        "fetch_available_models",
        lambda api_key, base_url, timeout=10.0: ["deepseek-v4-flash", "deepseek-v4-pro"],
    )

    success, message, model_count = llm_util.test_llm_connection(
        "test-key",
        "https://api.deepseek.com",
        model="deepseek-v4-pro",
    )

    assert success is True
    assert "deepseek-v4-pro" in message
    assert model_count == 2


def test_llm_connection_rejects_missing_selected_model(monkeypatch):
    monkeypatch.setattr(
        llm_util,
        "fetch_available_models",
        lambda api_key, base_url, timeout=10.0: ["deepseek-v4-flash"],
    )

    success, message, model_count = llm_util.test_llm_connection(
        "test-key",
        "https://api.deepseek.com",
        model="deepseek-v4-pro",
    )

    assert success is False
    assert "deepseek-v4-pro" in message
    assert model_count == 1


def test_llm_connection_rejects_missing_api_key():
    success, message, model_count = llm_util.test_llm_connection(
        "",
        "https://api.deepseek.com",
        model="deepseek-v4-pro",
    )

    assert success is False
    assert message == "Authentication failed: API Key is missing"
    assert model_count == 0
