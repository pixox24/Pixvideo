from pathlib import Path


def test_system_settings_exposes_image_generation_connection_fields():
    component = Path("frontend/src/components/SystemSettingsTab.tsx").read_text(encoding="utf-8")

    assert "图片生成模型" in component
    assert "settings.imageGeneration.baseUrl" in component
    assert "settings.imageGeneration.apiKey" in component
    assert "settings.imageGeneration.model" in component
    assert 'testConnection("image_generation", settings.imageGeneration)' in component


def test_frontend_config_payload_maps_image_generation_settings():
    api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")
    types = Path("frontend/src/types.ts").read_text(encoding="utf-8")

    assert "imageGeneration" in types
    assert "image_generation" in api
    assert "api_key: settings.imageGeneration.apiKey || undefined" in api
    assert "base_url: settings.imageGeneration.baseUrl || undefined" in api
    assert "model: settings.imageGeneration.model || undefined" in api


def test_quick_create_sends_custom_image_dimensions():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")

    assert "imageAspectRatio" in component
    assert "imageWidth" in component
    assert "imageHeight" in component
    assert "mediaWidth: imageWidth" in component
    assert "mediaHeight: imageHeight" in component
    assert "videoFps" in component
    # Test-image and production image gen use mapped whitelist size
    assert "width: imageGenSize[0]" in component
    assert "height: imageGenSize[1]" in component
    assert "media_width: input.mediaWidth || undefined" in api
    assert "media_height: input.mediaHeight || undefined" in api
    assert "video_fps: input.videoFps || undefined" in api


def test_quick_create_separates_video_canvas_from_image_gen_size():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "成片规格 / Video Canvas" in component
    assert "DEFAULT_VIDEO_WIDTH" in component
    assert "mapImageGenSize" in component
    assert "1080×1920@30" in component or "1080x1920" in component
    assert "高级/慢" in component or "isAdvancedCanvas" in component
    assert "分镜模板渲染" not in component
    assert 'setViewMode("template")' not in component


def test_quick_create_submission_is_fixed_to_plain_image_composition():
    api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")

    assert 'composition_mode: "plain_image"' in api
    assert "frame_template: input.templateId" not in api


def test_quick_create_workflow_panel_is_collapsed_by_default():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "ChevronDown" in component
    assert "ChevronUp" in component
    assert "const [workflowsCollapsed, setWorkflowsCollapsed] = useState(true);" in component
    assert "setWorkflowsCollapsed((current) => !current)" in component
    assert "!workflowsCollapsed &&" in component
