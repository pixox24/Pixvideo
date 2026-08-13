from pathlib import Path


def test_quick_create_has_api_image_toggle_default_off():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text(encoding="utf-8")
    types = Path("frontend/src/types.ts").read_text(encoding="utf-8")
    api = Path("frontend/src/lib/api.ts").read_text(encoding="utf-8")

    assert 'useState(false)' in component or "useState(false)" in component
    assert "useApiImage" in component
    assert "使用 API 图片生成" in component
    assert "素材库" in component
    assert "useApiImage?: boolean" in types
    assert "use_api_image: Boolean(input.useApiImage)" in api


def test_project_config_dual_writes_use_api_image():
    from pixelle_video.utils.project_config import normalize_project_config

    camel = normalize_project_config({"useApiImage": True})
    assert camel["useApiImage"] is True
    assert camel["use_api_image"] is True

    snake = normalize_project_config({"use_api_image": False})
    assert snake["useApiImage"] is False
    assert snake["use_api_image"] is False
