import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, GripVertical, Maximize2, Minus, Plus, Redo2, Undo2, ZoomIn, ZoomOut } from "lucide-react";
import { GenerationRun, WorkbenchScene } from "../types";
import {
  buildEqualWidthTimelineLayout,
  buildTimelineLayout,
  clampTimelineTime,
  findSceneAtTime,
  formatTimelineTime,
  getTimelineDuration,
  mapRealTimeToViewTime,
  mapViewTimeToRealTime,
  TimelineLayoutItem,
} from "../lib/workbenchState";
import {
  isRunActive,
  resolveSceneVisualStatus,
  SCENE_STATUS_LABEL,
  SceneVisualStatus,
  summarizeSceneStatuses,
} from "../lib/sceneStatus";

const MIN_PPS = 8;
const MAX_PPS = 120;
const RULER_H = 28;
const STATUS_LANE_H = 5;
const TRACK_H = 72;
const PAD = 16;
const RESIZE_HIT = 10;
/** Virtual seconds per clip in equal-width monitoring mode. */
const EQUAL_UNIT = 1;
/** Default batch hold step (seconds). */
const HOLD_DELTA_STEP = 0.5;

type LayoutMode = "duration" | "equal";

interface Props {
  scenes: WorkbenchScene[];
  selectedSceneId: string | null;
  /** Multi-select from scene list; when non-empty, batch hold applies only to these. */
  selectedSceneIds?: Set<string>;
  currentTime: number;
  totalDuration: number;
  isPlaying: boolean;
  pixelsPerSecond: number;
  canUndo: boolean;
  canRedo: boolean;
  /** Active or latest generation run — drives per-clip progress status. */
  generationRun?: GenerationRun | null;
  onZoomChange: (pps: number) => void;
  onSelect: (id: string) => void;
  onSeek: (time: number) => void;
  onPause: () => void;
  onReorder: (ids: string[]) => void;
  onHold: (sceneId: string, hold: number) => void;
  /** Relative hold change for all scenes, or only multi-selected when any are checked. */
  onHoldDelta?: (delta: number) => void;
  onUndo: () => void;
  onRedo: () => void;
}

const clampPps = (value: number) => Math.min(MAX_PPS, Math.max(MIN_PPS, value));

const roundHold = (value: number) => Math.round(Math.max(0, value) * 10) / 10;

function sceneThumb(scene: WorkbenchScene | undefined): string | null {
  if (!scene) return null;
  const current = scene.versions.find((v) => v.versionId === scene.currentVersionId);
  return current?.thumbnailUrl || current?.imageUrl || scene.versions[0]?.thumbnailUrl || scene.versions[0]?.imageUrl || null;
}

