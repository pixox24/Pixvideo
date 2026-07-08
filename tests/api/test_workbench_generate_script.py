import pytest
from fastapi import HTTPException

from api.routers import workbench


@pytest.mark.asyncio
async def test_generate_script_rejects_unsaved_llm_config(monkeypatch):
    monkeypatch.setattr(workbench.config_manager, "get_llm_config", lambda: {
        "api_key": "",
        "base_url": "",
        "model": "",
    })

    with pytest.raises(HTTPException) as exc_info:
        await workbench.generate_script(
            workbench.GenerateScriptRequest(topic="测试主题", sceneCount=3),
            pixelle_video=object(),
        )

    assert exc_info.value.status_code == 400
    assert "LLM 配置未保存" in exc_info.value.detail
