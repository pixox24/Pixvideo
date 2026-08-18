import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.routers import workbench


class FakeSegmentationLLM:
    def __init__(self, response: str):
        self.response = response
        self.calls: list[dict] = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_storyboard_analysis_rejects_blank_text():
    with pytest.raises(ValidationError):
        workbench.StoryboardAnalyzeRequest(text="   ")


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


@pytest.mark.asyncio
async def test_storyboard_analysis_returns_units_duration_and_warnings():
    source = "星期一的早晨，我们打开日历，发现距离发布会只剩三天。"
    result = await workbench.analyze_storyboard(
        workbench.StoryboardAnalyzeRequest(
            text=source,
            splitType="auto",
            segmentationMode="deterministic",
        ),
        pixelle_video=object(),
    )

    assert result["success"] is True
    assert result["sourceText"] == source
    assert result["semanticSceneCount"] >= 1
    assert result["units"][0]["text"]
    assert result["units"][0]["estimatedSeconds"] > 0
    assert result["charCount"] == len(source.replace(" ", ""))
    assert "星期一" in result["units"][0]["textAnchors"]


@pytest.mark.asyncio
async def test_storyboard_analysis_uses_validated_llm_boundaries_for_long_unit():
    source = "今天我们从日历开始规划发布会倒计时并把每一个任务安排到准确的时间线上同时检查人员物料场地和最终确认清单确保发布当天万无一失"
    response = (
        '{"segments":['
        '{"text":"今天我们从日历开始规划发布会倒计时",'
        '"boundary_reason":"先建立时间锚点",'
        '"visual_focus":"日历和倒计时标记"},'
        '{"text":"并把每一个任务安排到准确的时间线上同时检查人员物料场地和最终确认清单确保发布当天万无一失",'
        '"boundary_reason":"转入执行动作",'
        '"visual_focus":"时间线和任务卡片"}'
        ']}'
    )
    llm = FakeSegmentationLLM(response)
    result = await workbench.analyze_storyboard(
        workbench.StoryboardAnalyzeRequest(
            text=source,
            splitType="auto",
            sceneCount=3,
            segmentationMode="auto",
        ),
        pixelle_video=type("Core", (), {"llm": llm})(),
    )

    assert result["usedLlm"] is True
    assert [unit["text"] for unit in result["units"]] == [
        "今天我们从日历开始规划发布会倒计时",
        "并把每一个任务安排到准确的时间线上同时检查人员物料场地和最终确认清单确保发布当天万无一失",
    ]
    assert result["units"][0]["visualFocus"] == "日历和倒计时标记"
    assert "并把每一个任务安排到准确的时间线上" in "".join(unit["text"] for unit in result["units"])
    assert llm.calls
