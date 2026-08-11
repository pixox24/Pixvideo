from pathlib import Path


def test_timeline_has_audio_driven_clips_and_reorder_controls():
    source = (Path(__file__).parents[2] / "frontend/src/components/WorkbenchTimeline.tsx").read_text(encoding="utf-8")
    assert "getSceneTimelineDuration" in source
    assert "onReorder" in source
    assert "manualHoldSeconds" in source
    assert "draggable" in source
    assert "window.setTimeout(() => onHold(sceneId, value), 350)" in source


def test_timeline_pure_functions_are_exported_from_state_lib():
    state = (Path(__file__).parents[2] / "frontend/src/lib/workbenchState.ts").read_text(encoding="utf-8")
    for marker in [
        "getSceneAudioDuration",
        "getSceneTimelineDuration",
        "buildTimelineLayout",
        "getTimelineDuration",
        "findSceneAtTime",
        "clampTimelineTime",
        "formatTimelineTime",
    ]:
        assert marker in state
    assert "effectiveSceneDuration" not in state


def test_workbench_drives_project_playback_clock():
    workbench = (Path(__file__).parents[2] / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
    assert "requestAnimationFrame" in workbench
    assert "findSceneAtTime" in workbench
    assert "currentTimeRef.current + delta" in workbench
    assert 'event.code === "Space"' in workbench
    assert "visibilitychange" in workbench
    assert 'aria-label={isPlaying ? "暂停播放" : "播放项目"}' in workbench
    assert "totalDurationRef.current || totalDuration" in workbench
    assert "currentSceneItemRef.current ?? currentSceneItem" in workbench
    assert "requestPlaybackFrame" in workbench
    assert "cancelPlaybackFrame" in workbench
    # Audio must follow the rAF ref clock — not a currentTime useEffect — to avoid
    # play()/pause() races (Chrome: "The play() request was interrupted...").
    assert "syncNarrationAudio" in workbench
    assert "isPlayInterruptedError" in workbench
    assert "UI_TICK_MS" in workbench


def test_timeline_receives_playback_props():
    source = (Path(__file__).parents[2] / "frontend/src/components/WorkbenchTimeline.tsx").read_text(encoding="utf-8")
    for marker in ["currentTime", "totalDuration", "isPlaying", "onSeek", "pixelsPerSecond", "onZoomChange", "onPause"]:
        assert marker in source
    assert "formatTimelineTime(currentTime)" in source


def test_timeline_renders_ruler_playhead_zoom_and_clicks():
    source = (Path(__file__).parents[2] / "frontend/src/components/WorkbenchTimeline.tsx").read_text(encoding="utf-8")
    for marker in [
        "setPointerCapture",
        "releasePointerCapture",
        "cursor-ew-resize",
        "overflow-x-auto",
        "aria-label=\"缩放比例\"",
        "aria-label=\"适应全部\"",
        "timeFromClientX",
        "clampTimelineTime",
    ]:
        assert marker in source
    assert "pointer-events-none" in source


def test_timeline_edge_resize_uses_pointer_events_and_single_save():
    source = (Path(__file__).parents[2] / "frontend/src/components/WorkbenchTimeline.tsx").read_text(encoding="utf-8")
    for marker in [
        "handleResizePointerDown",
        "handleResizePointerUp",
        "cursor-col-resize",
        "setPointerCapture",
        "changeHold(state.sceneId, nextHold)",
        "onPointerCancel",
    ]:
        assert marker in source


def test_timeline_exposes_undo_redo_controls():
    source = (Path(__file__).parents[2] / "frontend/src/components/WorkbenchTimeline.tsx").read_text(encoding="utf-8")
    for marker in ["canUndo", "canRedo", "onUndo", "onRedo", 'aria-label="撤销"', 'aria-label="重做"']:
        assert marker in source


def test_workbench_owns_zoom_state():
    workbench = (Path(__file__).parents[2] / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
    assert "pixelsPerSecond" in workbench
    assert "setPixelsPerSecond(Math.min(120, Math.max(8, value)))" in workbench


def test_workbench_tracks_undo_redo_history():
    workbench = (Path(__file__).parents[2] / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
    for marker in ["timelinePast", "timelinePresent", "timelineFuture", "handleUndo", "handleRedo", "pushTimelineHistory"]:
        assert marker in workbench


def test_workbench_serializes_timeline_saves_and_uses_latest_snapshot():
    workbench = (Path(__file__).parents[2] / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
    for marker in [
        "timelineSaveChainRef",
        "timelinePresentRef",
        "timelineSaveChainRef.current.then",
        "applyTimeline(result.present.sceneIds, result.present.holds",
    ]:
        assert marker in workbench


def test_workbench_reserves_a_real_preview_column_before_inspector():
    workbench = (Path(__file__).parents[2] / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
    # Three-column stage layout: scene rail | preview | inspector
    assert "lg:grid-cols-[minmax(200px,240px)_minmax(0,1fr)_minmax(260px,320px)]" in workbench
    assert "ui-stage" in workbench
    assert "SceneInspector" in workbench


def test_workbench_binds_project_bgm_to_a_separate_looping_audio():
    workbench = (Path(__file__).parents[2] / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
    for marker in ["selectedBgm", "bgmAudioRef", "settings.bgmVolume / 100", 'loop', "背景音乐加载失败，已继续播放旁白"]:
        assert marker in workbench


def test_workbench_does_not_return_before_declaring_playback_hooks():
    workbench = (Path(__file__).parents[2] / "frontend/src/components/ProjectWorkbench.tsx").read_text(encoding="utf-8")
    loading_return = '正在加载项目…'
    assert workbench.index("const seek = useCallback") < workbench.index(loading_return)
