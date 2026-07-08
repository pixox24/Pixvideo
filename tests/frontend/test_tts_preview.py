from pathlib import Path


def test_quick_create_has_tts_preview_text_input_and_calls_tts_api():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text()

    assert "previewTtsText" in component
    assert "试听文案" in component
    assert 'fetch("/api/tts/synthesize"' in component
    assert 'const previewInferenceMode = ttsMode === "edge" ? "local" : ttsMode' in component
    assert "inference_mode: previewInferenceMode" in component
    assert 'minimax_model: ttsMode === "minimax" ? minimaxModel : undefined' in component
    assert 'minimax_emotion: ttsMode === "minimax" ? emotion || undefined : undefined' in component


def test_quick_create_uses_real_minimax_defaults_and_models():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text()

    assert 'useState("male-qn-qingse")' in component
    assert 'useState("speech-2.8-turbo")' in component
    assert 'value="speech-2.8-turbo"' in component
    assert 'value="speech-2.8-hd"' in component
    assert "speech-mimic-v1" not in component
    assert "minimax-emotion-db1" not in component


def test_digital_human_uses_real_minimax_voice_and_model():
    component = Path("frontend/src/components/DigitalHuman.tsx").read_text()

    assert 'useState("male-qn-qingse")' in component
    assert 'minimaxModel: "speech-2.8-turbo"' in component
    assert "VOICE_OPTIONS.minimax.map" in component
    assert "minimax-emotion-db1" not in component
