import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Maximize, Redo2, Undo2, ZoomIn, ZoomOut } from "lucide-react";
import { WorkbenchScene } from "../types";
import { buildTimelineLayout, clampTimelineTime, findSceneAtTime, formatTimelineTime, getSceneTimelineDuration, TimelineLayoutItem } from "../lib/workbenchState";

const MIN_PIXELS_PER_SECOND = 8;
const MAX_PIXELS_PER_SECOND = 120;
const RULER_HEIGHT = 22;
const TRACK_HEIGHT = 64;
const CONTENT_PADDING = 8;

interface Props {
  scenes: WorkbenchScene[];
  selectedSceneId: string | null;
  currentTime: number;
  totalDuration: number;
  isPlaying: boolean;
  pixelsPerSecond: number;
  canUndo: boolean;
  canRedo: boolean;
  onZoomChange: (pps: number) => void;
  onSelect: (id: string) => void;
  onSeek: (time: number) => void;
  onPause: () => void;
  onReorder: (ids: string[]) => void;
  onHold: (sceneId: string, hold: number) => void;
  onUndo: () => void;
  onRedo: () => void;
}

const clampPps = (value: number) => Math.min(MAX_PIXELS_PER_SECOND, Math.max(MIN_PIXELS_PER_SECOND, value));

