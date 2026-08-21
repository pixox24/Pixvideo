from pathlib import Path


def test_quick_create_exposes_five_stage_navigation_and_section_anchors():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    wizard = Path("frontend/src/components/quickCreate/wizard.ts").read_text(encoding="utf-8")

    for stage in ["内容", "风格", "声音", "确认"]:
        assert stage in wizard
    for anchor in ["stage-content", "stage-storyboard", "stage-style", "stage-voice", "stage-review"]:
        assert f'id="{anchor}"' in quick_create
    assert "stage-production" not in quick_create
    assert "AdvancedFold" in quick_create
    assert "高级设定" in quick_create


def test_quick_create_autosaves_and_recovers_a_versioned_draft():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert 'QUICK_CREATE_DRAFT_KEY = "pixvideo.quick-create.draft.v1"' in quick_create
    assert "localStorage.getItem(QUICK_CREATE_DRAFT_KEY)" in quick_create
    assert "localStorage.setItem(QUICK_CREATE_DRAFT_KEY" in quick_create
    assert "已恢复本地草稿" in quick_create

    for field in [
        "copyDraftMode",
        "splitType",
        "minimaxModel",
        "emotion",
        "promptPrefix",
        "enableMotion",
        "enableSubtitles",
        "imageAspectRatio",
    ]:
        assert f"draft.{field}" in quick_create
        assert f"{field}," in quick_create


def test_draft_scene_recovery_validates_shape_before_updating_state():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    recovery = quick_create.split("localStorage.getItem(QUICK_CREATE_DRAFT_KEY)", 1)[1].split(
        "React.useEffect(() => {", 1
    )[0]
    assert "draft.scenes.every" in recovery
    assert '}).id === "number"' in recovery
    assert '}).ttsText === "string"' in recovery
    assert '}).visualPrompt === "string"' in recovery


def test_recovered_batch_draft_recomputes_the_visible_topic_count():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    recovery = quick_create.split("localStorage.getItem(QUICK_CREATE_DRAFT_KEY)", 1)[1].split(
        "React.useEffect(() => {", 1
    )[0]
    assert "setBatchCount(" in recovery
    assert 'draft.batchInput.split("\\n")' in recovery


def test_editing_reviewed_configuration_requires_fresh_confirmation():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "const reviewReadyRef = React.useRef(false);" in quick_create
    assert "if (!reviewReadyRef.current)" in quick_create
    assert "setReviewConfirmed(false);" in quick_create
    assert "// Invalidate the review whenever a submitted production setting changes." in quick_create


def test_recovered_draft_takes_precedence_over_automatic_initial_preset():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    preset_effect = quick_create.split("// Apply Preset", 1)[1].split(
        "const maybeSyncCopyDraftToPreviewTts", 1
    )[0]
    assert "draftRecoveredRef.current" in preset_effect
    assert "lastAppliedPresetId.current === null" in preset_effect


def test_expensive_preview_assets_are_clearly_marked_preview_only():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert quick_create.count("仅供预览，不会复用到最终成片") >= 2


def test_full_copy_render_respects_the_selected_split_rule_before_rebalancing():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    function_body = quick_create.split("const buildScenesForRender", 1)[1].split("const validateBeforeSubmit", 1)[0]
    assert 'copyDraftMode === "segmented" ? "line" : splitType' in function_body
    assert "buildStoryboardNarrations(draftText, rule, targetCount" in function_body
