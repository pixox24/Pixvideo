import React, { useMemo, useState } from "react";
import { AlertTriangle, Check, Image as ImageIcon } from "lucide-react";
import { WorkbenchScene } from "../types";

interface Props {
  scenes: WorkbenchScene[];
  selectedSceneId: string | null;
  selectedSceneIds: Set<string>;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
  className?: string;
}

function sceneBadge(scene: WorkbenchScene): { label: string; className: string; icon: "ok" | "run" | "fail" | "warn" | null } {
  const image = scene.generationState?.image;
  const audio = scene.generationState?.audio;
  if ((scene.generationState?.candidateCount || 0) > 0) {
    return { label: "待选", className: "text-violet-300", icon: "warn" };
  }
  if (image === "stale" || audio === "stale") {
    return { label: "过期", className: "text-sky-300", icon: "warn" };
  }
  if (image === "missing" || audio === "missing") {
    return { label: "缺失", className: "text-amber-300", icon: "warn" };
  }
  if (image === "ready" && audio === "ready") {
    return { label: "就绪", className: "text-emerald-400", icon: "ok" };
  }
  if (scene.status === "completed" || (scene.currentVersionId && scene.audioUrl)) {
    return { label: "就绪", className: "text-emerald-400", icon: "ok" };
  }
  if (scene.status === "failed") {
    return { label: "失败", className: "text-rose-400", icon: "fail" };
  }
  return { label: "待生成", className: "text-zinc-500", icon: null };
}

export const SceneList: React.FC<Props> = ({ scenes, selectedSceneId, selectedSceneIds, onSelect, onToggle, className = "" }) => {
  const [scrollTop, setScrollTop] = useState(0);
  const rowHeight = 76;
  const start = Math.max(0, Math.floor(scrollTop / rowHeight) - 3);
  const visibleScenes = useMemo(() => scenes.slice(start, start + 18), [scenes, start]);
  return (
    <section
      className={`flex min-h-0 flex-col border-r border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] ${className}`}
    >
      <div className="border-b border-[var(--color-border-subtle)] px-3 py-2 text-xs font-semibold text-zinc-200">
        分镜列表
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto" onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}>
        <div style={{ height: scenes.length * rowHeight, position: "relative" }}>
          {visibleScenes.map((scene, index) => {
            const position = start + index;
            const thumb =
              scene.versions.find((version) => version.versionId === scene.currentVersionId)?.thumbnailUrl ||
              scene.versions.find((version) => version.versionId === scene.currentVersionId)?.imageUrl;
            const badge = sceneBadge(scene);
            const active = selectedSceneId === scene.sceneId;
            return (
              <button
                key={scene.sceneId}
                type="button"
                onClick={() => onSelect(scene.sceneId)}
                className={`absolute left-0 right-0 flex h-[76px] items-center gap-2 px-2 text-left transition-colors ${
                  active
                    ? "bg-amber-500/10 ring-1 ring-inset ring-amber-500/20"
                    : "hover:bg-white/5"
                }`}
                style={{ top: position * rowHeight }}
              >
                <input
                  type="checkbox"
                  aria-label={`选择分镜 ${position + 1}`}
                  checked={selectedSceneIds.has(scene.sceneId)}
                  onClick={(event) => event.stopPropagation()}
                  onChange={() => onToggle(scene.sceneId)}
                  className="accent-amber-500"
                />
                <div className="flex h-12 w-16 shrink-0 items-center justify-center overflow-hidden rounded-[var(--radius-sm)] bg-[var(--color-surface-3)] text-zinc-600">
                  {thumb ? (
                    <img src={thumb} alt="当前画面" className="h-full w-full object-cover" />
                  ) : (
                    <ImageIcon className="h-4 w-4" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 text-caption">
                    <span>#{position + 1}</span>
                    <span className={badge.className}>{badge.label}</span>
                  </div>
                  <div className="truncate text-xs text-zinc-300">{scene.narration.slice(0, 42)}</div>
                </div>
                {badge.icon === "ok" && <Check className="h-3.5 w-3.5 text-emerald-400" />}
                {badge.icon === "fail" && <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />}
                {badge.icon === "warn" && <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />}
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
};
