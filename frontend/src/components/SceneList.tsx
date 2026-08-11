import React, { useMemo, useState } from "react";
import { AlertTriangle, Check, Image as ImageIcon, Loader } from "lucide-react";
import { GenerationRun, WorkbenchScene } from "../types";
import { resolveSceneVisualStatus, SCENE_STATUS_LABEL, SceneVisualStatus } from "../lib/sceneStatus";

interface Props {
  scenes: WorkbenchScene[];
  selectedSceneId: string | null;
  selectedSceneIds: Set<string>;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
  className?: string;
  /** Output frame aspect (w/h); used for thumb box. Default 16/9. */
  frameAspect?: number;
  generationRun?: GenerationRun | null;
}

function badgeFromStatus(status: SceneVisualStatus): { label: string; className: string; icon: "ok" | "run" | "fail" | "warn" | null } {
  switch (status) {
    case "ready":
      return { label: SCENE_STATUS_LABEL.ready, className: "text-emerald-400", icon: "ok" };
    case "running":
      return { label: SCENE_STATUS_LABEL.running, className: "text-amber-300", icon: "run" };
    case "failed":
      return { label: SCENE_STATUS_LABEL.failed, className: "text-rose-400", icon: "fail" };
    case "candidate":
      return { label: SCENE_STATUS_LABEL.candidate, className: "text-violet-300", icon: "warn" };
    case "stale":
      return { label: SCENE_STATUS_LABEL.stale, className: "text-sky-300", icon: "warn" };
    case "queued":
      return { label: SCENE_STATUS_LABEL.queued, className: "text-zinc-400", icon: null };
    default:
      return { label: SCENE_STATUS_LABEL.missing, className: "text-amber-300", icon: "warn" };
  }
}

export const SceneList: React.FC<Props> = ({
  scenes,
  selectedSceneId,
  selectedSceneIds,
  onSelect,
  onToggle,
  className = "",
  frameAspect = 16 / 9,
  generationRun = null,
}) => {
  const [scrollTop, setScrollTop] = useState(0);
  const rowHeight = 76;
  // Fixed height thumb; width follows project aspect (letterbox inside).
  const thumbH = 48;
  const aspect = frameAspect > 0.2 && frameAspect < 5 ? frameAspect : 16 / 9;
  const thumbW = Math.round(Math.min(72, Math.max(36, thumbH * aspect)));
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
            const badge = badgeFromStatus(resolveSceneVisualStatus(scene, generationRun));
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
                <div
                  className="relative shrink-0 overflow-hidden rounded-[var(--radius-sm)] bg-[var(--color-surface-0)] text-zinc-600 ring-1 ring-inset ring-white/5"
                  style={{ width: thumbW, height: thumbH }}
                >
                  {thumb ? (
                    <img
                      src={thumb}
                      alt=""
                      className="absolute inset-0 h-full w-full object-contain"
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center">
                      <ImageIcon className="h-4 w-4" />
                    </div>
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
                {badge.icon === "run" && <Loader className="h-3.5 w-3.5 animate-spin text-amber-300" />}
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
