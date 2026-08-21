"""React workbench HTTP facade.

Route implementations live in focused modules; this file re-exports names that
tests and the FastAPI app already import.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.routers.configuration import test_service
from api.routers.workbench_presets import (
    delete_preset,
    list_presets,
    save_preset,
    save_prompt_prefix,
    set_default_preset,
    update_preset,
)
from api.routers.workbench_presets import router as presets_router
from api.routers.workbench_script import (
    analyze_storyboard,
    generate_copy_draft,
    generate_script,
)
from api.routers.workbench_script import router as script_router
from api.routers.workbench_support import (  # noqa: F401
    GenerateCopyDraftRequest,
    GenerateScriptRequest,
    PromptPrefixSaveRequest,
    StoryboardAnalyzeRequest,
    TestConnectionRequest,
    _format_segmented_draft,
    _normalize_preset,
    _preset_from_config,
    _quick_create_config_from_preset,
    _service_test_request,
    config_manager,
)

router = APIRouter(tags=["React Workbench"])
router.include_router(presets_router)
router.include_router(script_router)


@router.post("/test-connection")
async def test_connection(request: TestConnectionRequest):
    """Compatibility route for the React settings panel."""
    return await test_service(_service_test_request(request))
