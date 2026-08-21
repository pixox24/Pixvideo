from pathlib import Path

RAIL = Path("frontend/src/components/quickCreate/CreateStageRail.tsx").read_text(encoding="utf-8")
QC = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
VIDEO = Path("frontend/src/components/VideoPreview.tsx").read_text(encoding="utf-8")


def test_stage_rail_is_sticky_preview_only():
    assert 'id="create-stage-rail"' in RAIL
    assert "sticky top-24" in RAIL
    assert "hidden xl:block" in RAIL
    assert "ui-stage" in RAIL
    assert "aspectRatio" in RAIL
    assert "生成口播后，分镜会出现在这里" in RAIL
    assert "setState" not in RAIL
    assert "fetch(" not in RAIL


def test_quick_create_mounts_stage_rail_in_xl_grid():
    assert "CreateStageRail" in QC
    assert "xl:grid-cols-[minmax(0,48rem)_20rem]" in QC
    assert "max-w-[1240px]" in QC
    assert "max-w-3xl" in QC


def test_video_preview_uses_ui_stage():
    assert "ui-stage" in VIDEO
    assert "border-zinc-800" not in VIDEO