export const WorkbenchTimeline: React.FC<Props> = ({
  scenes, selectedSceneId, currentTime, totalDuration, isPlaying,
  pixelsPerSecond, canUndo, canRedo, onZoomChange, onSelect, onSeek, onPause, onReorder, onHold, onUndo, onRedo,
}) => {
  const [holds, setHolds] = useState<Record<string, number>>({});
  const timers = useRef<Record<string, number>>({});
  const draggedIndex = useRef<number | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const scrubbingRef = useRef(false);
  const resizeStateRef = useRef<{ sceneId: string; startX: number; startHold: number } | null>(null);
  const layout = useMemo(() => buildTimelineLayout(scenes, holds), [scenes, holds]);
  useEffect(() => setHolds(Object.fromEntries(scenes.map((scene) => [scene.sceneId, scene.manualHoldSeconds]))), [scenes]);
  useEffect(() => () => Object.values(timers.current).forEach((timer) => window.clearTimeout(timer as number)), []);
  const pps = pixelsPerSecond;
  const contentWidth = Math.max(0, totalDuration) * pps + CONTENT_PADDING * 2;
  const playheadX = CONTENT_PADDING + currentTime * pps;
  const activeSceneId = isPlaying ? findSceneAtTime(layout, currentTime)?.sceneId : selectedSceneId;

  const timeFromClientX = (clientX: number) => {
    const rect = contentRef.current?.getBoundingClientRect();
    if (!rect) return 0;
    return clampTimelineTime((clientX - rect.left - CONTENT_PADDING) / pps, totalDuration);
  };
  const seekToClientX = (clientX: number) => onSeek(timeFromClientX(clientX));

  useEffect(() => {
    if (!isPlaying) return;
    const scroller = scrollRef.current;
    if (!scroller) return;
    const x = playheadX;
    if (x < scroller.scrollLeft + 40) scroller.scrollLeft = Math.max(0, x - 40);
    else if (x > scroller.scrollLeft + scroller.clientWidth - 40) scroller.scrollLeft = x - scroller.clientWidth + 40;
  }, [currentTime, isPlaying, pps, playheadX]);

  const changeHold = (sceneId: string, value: number) => {
    setHolds((current) => ({ ...current, [sceneId]: value }));
    const previous = timers.current[sceneId];
    if (previous) window.clearTimeout(previous);
    timers.current[sceneId] = window.setTimeout(() => onHold(sceneId, value), 350);
  };
  const dropAt = (index: number) => {
    const from = draggedIndex.current;
    draggedIndex.current = null;
    if (from === null || from === index) return;
    if (isPlaying) onPause();
    const ids = scenes.map((scene) => scene.sceneId);
    [ids[from], ids[index]] = [ids[index], ids[from]];
    onReorder(ids);
  };
  const moveByIds = (index: number, offset: number) => {
    const ids = scenes.map((scene) => scene.sceneId);
    const target = index + offset;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    onReorder(ids);
  };

  const fitAll = () => {
    const scroller = scrollRef.current;
    if (!scroller || totalDuration <= 0) return;
    const available = Math.max(80, scroller.clientWidth - CONTENT_PADDING * 2);
    onZoomChange(clampPps(available / totalDuration));
  };

  const handlePlayheadPointerDown = (event: React.PointerEvent) => {
    event.stopPropagation();
    if (isPlaying) onPause();
    scrubbingRef.current = true;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    seekToClientX(event.clientX);
  };
  const handlePlayheadPointerMove = (event: React.PointerEvent) => {
    if (!scrubbingRef.current) return;
    seekToClientX(event.clientX);
  };
  const handlePlayheadPointerUp = (event: React.PointerEvent) => {
    scrubbingRef.current = false;
    (event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId);
  };

  const handleClipPointerDown = (event: React.PointerEvent, item: TimelineLayoutItem) => {
    event.stopPropagation();
    onSelect(item.sceneId);
    const rect = contentRef.current?.getBoundingClientRect();
    if (rect) {
      const clipLeft = rect.left + CONTENT_PADDING + item.startSeconds * pps;
      const local = clampTimelineTime((event.clientX - clipLeft) / pps + item.startSeconds, totalDuration);
      onSeek(local);
    }
  };

  const roundHold = (value: number) => Math.round(Math.max(0, value) * 10) / 10;
  const handleResizePointerDown = (event: React.PointerEvent, item: TimelineLayoutItem) => {
    event.stopPropagation();
    if (isPlaying) onPause();
    resizeStateRef.current = { sceneId: item.sceneId, startX: event.clientX, startHold: item.holdSeconds };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  };
  const handleResizePointerMove = (event: React.PointerEvent) => {
    const state = resizeStateRef.current;
    if (!state) return;
    const nextHold = roundHold(state.startHold + (event.clientX - state.startX) / pps);
    setHolds((current) => ({ ...current, [state.sceneId]: nextHold }));
  };
  const handleResizePointerUp = (event: React.PointerEvent) => {
    const state = resizeStateRef.current;
    resizeStateRef.current = null;
    (event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId);
    if (!state) return;
    const nextHold = roundHold(state.startHold + (event.clientX - state.startX) / pps);
    if (nextHold !== state.startHold) changeHold(state.sceneId, nextHold);
  };
  const handleResizePointerCancel = (event: React.PointerEvent) => {
    const state = resizeStateRef.current;
    resizeStateRef.current = null;
    (event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId);
    if (state) setHolds((current) => ({ ...current, [state.sceneId]: state.startHold }));
  };

  const ticks = useMemo(() => {
    const majorStep = pps > 48 ? 0.5 : pps > 16 ? 1 : 5;
    const minorStep = majorStep / 5;
    const children: React.ReactNode[] = [];
    const count = Math.ceil(totalDuration / minorStep + 1e-9);
    for (let index = 0; index <= count; index += 1) {
      const time = index * minorStep;
      const x = CONTENT_PADDING + time * pps;
      const isMajor = Math.abs(time / majorStep - Math.round(time / majorStep)) < 1e-9;
      children.push(
        <div key={index} className="absolute top-0" style={{ left: x }}>
          <div className={isMajor ? "h-3 w-px bg-zinc-600" : "h-1.5 w-px bg-zinc-700"} />
          {isMajor && <div className="mt-0.5 text-[8px] leading-none text-zinc-500">{formatTimelineTime(time).slice(0, 5)}</div>}
        </div>,
      );
    }
    return children;
  }, [pps, totalDuration]);

  return (
    <section className="p-1">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="text-caption font-semibold uppercase tracking-wider">时间线</div>
        <div className="ml-1 font-mono text-caption">
          {formatTimelineTime(currentTime)} / {formatTimelineTime(totalDuration)}
        </div>
        <div className="ml-auto flex items-center gap-0.5">
          <button type="button" title="撤销" aria-label="撤销" disabled={!canUndo} onClick={onUndo} className="ui-btn ui-btn-ghost ui-btn-icon !h-8 !w-8 disabled:opacity-30"><Undo2 className="h-3.5 w-3.5" /></button>
          <button type="button" title="重做" aria-label="重做" disabled={!canRedo} onClick={onRedo} className="ui-btn ui-btn-ghost ui-btn-icon !h-8 !w-8 disabled:opacity-30"><Redo2 className="h-3.5 w-3.5" /></button>
          <button type="button" title="缩小" aria-label="缩小" onClick={() => onZoomChange(clampPps(pps / 1.25))} className="ui-btn ui-btn-ghost ui-btn-icon !h-8 !w-8"><ZoomOut className="h-3.5 w-3.5" /></button>
          <input aria-label="缩放比例" type="range" min={MIN_PIXELS_PER_SECOND} max={MAX_PIXELS_PER_SECOND} step={1} value={pps} onChange={(event) => onZoomChange(Number(event.target.value))} className="w-24 accent-amber-500" />
          <button type="button" title="放大" aria-label="放大" onClick={() => onZoomChange(clampPps(pps * 1.25))} className="ui-btn ui-btn-ghost ui-btn-icon !h-8 !w-8"><ZoomIn className="h-3.5 w-3.5" /></button>
          <button type="button" title="适应全部" aria-label="适应全部" onClick={fitAll} className="ui-btn ui-btn-ghost ui-btn-icon !h-8 !w-8"><Maximize className="h-3.5 w-3.5" /></button>
        </div>
      </div>
      <div ref={scrollRef} className="overflow-x-auto rounded-[var(--radius-md)]">
        <div ref={contentRef} className="relative" style={{ width: contentWidth, height: RULER_HEIGHT + TRACK_HEIGHT }}>
          <div onPointerDown={(event) => seekToClientX(event.clientX)} className="absolute inset-x-0 top-0 cursor-pointer border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]" style={{ height: RULER_HEIGHT }}>
            {ticks}
          </div>
          <div onPointerDown={(event) => seekToClientX(event.clientX)} className="absolute inset-x-0 cursor-pointer bg-[var(--color-surface-0)]" style={{ top: RULER_HEIGHT, height: TRACK_HEIGHT }}>
            {layout.map((item, index) => {
              const left = CONTENT_PADDING + item.startSeconds * pps;
              const width = item.durationSeconds * pps;
              const audioWidth = Math.min(width, item.audioDurationSeconds * pps);
              const isActive = item.sceneId === activeSceneId;
              return (
                <div
                  key={item.sceneId}
                  draggable
                  onDragStart={() => { draggedIndex.current = index; }}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={() => dropAt(index)}
                  onPointerDown={(event) => handleClipPointerDown(event, item)}
                  className={`absolute top-0 h-full overflow-hidden rounded-lg border px-1 py-0.5 ${isActive ? "border-amber-500 bg-amber-500/10 ring-1 ring-amber-500/30" : "border-[var(--color-border-strong)] bg-[var(--color-surface-3)]"}`}
                  style={{ left, width }}
                >
                  <div className="truncate text-[9px] leading-tight text-zinc-300">#{item.index + 1} · {getSceneTimelineDuration(scenes[item.index]!, item.holdSeconds).toFixed(1)}s</div>
                  <div className="mt-0.5 flex items-center gap-0.5">
                    <button type="button" title="左移" aria-label="左移" disabled={index === 0} onPointerDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); moveByIds(index, -1); }} className="text-zinc-400 disabled:opacity-30"><ChevronLeft className="h-2.5 w-2.5" /></button>
                    <button type="button" title="右移" aria-label="右移" disabled={index === scenes.length - 1} onPointerDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); moveByIds(index, 1); }} className="text-zinc-400 disabled:opacity-30"><ChevronRight className="h-2.5 w-2.5" /></button>
                  </div>
                  <input aria-label="延长停留" type="number" min="0" step="0.1" value={item.holdSeconds} onPointerDown={(event) => event.stopPropagation()} onClick={(event) => event.stopPropagation()} onChange={(event) => changeHold(item.sceneId, Math.max(0, Number(event.target.value) || 0))} className="mt-0.5 w-full bg-zinc-950 text-[8px] text-zinc-300" />
                  {item.audioDurationSeconds < item.durationSeconds && <div className="pointer-events-none absolute inset-y-0 right-0 bg-black/40" style={{ width: Math.max(0, width - audioWidth) }} />}
                </div>
              );
            })}
            {layout.map((item) => {
              const left = CONTENT_PADDING + item.startSeconds * pps;
              const width = item.durationSeconds * pps;
              return (
                <div
                  key={`resize-${item.sceneId}`}
                  onPointerDown={(event) => handleResizePointerDown(event, item)}
                  onPointerMove={handleResizePointerMove}
                  onPointerUp={handleResizePointerUp}
                  onPointerCancel={handleResizePointerCancel}
                  title="拖动右边缘调整停留时长"
                  aria-label="拖动右边缘调整停留时长"
                  className="absolute inset-y-0 z-10 cursor-col-resize"
                  style={{ left: left + width - 6, width: 12 }}
                />
              );
            })}
          </div>
          <div className="pointer-events-none absolute inset-y-0 z-10" style={{ left: playheadX }}>
            <div className="h-full w-px bg-amber-500" />
            <div className="absolute -left-[5px] top-0 h-2 w-[11px] rounded-b bg-amber-500" />
          </div>
          <div
            onPointerDown={handlePlayheadPointerDown}
            onPointerMove={handlePlayheadPointerMove}
            onPointerUp={handlePlayheadPointerUp}
            onPointerCancel={handlePlayheadPointerUp}
            className="absolute inset-y-0 z-20 cursor-ew-resize"
            style={{ left: playheadX - 6, width: 12 }}
          />
        </div>
      </div>
    </section>
  );
};