export const WorkbenchTimeline: React.FC<Props> = ({
  scenes,
  selectedSceneId,
  selectedSceneIds,
  currentTime,
  totalDuration,
  isPlaying,
  pixelsPerSecond,
  canUndo,
  canRedo,
  generationRun = null,
  onZoomChange,
  onSelect,
  onSeek,
  onPause,
  onReorder,
  onHold,
  onHoldDelta,
  onUndo,
  onRedo,
}) => {
  const [holds, setHolds] = useState<Record<string, number>>({});
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [hoverSceneId, setHoverSceneId] = useState<string | null>(null);
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [resizingSceneId, setResizingSceneId] = useState<string | null>(null);
  const [failureCursor, setFailureCursor] = useState(0);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("duration");
  const [layoutModePinned, setLayoutModePinned] = useState(false);
  /** User manually zoomed — skip auto-fit until fit-all / mode switch / scene count change clears pin. */
  const [zoomPinned, setZoomPinned] = useState(false);

  const timers = useRef<Record<string, number>>({});
  const draggedIndex = useRef<number | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const scrubbingRef = useRef(false);
  const resizeStateRef = useRef<{ sceneId: string; startX: number; startHold: number } | null>(null);
  const ppsRef = useRef(pixelsPerSecond);
  ppsRef.current = pixelsPerSecond;
  const lastFollowedRunSceneRef = useRef<string | null>(null);
  const layoutModeRef = useRef(layoutMode);
  layoutModeRef.current = layoutMode;
  const zoomPinnedRef = useRef(false);
  zoomPinnedRef.current = zoomPinned;

  const realLayout = useMemo(() => buildTimelineLayout(scenes, holds), [scenes, holds]);
  const equalLayout = useMemo(
    () => buildEqualWidthTimelineLayout(scenes, holds, EQUAL_UNIT),
    [scenes, holds],
  );
  const viewLayout = layoutMode === "equal" ? equalLayout : realLayout;
  const viewDuration = useMemo(() => getTimelineDuration(viewLayout), [viewLayout]);

  const statusByScene = useMemo(() => {
    const map = new Map<string, SceneVisualStatus>();
    for (const scene of scenes) {
      map.set(scene.sceneId, resolveSceneVisualStatus(scene, generationRun));
    }
    return map;
  }, [scenes, generationRun]);
  const statusSummary = useMemo(
    () => summarizeSceneStatuses(scenes, generationRun),
    [scenes, generationRun],
  );
  const runActive = isRunActive(generationRun);
  const showStatusLane = runActive || statusSummary.failed > 0 || statusSummary.running > 0;

  useEffect(() => {
    setHolds(Object.fromEntries(scenes.map((scene) => [scene.sceneId, scene.manualHoldSeconds])));
  }, [scenes]);

  // Auto layout: many scenes + active run → equal-width scan; otherwise duration (unless user pinned).
  useEffect(() => {
    if (layoutModePinned) return;
    const next: LayoutMode | null =
      runActive && scenes.length >= 12 ? "equal" : !runActive ? "duration" : null;
    if (!next || next === layoutMode) return;
    // Mode auto-switch: clear zoom pin so the new span can fill the rail.
    zoomPinnedRef.current = false;
    setZoomPinned(false);
    setLayoutMode(next);
  }, [runActive, scenes.length, layoutModePinned, layoutMode]);

  useEffect(
    () => () => Object.values(timers.current).forEach((timer) => window.clearTimeout(timer as number)),
    [],
  );

  const pps = pixelsPerSecond;
  const contentWidth = Math.max(320, Math.max(0, viewDuration) * pps + PAD * 2);
  const viewPlayheadTime = useMemo(
    () => mapRealTimeToViewTime(realLayout, viewLayout, currentTime),
    [realLayout, viewLayout, currentTime],
  );
  const playheadX = PAD + viewPlayheadTime * pps;
  const trackTop = RULER_H + (showStatusLane ? STATUS_LANE_H + 2 : 0);
  const contentHeight = trackTop + TRACK_H + 8;
  const activeSceneId = isPlaying
    ? findSceneAtTime(realLayout, currentTime)?.sceneId
    : selectedSceneId;
  const generatingSceneId = statusSummary.runningSceneId || generationRun?.currentSceneId || null;
  const selectedRealItem = realLayout.find((item) => item.sceneId === (selectedSceneId || activeSceneId)) || null;
  const selectedItem = selectedRealItem;
  const selectedScene = selectedItem ? scenes[selectedItem.index] : null;
  const selectedStatus = selectedScene
    ? statusByScene.get(selectedScene.sceneId) || "missing"
    : null;

  const scrollSceneIntoView = useCallback(
    (sceneId: string) => {
      const item = viewLayout.find((entry) => entry.sceneId === sceneId);
      const scroller = scrollRef.current;
      if (!item || !scroller) return;
      const left = PAD + item.startSeconds * ppsRef.current;
      const right = left + Math.max(8, item.durationSeconds * ppsRef.current);
      const viewLeft = scroller.scrollLeft;
      const viewRight = viewLeft + scroller.clientWidth;
      const margin = 48;
      if (left < viewLeft + margin) {
        scroller.scrollLeft = Math.max(0, left - margin);
      } else if (right > viewRight - margin) {
        scroller.scrollLeft = right - scroller.clientWidth + margin;
      }
    },
    [viewLayout],
  );

  // Follow the scene currently being generated (does not move playhead).
  useEffect(() => {
    if (!runActive || !generatingSceneId) return;
    if (lastFollowedRunSceneRef.current === generatingSceneId) return;
    lastFollowedRunSceneRef.current = generatingSceneId;
    scrollSceneIntoView(generatingSceneId);
  }, [runActive, generatingSceneId, scrollSceneIntoView]);

  const jumpToNextFailure = () => {
    const ids = statusSummary.failedSceneIds;
    if (ids.length === 0) return;
    const index = failureCursor % ids.length;
    const sceneId = ids[index]!;
    setFailureCursor(index + 1);
    onSelect(sceneId);
    scrollSceneIntoView(sceneId);
    const item = realLayout.find((entry) => entry.sceneId === sceneId);
    if (item) onSeek(item.startSeconds);
  };

  const setLayoutModeUser = (mode: LayoutMode) => {
    setLayoutModePinned(true);
    setLayoutMode(mode);
    // Mode switch: re-balance width even if user had pinned zoom for the previous mode.
    clearZoomPin();
    window.requestAnimationFrame(() => applyFit({ force: true }));
  };

  const timeFromClientX = useCallback(
    (clientX: number) => {
      const rect = contentRef.current?.getBoundingClientRect();
      if (!rect) return 0;
      const viewTime = clampTimelineTime((clientX - rect.left - PAD) / ppsRef.current, viewDuration);
      if (layoutModeRef.current === "equal") {
        return clampTimelineTime(
          mapViewTimeToRealTime(realLayout, equalLayout, viewTime),
          totalDuration,
        );
      }
      return clampTimelineTime(viewTime, totalDuration);
    },
    [viewDuration, totalDuration, realLayout, equalLayout],
  );

  const seekToClientX = useCallback(
    (clientX: number) => onSeek(timeFromClientX(clientX)),
    [onSeek, timeFromClientX],
  );

  // Keep playhead in view while playing — rAF-friendly scroll, no layout thrash
  useEffect(() => {
    if (!isPlaying || isScrubbing) return;
    const scroller = scrollRef.current;
    if (!scroller) return;
    const margin = 64;
    const left = scroller.scrollLeft;
    const right = left + scroller.clientWidth;
    if (playheadX < left + margin) {
      scroller.scrollLeft = Math.max(0, playheadX - margin);
    } else if (playheadX > right - margin) {
      scroller.scrollLeft = playheadX - scroller.clientWidth + margin;
    }
  }, [currentTime, isPlaying, isScrubbing, playheadX]);

  const changeHold = (sceneId: string, value: number) => {
    const next = roundHold(value);
    setHolds((current) => ({ ...current, [sceneId]: next }));
    const previous = timers.current[sceneId];
    if (previous) window.clearTimeout(previous);
    timers.current[sceneId] = window.setTimeout(() => onHold(sceneId, next), 280);
  };

  const dropAt = (index: number) => {
    const from = draggedIndex.current;
    draggedIndex.current = null;
    setDragOverIndex(null);
    if (from === null || from === index) return;
    if (isPlaying) onPause();
    const ids = scenes.map((scene) => scene.sceneId);
    const [moved] = ids.splice(from, 1);
    ids.splice(index, 0, moved);
    onReorder(ids);
  };

  /**
   * Fit timeline content to the scroll viewport width.
   * Uses parent totalDuration / equal unit count — not local hold-drag layout —
   * so resizing a clip edge does not thrash zoom.
   */
  const applyFit = useCallback(
    (opts?: { force?: boolean }) => {
      if (zoomPinnedRef.current && !opts?.force) return;
      const scroller = scrollRef.current;
      if (!scroller) return;
      const span =
        layoutModeRef.current === "equal"
          ? Math.max(EQUAL_UNIT, scenes.length * EQUAL_UNIT)
          : Math.max(0, totalDuration);
      if (span <= 0) return;
      const available = Math.max(80, scroller.clientWidth - PAD * 2 - 8);
      if (available < 40) return;
      const next = clampPps(available / span);
      if (Math.abs(next - ppsRef.current) < 0.35) return;
      onZoomChange(next);
    },
    [scenes.length, totalDuration, onZoomChange],
  );

  const pinZoom = useCallback(() => {
    zoomPinnedRef.current = true;
    setZoomPinned(true);
  }, []);

  const clearZoomPin = useCallback(() => {
    zoomPinnedRef.current = false;
    setZoomPinned(false);
  }, []);

  /** Explicit "适应全部": clear pin and force fit. */
  const fitAll = useCallback(() => {
    clearZoomPin();
    // Next frame so layoutMode/size is settled after pin clear.
    window.requestAnimationFrame(() => applyFit({ force: true }));
  }, [applyFit, clearZoomPin]);

  const userZoomChange = useCallback(
    (value: number) => {
      pinZoom();
      onZoomChange(clampPps(value));
    },
    [onZoomChange, pinZoom],
  );

  // Auto-fit: open / mode change / scene count / real duration bucket / container resize.
  // Skipped while zoom is user-pinned (unless force via fitAll).
  useEffect(() => {
    applyFit();
  }, [layoutMode, scenes.length, totalDuration, applyFit]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    let frame = 0;
    const ro = new ResizeObserver(() => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => applyFit());
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [applyFit]);

  const handleTrackPointerDown = (event: React.PointerEvent) => {
    // Only scrub when clicking empty track / ruler — clips stop propagation
    if (isPlaying) onPause();
    scrubbingRef.current = true;
    setIsScrubbing(true);
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    seekToClientX(event.clientX);
  };

  const handleTrackPointerMove = (event: React.PointerEvent) => {
    if (!scrubbingRef.current) return;
    seekToClientX(event.clientX);
  };

  const handleTrackPointerUp = (event: React.PointerEvent) => {
    if (!scrubbingRef.current) return;
    scrubbingRef.current = false;
    setIsScrubbing(false);
    try {
      (event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId);
    } catch {
      /* ignore */
    }
  };

  const handleClipPointerDown = (event: React.PointerEvent, item: TimelineLayoutItem) => {
    event.stopPropagation();
    onSelect(item.sceneId);
    if (isPlaying) onPause();
    const rect = contentRef.current?.getBoundingClientRect();
    const realItem = realLayout[item.index];
    if (!rect || !realItem) {
      if (realItem) onSeek(realItem.startSeconds);
      return;
    }
    const viewTime = clampTimelineTime((event.clientX - rect.left - PAD) / pps, viewDuration);
    const realTime = layoutMode === "equal"
      ? mapViewTimeToRealTime(realLayout, viewLayout, viewTime)
      : viewTime;
    onSeek(clampTimelineTime(realTime, totalDuration));
  };

  const handleResizePointerDown = (event: React.PointerEvent, item: TimelineLayoutItem) => {
    // Equal-width mode is for scan/status — hold resize only in duration mode.
    if (layoutMode === "equal") return;
    event.stopPropagation();
    event.preventDefault();
    if (isPlaying) onPause();
    onSelect(item.sceneId);
    const realItem = realLayout[item.index] || item;
    resizeStateRef.current = { sceneId: item.sceneId, startX: event.clientX, startHold: realItem.holdSeconds };
    setResizingSceneId(item.sceneId);
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  };

  const handleResizePointerMove = (event: React.PointerEvent) => {
    const state = resizeStateRef.current;
    if (!state || layoutMode === "equal") return;
    const nextHold = roundHold(state.startHold + (event.clientX - state.startX) / pps);
    setHolds((current) => ({ ...current, [state.sceneId]: nextHold }));
  };

  const handleResizePointerUp = (event: React.PointerEvent) => {
    const state = resizeStateRef.current;
    resizeStateRef.current = null;
    setResizingSceneId(null);
    try {
      (event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId);
    } catch {
      /* ignore */
    }
    if (!state) return;
    const nextHold = roundHold(state.startHold + (event.clientX - state.startX) / pps);
    if (nextHold !== state.startHold) changeHold(state.sceneId, nextHold);
    else setHolds((current) => ({ ...current, [state.sceneId]: state.startHold }));
  };

  const handleResizePointerCancel = (event: React.PointerEvent) => {
    const state = resizeStateRef.current;
    resizeStateRef.current = null;
    setResizingSceneId(null);
    try {
      (event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId);
    } catch {
      /* ignore */
    }
    if (state) setHolds((current) => ({ ...current, [state.sceneId]: state.startHold }));
  };

  // Sparse labeled ticks on the *view* axis (real seconds or equal units).
  const ticks = useMemo(() => {
    if (viewDuration <= 0) return [] as Array<{ time: number; x: number; label: string }>;
    if (layoutMode === "equal") {
      // Label every N clips so the ruler stays calm.
      const every = scenes.length > 40 ? 5 : scenes.length > 20 ? 2 : 1;
      const list: Array<{ time: number; x: number; label: string }> = [];
      for (let index = 0; index <= scenes.length; index += every) {
        const time = Math.min(viewDuration, index * EQUAL_UNIT);
        list.push({
          time,
          x: PAD + time * pps,
          label: index >= scenes.length ? `${scenes.length}` : `#${index + 1}`,
        });
      }
      return list;
    }
    const candidates = [1, 2, 5, 10, 15, 30, 60];
    const targetPx = 100;
    let step = candidates[candidates.length - 1]!;
    for (const candidate of candidates) {
      if (candidate * pps >= targetPx * 0.75) {
        step = candidate;
        break;
      }
    }
    if (pps >= 90) step = 0.5;
    else if (pps >= 55 && step > 1) step = 1;

    const list: Array<{ time: number; x: number; label: string }> = [];
    const count = Math.ceil(viewDuration / step + 1e-9);
    for (let index = 0; index <= count; index += 1) {
      const time = Math.min(viewDuration, index * step);
      list.push({
        time,
        x: PAD + time * pps,
        label: time < 60
          ? `${time % 1 === 0 ? time.toFixed(0) : time.toFixed(1)}s`
          : formatTimelineTime(time).slice(0, 5),
      });
      if (time >= viewDuration - 1e-9) break;
    }
    return list;
  }, [pps, viewDuration, layoutMode, scenes.length]);

  const zoomPct = Math.round(((pps - MIN_PPS) / (MAX_PPS - MIN_PPS)) * 100);
  const multiSelectedCount = selectedSceneIds?.size ?? 0;
  const holdBatchUsesSelection = multiSelectedCount > 0;
  const holdBatchCount = holdBatchUsesSelection ? multiSelectedCount : scenes.length;
  const holdBatchLabel = holdBatchUsesSelection ? `选中 ${holdBatchCount}` : "全部";

  const applyHoldDelta = (delta: number) => {
    if (!onHoldDelta || scenes.length === 0) return;
    // Optimistic local holds so the rail updates before server round-trip.
    const targets = holdBatchUsesSelection && selectedSceneIds
      ? scenes.filter((scene) => selectedSceneIds.has(scene.sceneId)).map((scene) => scene.sceneId)
      : scenes.map((scene) => scene.sceneId);
    setHolds((current) => {
      const next = { ...current };
      for (const id of targets) {
        const base = next[id] ?? scenes.find((scene) => scene.sceneId === id)?.manualHoldSeconds ?? 0;
        next[id] = roundHold(base + delta);
      }
      return next;
    });
    onHoldDelta(delta);
  };

  return (
    <section className="tl-root" aria-label="时间线">
      {/* ── Toolbar: time primary, tools secondary ── */}
      <header className="tl-toolbar">
        <div className="tl-toolbar-left">
          <span className="tl-title">时间线</span>
          <div className="tl-clock" aria-live="polite">
            <span className="tl-clock-now font-mono">{formatTimelineTime(currentTime)}</span>
            <span className="tl-clock-sep">/</span>
            <span className="tl-clock-total font-mono">{formatTimelineTime(totalDuration)}</span>
          </div>
          <div className="tl-status-summary" aria-label="镜头状态摘要">
            <span className="tl-meta">{statusSummary.total} 分镜</span>
            {statusSummary.ready > 0 && (
              <span className="tl-pill tl-pill-ready">{statusSummary.ready} 就绪</span>
            )}
            {statusSummary.running > 0 && (
              <span className="tl-pill tl-pill-running">{statusSummary.running} 生成中</span>
            )}
            {statusSummary.queued > 0 && runActive && (
              <span className="tl-pill tl-pill-queued">{statusSummary.queued} 排队</span>
            )}
            {statusSummary.failed > 0 && (
              <span className="tl-pill tl-pill-failed">{statusSummary.failed} 失败</span>
            )}
            {statusSummary.candidate > 0 && (
              <span className="tl-pill tl-pill-candidate">{statusSummary.candidate} 待选</span>
            )}
            {statusSummary.failed === 0
              && statusSummary.running === 0
              && statusSummary.ready === statusSummary.total
              && statusSummary.total > 0 && (
              <span className="tl-pill tl-pill-ready">全部就绪</span>
            )}
            {selectedItem ? (
              <>
                <span className="tl-meta-dot" />
                <span className="tl-meta">#{selectedItem.index + 1}</span>
              </>
            ) : null}
          </div>
          {statusSummary.failed > 0 && (
            <button
              type="button"
              className="tl-fail-jump"
              onClick={jumpToNextFailure}
              title="跳到下一失败镜头"
            >
              <AlertTriangle className="h-3 w-3" />
              下一失败
              {statusSummary.failed > 1 ? ` (${(failureCursor % statusSummary.failed) + 1}/${statusSummary.failed})` : ""}
            </button>
          )}
        </div>
        <div className="tl-toolbar-right">
          {onHoldDelta && scenes.length > 0 && (
            <div className="tl-hold-batch" role="group" aria-label="批量调整停留">
              <span className="tl-hold-batch-label" title={holdBatchUsesSelection ? "作用于分镜列表中勾选的镜头" : "作用于全部分镜"}>
                停留 · {holdBatchLabel}
              </span>
              <button
                type="button"
                className="tl-icon-btn"
                title={`为${holdBatchLabel}各 −${HOLD_DELTA_STEP}s 停留`}
                aria-label={`停留减少 ${HOLD_DELTA_STEP} 秒`}
                disabled={holdBatchCount === 0}
                onClick={() => applyHoldDelta(-HOLD_DELTA_STEP)}
              >
                <Minus className="h-3.5 w-3.5" />
              </button>
              <span className="tl-hold-batch-step font-mono">±{HOLD_DELTA_STEP}s</span>
              <button
                type="button"
                className="tl-icon-btn"
                title={`为${holdBatchLabel}各 +${HOLD_DELTA_STEP}s 停留`}
                aria-label={`停留增加 ${HOLD_DELTA_STEP} 秒`}
                disabled={holdBatchCount === 0}
                onClick={() => applyHoldDelta(HOLD_DELTA_STEP)}
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          <div className="tl-mode-toggle" role="group" aria-label="时间线排布">
            <button
              type="button"
              className={layoutMode === "duration" ? "is-active" : ""}
              onClick={() => setLayoutModeUser("duration")}
              title="按真实时长排布（精修/剪辑）"
            >
              按时长
            </button>
            <button
              type="button"
              className={layoutMode === "equal" ? "is-active" : ""}
              onClick={() => setLayoutModeUser("equal")}
              title="按镜头等宽排布（生成进度扫视）"
            >
              按镜头
            </button>
          </div>
          <div className="tl-tool-group" role="group" aria-label="历史">
            <button type="button" title="撤销 (Ctrl+Z)" aria-label="撤销" disabled={!canUndo} onClick={onUndo} className="tl-icon-btn">
              <Undo2 className="h-3.5 w-3.5" />
            </button>
            <button type="button" title="重做 (Ctrl+Y)" aria-label="重做" disabled={!canRedo} onClick={onRedo} className="tl-icon-btn">
              <Redo2 className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="tl-tool-group" role="group" aria-label="缩放">
            <button type="button" title="缩小" aria-label="缩小" onClick={() => userZoomChange(pps / 1.25)} className="tl-icon-btn">
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <input
              aria-label="缩放比例"
              type="range"
              min={MIN_PPS}
              max={MAX_PPS}
              step={1}
              value={pps}
              onChange={(event) => userZoomChange(Number(event.target.value))}
              className="tl-zoom-slider"
            />
            <button type="button" title="放大" aria-label="放大" onClick={() => userZoomChange(pps * 1.25)} className="tl-icon-btn">
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              title={zoomPinned ? "适应全部（将解除手动缩放）" : "适应全部"}
              aria-label="适应全部"
              onClick={fitAll}
              className={`tl-icon-btn${zoomPinned ? " is-emphasis" : ""}`}
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
            <span className="tl-zoom-label font-mono" title={zoomPinned ? "已手动缩放" : "自动铺满"}>
              {zoomPct}%{zoomPinned ? "·" : ""}
            </span>
          </div>
        </div>
      </header>

      {/* ── Scroll body ── */}
      <div ref={scrollRef} className="tl-scroll">
        <div
          ref={contentRef}
          className="tl-content"
          style={{ width: contentWidth, height: contentHeight }}
        >
          {/* Ruler */}
          <div
            className="tl-ruler"
            style={{ height: RULER_H }}
            onPointerDown={handleTrackPointerDown}
            onPointerMove={handleTrackPointerMove}
            onPointerUp={handleTrackPointerUp}
            onPointerCancel={handleTrackPointerUp}
          >
            {ticks.map((tick, index) => (
              <div key={index} className="tl-tick" style={{ left: tick.x }}>
                <div className="tl-tick-mark" />
                <div className="tl-tick-label font-mono">{tick.label}</div>
              </div>
            ))}
          </div>

          {/* Thin status lane — progress at a glance without a second grid */}
          {showStatusLane && (
            <div className="tl-status-lane" style={{ top: RULER_H, height: STATUS_LANE_H }} aria-hidden>
              {viewLayout.map((item) => {
                const left = PAD + item.startSeconds * pps;
                const width = Math.max(3, item.durationSeconds * pps);
                const status = statusByScene.get(item.sceneId) || "missing";
                return (
                  <div
                    key={`st-${item.sceneId}`}
                    className={`tl-status-seg is-${status}`}
                    style={{ left, width }}
                  />
                );
              })}
            </div>
          )}

          {/* Track lane */}
          <div className="tl-track-row" style={{ top: trackTop, height: TRACK_H }}>
            <div
              className="tl-track"
              onPointerDown={handleTrackPointerDown}
              onPointerMove={handleTrackPointerMove}
              onPointerUp={handleTrackPointerUp}
              onPointerCancel={handleTrackPointerUp}
            >
              {viewLayout.map((item, index) => {
                const left = PAD + item.startSeconds * pps;
                const width = Math.max(4, item.durationSeconds * pps);
                const realItem = realLayout[index] || item;
                const audioRatio =
                  realItem.durationSeconds > 0
                    ? Math.min(1, realItem.audioDurationSeconds / realItem.durationSeconds)
                    : 1;
                const isSelected = item.sceneId === selectedSceneId;
                const isActive = item.sceneId === activeSceneId;
                const isGenerating = item.sceneId === generatingSceneId;
                const isHover = item.sceneId === hoverSceneId || item.sceneId === resizingSceneId;
                const scene = scenes[item.index];
                const thumb = sceneThumb(scene);
                const status = statusByScene.get(item.sceneId) || "missing";
                const showDropBefore = dragOverIndex === index && draggedIndex.current !== null && draggedIndex.current !== index;
                const narrow = width < 40;

                return (
                  <React.Fragment key={item.sceneId}>
                    {showDropBefore && (
                      <div className="tl-drop-line" style={{ left: left - 2 }} aria-hidden />
                    )}
                    <div
                      draggable={!resizingSceneId}
                      onDragStart={(event) => {
                        draggedIndex.current = index;
                        event.dataTransfer.effectAllowed = "move";
                        event.dataTransfer.setData("text/plain", item.sceneId);
                      }}
                      onDragEnd={() => {
                        draggedIndex.current = null;
                        setDragOverIndex(null);
                      }}
                      onDragOver={(event) => {
                        event.preventDefault();
                        event.dataTransfer.dropEffect = "move";
                        setDragOverIndex(index);
                      }}
                      onDrop={(event) => {
                        event.preventDefault();
                        dropAt(index);
                      }}
                      onPointerDown={(event) => handleClipPointerDown(event, item)}
                      onMouseEnter={() => setHoverSceneId(item.sceneId)}
                      onMouseLeave={() => setHoverSceneId((id) => (id === item.sceneId ? null : id))}
                      className={[
                        "tl-clip",
                        `is-status-${status}`,
                        isSelected ? "is-selected" : "",
                        isActive ? "is-active" : "",
                        isGenerating ? "is-generating" : "",
                        isHover ? "is-hover" : "",
                        narrow ? "is-narrow" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      style={{ left, width }}
                      title={`#${item.index + 1} · ${SCENE_STATUS_LABEL[status]} · ${realItem.durationSeconds.toFixed(1)}s`}
                    >
                      {thumb && width >= 28 && (
                        <div
                          className="tl-clip-thumb"
                          style={{ backgroundImage: `url(${thumb})` }}
                          aria-hidden
                        />
                      )}
                      <div className="tl-clip-shade" aria-hidden />

                      <div className="tl-clip-layers" aria-hidden>
                        <div className="tl-clip-audio" style={{ width: `${audioRatio * 100}%` }} />
                        {realItem.holdSeconds > 0.05 && (
                          <div className="tl-clip-hold" style={{ width: `${(1 - audioRatio) * 100}%` }} />
                        )}
                      </div>

                      <div className="tl-clip-body">
                        {!narrow && (
                          <div className="tl-clip-grip" aria-hidden>
                            <GripVertical className="h-3 w-3" />
                          </div>
                        )}
                        <div className="tl-clip-info">
                          <span className="tl-clip-index">#{item.index + 1}</span>
                          {width >= 56 && (
                            <span className="tl-clip-dur font-mono">{realItem.durationSeconds.toFixed(1)}s</span>
                          )}
                        </div>
                        {width >= 88 && realItem.holdSeconds > 0.05 && (
                          <span className="tl-clip-hold-badge font-mono">+{realItem.holdSeconds.toFixed(1)}</span>
                        )}
                      </div>

                      {(status === "failed" || status === "running" || status === "candidate") && (
                        <div className="tl-clip-badge" aria-hidden>
                          {status === "failed" && <AlertTriangle className="h-2.5 w-2.5" />}
                          {status === "running" && <span className="tl-clip-pulse" />}
                          {status === "candidate" && <span className="tl-clip-dot-candidate" />}
                        </div>
                      )}

                      {layoutMode === "duration" && (
                        <div
                          className="tl-resize"
                          onPointerDown={(event) => handleResizePointerDown(event, item)}
                          onPointerMove={handleResizePointerMove}
                          onPointerUp={handleResizePointerUp}
                          onPointerCancel={handleResizePointerCancel}
                          title="拖动调整停留时长"
                          aria-label={`调整分镜 ${item.index + 1} 停留时长`}
                          style={{ width: RESIZE_HIT }}
                        >
                          <span className="tl-resize-bar" />
                        </div>
                      )}
                    </div>
                  </React.Fragment>
                );
              })}
              {dragOverIndex === viewLayout.length && viewLayout.length > 0 && (
                <div
                  className="tl-drop-line"
                  style={{ left: PAD + viewLayout[viewLayout.length - 1]!.endSeconds * pps - 2 }}
                  aria-hidden
                />
              )}
            </div>
          </div>

          {/* Playhead — refined needle: gem head + soft blade + foot glow */}
          <div
            className={`tl-playhead${isPlaying || isScrubbing ? " is-live" : ""}`}
            style={{ transform: `translate3d(${playheadX}px,0,0)` }}
            aria-hidden
          >
            <div className="tl-playhead-head">
              <span className="tl-playhead-gem" />
              <span className="tl-playhead-wing tl-playhead-wing-l" />
              <span className="tl-playhead-wing tl-playhead-wing-r" />
            </div>
            <div className="tl-playhead-blade">
              <span className="tl-playhead-core" />
              <span className="tl-playhead-glow" />
            </div>
            <div className="tl-playhead-foot" />
          </div>
          <div
            className="tl-playhead-hit"
            style={{ left: playheadX - 8, width: 16 }}
            onPointerDown={(event) => {
              event.stopPropagation();
              handleTrackPointerDown(event);
            }}
            onPointerMove={handleTrackPointerMove}
            onPointerUp={handleTrackPointerUp}
            onPointerCancel={handleTrackPointerUp}
            aria-label="播放头，拖动定位"
            role="slider"
            aria-valuemin={0}
            aria-valuemax={Math.max(0, totalDuration)}
            aria-valuenow={currentTime}
          />
        </div>
      </div>

      {/* ── Status strip: selection context without overlaying the track ── */}
      <footer className="tl-footer">
        {selectedItem && selectedScene ? (
          <div className="tl-footer-main">
            <span className="tl-footer-scene">分镜 #{selectedItem.index + 1}</span>
            {selectedStatus && (
              <>
                <span className="tl-footer-sep" />
                <span className={`tl-footer-status is-${selectedStatus}`}>
                  {SCENE_STATUS_LABEL[selectedStatus]}
                </span>
              </>
            )}
            <span className="tl-footer-sep" />
            <span className="font-mono text-[11px] text-zinc-400">
              总长 {selectedItem.durationSeconds.toFixed(1)}s
            </span>
            <span className="text-[11px] text-zinc-500">
              配音 {selectedItem.audioDurationSeconds.toFixed(1)}s
              {selectedItem.holdSeconds > 0
                ? ` · 停留 ${selectedItem.holdSeconds.toFixed(1)}s`
                : " · 无停留"}
            </span>
            {selectedScene.narration && (
              <>
                <span className="tl-footer-sep" />
                <span className="tl-footer-narration" title={selectedScene.narration}>
                  {selectedScene.narration}
                </span>
              </>
            )}
          </div>
        ) : (
          <div className="tl-footer-hint">
            {layoutMode === "equal"
              ? "按镜头等宽扫视 · 点击定位 · 可切回「按时长」精修"
              : runActive
                ? "生成进度在时间线 · 多镜自动「按镜头」等宽 · 失败点「下一失败」"
                : "点击片段选中 · 拖动排序 · 右缘拉伸停留 · 标尺/空白处 scrub"}
          </div>
        )}
        {resizingSceneId && selectedItem && (
          <div className="tl-footer-live font-mono">
            停留 → {selectedItem.holdSeconds.toFixed(1)}s
          </div>
        )}
      </footer>
    </section>
  );
};
