import React, { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { WorkbenchScene } from "../types";
import { effectiveSceneDuration } from "../lib/workbenchState";

interface Props { scenes: WorkbenchScene[]; selectedSceneId: string | null; onSelect: (id: string) => void; onReorder: (ids: string[]) => void; onHold: (sceneId: string, hold: number) => void; }
export const WorkbenchTimeline: React.FC<Props> = ({ scenes, selectedSceneId, onSelect, onReorder, onHold }) => {
  const [holds, setHolds] = useState<Record<string, number>>({});
  const timers = useRef<Record<string, number>>({});
  const draggedIndex = useRef<number | null>(null);
  useEffect(() => setHolds(Object.fromEntries(scenes.map((scene) => [scene.sceneId, scene.manualHoldSeconds]))), [scenes]);
  useEffect(() => () => Object.values(timers.current).forEach((timer) => window.clearTimeout(timer as number)), []);
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
    const ids = scenes.map((scene) => scene.sceneId);
    [ids[from], ids[index]] = [ids[index], ids[from]];
    onReorder(ids);
  };
  return <section className="border-t border-zinc-800 bg-[#0d0e11] p-3"><div className="mb-2 text-[10px] font-semibold uppercase text-zinc-500">时间线</div><div className="flex gap-1 overflow-x-auto pb-1">{scenes.map((scene, index) => { const hold = holds[scene.sceneId] ?? scene.manualHoldSeconds; return <div key={scene.sceneId} draggable onDragStart={() => { draggedIndex.current = index; }} onDragOver={(event) => event.preventDefault()} onDrop={() => dropAt(index)} onClick={() => onSelect(scene.sceneId)} className={`relative min-w-[48px] border p-2 ${selectedSceneId === scene.sceneId ? "border-amber-500" : "border-zinc-800"}`} style={{ width: Math.max(48, effectiveSceneDuration(scene.durationSeconds, hold) * 24) }}><div className="truncate text-[10px] text-zinc-300">#{index + 1}</div><div className="text-[9px] text-zinc-500">{effectiveSceneDuration(scene.durationSeconds, hold).toFixed(1)}s</div><div className="mt-1 flex items-center gap-1"><button type="button" title="左移" aria-label="左移" disabled={index === 0} onClick={(event) => { event.stopPropagation(); const ids = scenes.map((item) => item.sceneId); [ids[index - 1], ids[index]] = [ids[index], ids[index - 1]]; onReorder(ids); }}><ChevronLeft className="h-3 w-3" /></button><button type="button" title="右移" aria-label="右移" disabled={index === scenes.length - 1} onClick={(event) => { event.stopPropagation(); const ids = scenes.map((item) => item.sceneId); [ids[index], ids[index + 1]] = [ids[index + 1], ids[index]]; onReorder(ids); }}><ChevronRight className="h-3 w-3" /></button></div><input aria-label="拖动延长停留" className="mt-1 w-full accent-amber-500" type="range" min="0" max="30" step="0.1" value={hold} onClick={(event) => event.stopPropagation()} onChange={(event) => changeHold(scene.sceneId, Math.max(0, Number(event.target.value) || 0))} /><input aria-label="延长停留" className="mt-1 w-full bg-zinc-950 text-[9px]" type="number" min="0" step="0.1" value={hold} onClick={(event) => event.stopPropagation()} onChange={(event) => changeHold(scene.sceneId, Math.max(0, Number(event.target.value) || 0))} /></div>; })}</div></section>;
};
