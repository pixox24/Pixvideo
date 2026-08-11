from pixelle_video.utils.storyboard_split import (
    build_storyboard_narrations,
    heal_mid_cuts,
    pack_semantic_units,
    soft_expand_by_pause,
    split_draft_by_rule,
)


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
