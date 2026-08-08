import React, { useMemo, useState } from "react";
import { Check, Image as ImageIcon } from "lucide-react";
import { WorkbenchScene } from "../types";

interface Props { scenes: WorkbenchScene[]; selectedSceneId: string | null; selectedSceneIds: Set<string>; onSelect: (id: string) => void; onToggle: (id: string) => void; className?: string; }

export const SceneList: React.FC<Props> = ({ scenes, selectedSceneId, selectedSceneIds, onSelect, onToggle, className = "" }) => {
  const [scrollTop, setScrollTop] = useState(0);
  const rowHeight = 72;
  const start = Math.max(0, Math.floor(scrollTop / rowHeight) - 3);
  const visibleScenes = useMemo(() => scenes.slice(start, start + 18), [scenes, start]);
  return (
    <section className={`min-h-0 flex flex-col border-r border-zinc-800 bg-[#0d0e11] ${className}`}>
      <div className="border-b border-zinc-800 px-3 py-2 text-xs font-semibold text-zinc-200">分镜 / 素材</div>
      <div className="min-h-0 flex-1 overflow-y-auto" onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}>
        <div style={{ height: scenes.length * rowHeight, position: "relative" }}>
          {visibleScenes.map((scene, index) => {
            const position = start + index;
            return <button key={scene.sceneId} type="button" onClick={() => onSelect(scene.sceneId)} className={`absolute left-0 right-0 flex h-[72px] items-center gap-2 border-b border-zinc-900 px-2 text-left ${selectedSceneId === scene.sceneId ? "bg-amber-500/10" : "hover:bg-zinc-900/70"}`} style={{ top: position * rowHeight }}>
              <input type="checkbox" aria-label={`选择分镜 ${position + 1}`} checked={selectedSceneIds.has(scene.sceneId)} onClick={(event) => event.stopPropagation()} onChange={() => onToggle(scene.sceneId)} />
              <div className="flex h-12 w-16 shrink-0 items-center justify-center overflow-hidden bg-zinc-900 text-zinc-600">{scene.versions.find((version) => version.versionId === scene.currentVersionId)?.thumbnailUrl || scene.versions.find((version) => version.versionId === scene.currentVersionId)?.imageUrl ? <img src={scene.versions.find((version) => version.versionId === scene.currentVersionId)?.thumbnailUrl || scene.versions.find((version) => version.versionId === scene.currentVersionId)?.imageUrl} alt="当前画面" className="h-full w-full object-cover" /> : <ImageIcon className="h-4 w-4" />}</div>
              <div className="min-w-0 flex-1"><div className="text-[10px] text-zinc-500">#{position + 1}</div><div className="truncate text-xs text-zinc-300">{scene.narration.slice(0, 42)}</div></div>
              {scene.status === "completed" && <Check className="h-3.5 w-3.5 text-emerald-400" />}
            </button>;
          })}
        </div>
      </div>
    </section>
  );
};
