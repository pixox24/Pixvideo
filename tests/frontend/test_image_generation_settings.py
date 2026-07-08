from pathlib import Path


def test_system_settings_exposes_image_generation_connection_fields():
    component = Path("frontend/src/components/SystemSettingsTab.tsx").read_text()

    assert "图片生成模型设置" in component
    assert "settings.imageGeneration.baseUrl" in component
    assert "settings.imageGeneration.apiKey" in component
    assert "settings.imageGeneration.model" in component
    assert 'testConnection("image_generation", settings.imageGeneration)' in component


def test_frontend_config_payload_maps_image_generation_settings():
    api = Path("frontend/src/lib/api.ts").read_text()
    types = Path("frontend/src/types.ts").read_text()

    assert "imageGeneration" in types
    assert "image_generation" in api
    assert "api_key: settings.imageGeneration.apiKey || undefined" in api
    assert "base_url: settings.imageGeneration.baseUrl || undefined" in api
    assert "model: settings.imageGeneration.model || undefined" in api


def test_quick_create_sends_custom_image_dimensions():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text()
    api = Path("frontend/src/lib/api.ts").read_text()

    assert "imageAspectRatio" in component
    assert "imageWidth" in component
    assert "imageHeight" in component
    assert "mediaWidth: imageWidth" in component
    assert "mediaHeight: imageHeight" in component
    assert "media_width: input.mediaWidth || undefined" in api
    assert "media_height: input.mediaHeight || undefined" in api
