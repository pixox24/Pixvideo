from pathlib import Path

REMOVED_MODULES = (
    "custom-media",
    "digital-human",
    "action-transfer",
)


def test_navigation_and_submission_are_focused_on_quick_create():
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")

    for module in REMOVED_MODULES:
        assert f'setActiveTab("{module}")' not in app
        assert f'taskInput.tabType === "{module}"' not in app
    assert "const response = await submitVideoTask(taskInput);" in app


def test_removed_specialist_pages_and_frontend_clients_are_absent():
    component_dir = Path("frontend/src/components")
    for filename in (
        "CustomMedia.tsx",
        "DigitalHuman.tsx",
        "ActionTransfer.tsx",
    ):
        assert not (component_dir / filename).exists()

    assert (component_dir / "ImageToVideo.tsx").exists()
    i2v = (component_dir / "ImageToVideo.tsx").read_text(encoding="utf-8")
    quick = (component_dir / "QuickCreate.tsx").read_text(encoding="utf-8")
    app = Path("frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "onOpenImageToVideo" in quick
    assert "onBackToCreate" in i2v
    assert "返回口播创作" in i2v
    assert "createView" not in quick
    assert "createView" not in app
    assert 'useState<"ai" | "manual" | "batch">' in quick
    assert "图生视频" in quick
    assert "setActiveTab(\"image-to-video\")" in app
    assert "hidden" in app.split('setActiveTab("image-to-video")', 2)[1][:400] or 'className={`${navBtn("image-to-video"' in app

    api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")
    assert "/api/specialist/image-to-video/generate/async" in api
    assert "uploadSpecialistFiles" not in api
    assert "/api/specialist/action-transfer" not in api
    assert "/api/specialist/digital-human" not in api
    assert "/api/specialist/custom-media" not in api


def test_active_navigation_is_narrow_but_legacy_history_sources_remain_supported():
    types = Path("frontend/src/types.ts").read_text(encoding="utf-8")
    history = Path("frontend/src/components/HistoryList.tsx").read_text(encoding="utf-8")

    active_tab = types.split("export type ActiveTab", 1)[1].split("export type TaskSource", 1)[0]
    for module in REMOVED_MODULES:
        assert module not in active_tab
        assert module in types
        assert module in history
    assert "image-to-video" in active_tab


def test_quick_create_resource_loading_does_not_fetch_templates():
    api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")

    loader = api.split("export async function fetchQuickCreateResources", 1)[1].split(
        "export function buildConfigPayload", 1
    )[0]
    assert "/api/resources/templates" not in loader


def test_single_video_submission_reuses_assets_from_the_previous_task():
    quick_create = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")

    assert "reuseSourceTaskId" in quick_create
    assert "reuseSourceTaskId || latestCompletedTaskId" in quick_create
    assert "reuseTaskId: mode === \"batch\" ? undefined : effectiveReuseSourceTaskId" in quick_create
    assert "setReuseSourceTaskId(submittedTaskId)" in quick_create
    assert "reuse_assets_from_task_id: input.reuseTaskId || undefined" in api
    assert "latestCompletedQuickCreateTask" in Path("frontend/src/App.tsx").read_text(encoding="utf-8")
