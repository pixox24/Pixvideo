from pixelle_video.utils.storyboard_split import (
    build_storyboard_narrations,
    heal_mid_cuts,
    pack_semantic_units,
    soft_expand_by_pause,
    split_draft_by_rule,
)
from pixelle_video.utils.content_generators import segment_narration_semantically
import pytest


def test_soft_expand_keeps_pause_on_left():
    expanded = soft_expand_by_pause(
        ["荣格说中年是第二次成年，前半生为别人活，后半生该找回真正的自己。"]
    )
    assert expanded == [
        "荣格说中年是第二次成年，",
        "前半生为别人活，",
        "后半生该找回真正的自己。",
    ]


def test_heal_mid_cuts_joins_hard_word_break():
    healed = heal_mid_cuts(
        [
            "抬头看天空，那会不会是渲染出来的背景？科学家发",
            "现，光速就像系统设定的上限",
        ]
    )
    assert len(healed) == 1
    assert "科学家发现" in healed[0]


def test_pack_never_character_slices_when_short():
    units = ["荣格说中年是第二次成年", "前半生为别人活", "后半生该找回真正的自己"]
    packed = pack_semantic_units(units, 6)
    assert packed == units
    assert "后半生该" not in packed


def test_build_storyboard_without_soft_expand_keeps_sentence():
    text = "荣格说中年是第二次成年，前半生为别人活，后半生该找回真正的自己。身边人都在交卷。"
    scenes = build_storyboard_narrations(text, "sentence", 6, soft_expand=False, heal=True)
    assert all("科学家发" not in s or "发现" in s for s in scenes)
    # Without soft expand, full sentences stay together
    assert any("后半生该找回真正的自己" in s for s in scenes)


def test_sentence_split_basic():
    text = "第一句。第二句！第三句？"
    assert split_draft_by_rule(text, "sentence") == ["第一句。", "第二句！", "第三句？"]


def test_auto_split_handles_unbroken_multi_sentence_copy():
    text = "星期一早上八点我走进办公室。打开电脑后邮件已经堆满屏幕。那一刻我意识到这一周又要重复开始。"
    scenes = split_draft_by_rule(text, "auto")
    assert len(scenes) == 3
    assert "星期一" in scenes[0]
    assert "邮件" in scenes[1]
    assert "重复开始" in scenes[2]
    assert "".join(scenes) == text


def test_auto_split_long_sentence_uses_pause_boundaries_without_char_cutting():
    text = "进入房间以后我先打开窗户让新鲜空气进来，然后把桌上的文件按照日期重新整理，最后坐下来开始处理今天最重要的工作。"
    scenes = split_draft_by_rule(text, "auto")
    assert len(scenes) >= 2
    assert "".join(scenes) == text
    assert all(len(scene.replace(" ", "")) >= 12 for scene in scenes)


def test_sentence_split_keeps_decimal_dates_and_versions_intact():
    text = "版本 3.14 于 2026.08.18 发布。随后团队开始复盘。"
    assert split_draft_by_rule(text, "sentence") == [
        "版本 3.14 于 2026.08.18 发布。",
        "随后团队开始复盘。",
    ]


@pytest.mark.asyncio
async def test_semantic_segmentation_requires_exact_source_reconstruction():
    source = "星期一早上八点我走进办公室，打开电脑后邮件已经堆满屏幕。"

    class FakeLLM:
        async def __call__(self, **_kwargs):
            return '{"segments":[{"text":"星期一早上八点我走进办公室，","boundary_reason":"time and place","visual_focus":"calendar and office"},{"text":"打开电脑后邮件已经堆满屏幕。","boundary_reason":"action change","visual_focus":"email screen"}]}'

    segments = await segment_narration_semantically(FakeLLM(), source, target_count=2)
    assert [item["text"] for item in segments] == [
        "星期一早上八点我走进办公室，",
        "打开电脑后邮件已经堆满屏幕。",
    ]


@pytest.mark.asyncio
async def test_semantic_segmentation_rejects_rewritten_source():
    class FakeLLM:
        async def __call__(self, **_kwargs):
            return '{"segments":[{"text":"改写后的旁白。","boundary_reason":"rewrite","visual_focus":"room"}]}'

    with pytest.raises(ValueError, match="changed|omitted|duplicated"):
        await segment_narration_semantically(FakeLLM(), "原始旁白。", target_count=2)
