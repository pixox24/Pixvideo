"""PR-C: four-step create wizard UI shell."""

from pathlib import Path

WIZARD = Path("frontend/src/components/quickCreate/wizard.ts").read_text(encoding="utf-8")
STEPPER = Path("frontend/src/components/quickCreate/CreateStepper.tsx").read_text(encoding="utf-8")
FOOTER = Path("frontend/src/components/quickCreate/CreateStickyFooter.tsx").read_text(encoding="utf-8")
QC = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")


def test_wizard_has_four_semantic_steps():
    for step_id in ('"content"', '"style"', '"voice"', '"review"'):
        assert step_id in WIZARD
    assert "production" not in WIZARD or '"production"' not in WIZARD
    assert "WIZARD_STAGE_ID" in WIZARD


def test_advanced_fold_is_controlled_button_not_details():
    fold = Path("frontend/src/components/quickCreate/AdvancedFold.tsx").read_text(encoding="utf-8")
    assert "<details>" not in fold and "</details>" not in fold
    assert "aria-expanded" in fold
    assert "onToggle" in fold


def test_create_stepper_and_footer_exist():
    assert "CreateStepper" in STEPPER
    assert "CreateStickyFooter" in FOOTER
    assert "ui-btn-primary" in FOOTER
    assert "ui-sticky-footer" in FOOTER or "CreateStickyFooter" in FOOTER


def test_quick_create_wires_four_steps():
    assert "CreateStepper" in QC
    assert "CreateStickyFooter" in QC
    assert 'wizardStep === "style"' in QC
    assert 'wizardStep === "voice"' in QC
    assert 'id="stage-style"' in QC
    assert 'id="stage-voice"' in QC
    assert "stage-production" not in QC
    assert "AdvancedFold" in QC
    assert "高级设定" in QC
    assert "高级配音" in QC
    assert "抽词选项" in QC
    assert "ui-segment" in QC
    assert "order-1" in QC and "order-2" in QC
    assert "CreateStageRail" in QC
    assert "图生视频" in QC
    assert "onOpenImageToVideo" in QC
    assert 'useState<"ai" | "manual" | "batch">' in QC
    assert 'id="create-stage-rail"' in Path("frontend/src/components/quickCreate/CreateStageRail.tsx").read_text(encoding="utf-8")
    assert "xl:grid-cols-[minmax(0,48rem)_20rem]" in QC
    assert "生成口播后，分镜会出现在这里" in Path("frontend/src/components/quickCreate/CreateStageRail.tsx").read_text(encoding="utf-8")
