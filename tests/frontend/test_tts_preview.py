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


def test_quick_create_can_synthesize_current_generated_copy():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text()

    assert "getCurrentCopyForTts" in component
    assert "handleSynthesizeCurrentCopy" in component
    assert "synthesizingCopy" in component
    assert "copyTtsAudioUrl" in component
    assert "copyTtsDuration" in component
    assert "合成当前文案" in component
    assert "当前文案音频" in component
    assert "清除音频" in component
    assert "scenes.map((scene) => scene.ttsText)" in component
    assert "copyDraft.trim()" in component


def test_generated_copy_draft_autofills_preview_script_first_sentence_without_overwriting_user_text():
    component = Path("frontend/src/components/QuickCreate.tsx").read_text()

    assert "extractPreviewSentenceFromCopyDraft" in component
    assert "maybeSyncCopyDraftToPreviewTts" in component
    assert "previewTtsTextUserEditedRef" in component
    assert "draftText.split(/[。\\.]/)" in component
    assert "maybeSyncCopyDraftToPreviewTts(draftText)" in component
    assert "previewTtsTextUserEditedRef.current = true" in component


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
