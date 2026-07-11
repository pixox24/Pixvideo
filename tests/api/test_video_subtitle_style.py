from api.routers.video import _build_video_params
from api.schemas.video import VideoGenerateRequest


def test_video_request_passes_subtitle_style_to_pipeline(monkeypatch):
    monkeypatch.setattr("api.routers.video._resolve_media_size", lambda _request: (1080, 1920))

    request = VideoGenerateRequest(
        text="第一句旁白。第二句旁白。",
        mode="fixed",
        subtitle_enabled=True,
        subtitle_style={
            "mode": "ass",
            "preset": "short-video-bold",
            "fontFamily": "PingFang SC",
            "fontPath": "/System/Library/Fonts/PingFang.ttc",
            "fontSize": 56,
            "primaryColor": "#FFFFFF",
            "outlineColor": "#000000",
            "outlineWidth": 4,
            "marginV": 140,
            "alignment": 2,
            "maxCharsPerLine": 12,
            "maxLines": 2,
            "animation": "fade",
            "segmentMode": "phrase",
        },
    )

    params = _build_video_params(request)

    assert params["subtitle_enabled"] is True
    assert params["subtitle_style"]["mode"] == "ass"
    assert params["subtitle_style"]["fontSize"] == 56
    assert params["subtitle_style"]["fontPath"] == "/System/Library/Fonts/PingFang.ttc"


def test_video_request_accepts_hyperframes_subtitle_mode(monkeypatch):
    monkeypatch.setattr("api.routers.video._resolve_media_size", lambda _request: (1080, 1920))

    request = VideoGenerateRequest(
        text="动态字幕测试",
        subtitle_style={"mode": "hyperframes", "animation": "pop"},
    )

    params = _build_video_params(request)

    assert params["subtitle_style"]["mode"] == "hyperframes"
    assert params["subtitle_style"]["animation"] == "pop"


def test_video_request_accepts_dynamic_highlight_settings(monkeypatch):
    monkeypatch.setattr("api.routers.video._resolve_media_size", lambda _request: (1080, 1920))

    request = VideoGenerateRequest(
        text="动态字幕测试",
        subtitle_style={
            "mode": "hyperframes",
            "animation": "word-pop",
            "highlightWords": ["表达力", "重点"],
            "highlightStyle": "badge",
            "highlightScale": 135,
            "backgroundOpacity": 45,
        },
    )

    params = _build_video_params(request)

    assert params["subtitle_style"]["animation"] == "word-pop"
    assert params["subtitle_style"]["highlightWords"] == ["表达力", "重点"]
    assert params["subtitle_style"]["highlightStyle"] == "badge"
    assert params["subtitle_style"]["highlightScale"] == 135
    assert params["subtitle_style"]["backgroundOpacity"] == 45
