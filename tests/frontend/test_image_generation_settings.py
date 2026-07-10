from pathlib import Path


def test_system_settings_exposes_image_generation_connection_fields():
    component = Path("frontend/src/components/SystemSettingsTab.tsx").read_text(encoding="utf-8")

    assert "图片生成模型设置" in component
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
    assert "width: imageWidth" in component
    assert "height: imageHeight" in component
    assert "media_width: input.mediaWidth || undefined" in api
    assert "media_height: input.mediaHeight || undefined" in api


def test_quick_create_test_prompt_labels_image_motion_size_source():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "使用图片运动生成比例" in component
    assert "{imageWidth}x{imageHeight}" in component


def test_quick_create_explains_output_ratio_source_by_render_mode():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "图片/视频画布比例" in component
    assert "此尺寸会同时用于生成图片素材和最终视频画布" in component
    assert "模板模式下最终视频比例由模板决定" in component
    assert "当前模板画布" in component


def test_quick_create_defaults_to_image_motion_before_template_rendering():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert 'useState<"template" | "pure-image">("pure-image")' in component
    assert component.index('setViewMode("pure-image")') < component.index('setViewMode("template")')


def test_quick_create_workflow_panel_is_collapsed_by_default():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")

    assert "ChevronDown" in component
    assert "ChevronUp" in component
    assert "const [workflowsCollapsed, setWorkflowsCollapsed] = useState(true);" in component
    assert "setWorkflowsCollapsed((current) => !current)" in component
    assert "!workflowsCollapsed &&" in component
