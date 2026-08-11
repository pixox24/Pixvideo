import React, { useMemo } from "react";
import { AlertTriangle, Check, Image as ImageIcon, Loader, Volume2 } from "lucide-react";
import { GenerationRun, WorkbenchScene } from "../types";

interface Props {
  scenes: WorkbenchScene[];
  run: GenerationRun | null;
  onSelect: (sceneId: string) => void;
  selectedSceneId: string | null;
  /** Output frame aspect (width / height). Defaults to 16/9 when unknown. */
  frameAspect?: number;
}

type SceneVisualStatus =
  | "ready"
  | "running"
  | "failed"
  | "stale"
  | "missing"
  | "candidate"
  | "queued";

function resolveStatus(scene: WorkbenchScene, run: GenerationRun | null): SceneVisualStatus {
  const item = run?.items.find((entry) => entry.sceneId === scene.sceneId);
  if (item) {
    if (item.status === "failed") return "failed";
    if (item.status === "candidate_review") return "candidate";
    if (item.status === "completed" || item.status === "skipped") return "ready";
    if (item.status === "queued") return "queued";
    if (item.status.startsWith("running") || item.status === "running_tts" || item.status === "running_image") {
      return "running";
    }
  }
  const image = scene.generationState?.image;
  const audio = scene.generationState?.audio;
  if (image === "stale" || audio === "stale") return "stale";
  if (image === "missing" || audio === "missing") return "missing";
  if ((scene.generationState?.candidateCount || 0) > 0) return "candidate";
  if (image === "ready" && audio === "ready") return "ready";
  if (scene.currentVersionId && scene.audioUrl) return "ready";
  return "missing";
}

const STATUS_STYLE: Record<SceneVisualStatus, string> = {
  ready: "border-emerald-500/35 bg-emerald-500/5 text-emerald-300",
  running: "border-amber-500/35 bg-amber-500/5 text-amber-200",
  failed: "border-rose-500/35 bg-rose-500/5 text-rose-300",
  stale: "border-sky-500/35 bg-sky-500/5 text-sky-200",
  missing: "border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] text-zinc-500",
  candidate: "border-violet-500/35 bg-violet-500/5 text-violet-200",
  queued: "border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] text-zinc-400",
};

const STATUS_LABEL: Record<SceneVisualStatus, string> = {
  ready: "就绪",
  running: "生成中",
  failed: "失败",
  stale: "已过期",
  missing: "缺失",
  candidate: "待选版本",
  queued: "排队",
};

function clampAspect(value: number | undefined): number {
  if (!value || !Number.isFinite(value) || value <= 0.2 || value > 5) return 16 / 9;
  return value;
}

/**
 * Progress strip: fixed *frame* from project aspect + object-contain media.
 * Avoids force-crop (object-cover) which misrepresents composition;
 * still keeps a uniform grid unlike free-form natural aspect per cell.
 */
export const SceneProgressGrid: React.FC<Props> = ({
  scenes,
  run,
  onSelect,
  selectedSceneId,
  frameAspect,
}) => {
  const aspect = useMemo(() => clampAspect(frameAspect), [frameAspect]);
  if (scenes.length === 0) return null;

  // Portrait projects: fewer columns so each cell stays readable.
  const gridClass =
    aspect < 0.85
      ? "grid grid-cols-5 gap-1.5 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10"
      : aspect > 1.3
        ? "grid grid-cols-4 gap-1.5 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10"
        : "grid grid-cols-4 gap-1.5 sm:grid-cols-5 md:grid-cols-7 lg:grid-cols-9";

  return (
    <div className="border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] px-3 py-2">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-zinc-300">镜头进度</p>
        <p className="text-caption text-zinc-500">完整画面 · 点击定位</p>
      </div>
      <div className={gridClass}>
        {scenes.map((scene, index) => {
          const status = resolveStatus(scene, run);
          const version = scene.versions.find((entry) => entry.versionId === scene.currentVersionId);
          const thumb = version?.thumbnailUrl || version?.imageUrl;
          const selected = selectedSceneId === scene.sceneId;
          return (
            <button
              key={scene.sceneId}
              type="button"
              onClick={() => onSelect(scene.sceneId)}
              title={`分镜 #${index + 1} · ${STATUS_LABEL[status]}`}
              className={`group relative overflow-hidden rounded-[var(--radius-sm)] border text-left transition-[box-shadow,border-color] ${STATUS_STYLE[status]} ${
                selected ? "ring-1 ring-amber-400/80 border-amber-500/40" : "hover:border-white/15"
              }`}
            >
              {/* Frame follows output aspect; media letterboxed inside */}
              <div
                className="relative w-full bg-[var(--color-surface-0)]"
                style={{ aspectRatio: String(aspect) }}
              >
                {thumb ? (
                  <img
                    src={thumb}
                    alt=""
                    className="absolute inset-0 h-full w-full object-contain opacity-95 transition-opacity group-hover:opacity-100"
                    loading="lazy"
                    decoding="async"
                  />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center">
                    {status === "running" ? (
                      <Loader className="h-3.5 w-3.5 animate-spin" />
                    ) : status === "failed" ? (
                      <AlertTriangle className="h-3.5 w-3.5" />
                    ) : (
                      <ImageIcon className="h-3.5 w-3.5 opacity-50" />
                    )}
                  </div>
                )}
                {/* Soft vignette so letterbox feels intentional, not empty */}
                <div
                  className="pointer-events-none absolute inset-0 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.04)]"
                  aria-hidden
                />
              </div>
              <div className="flex items-center justify-between gap-1 px-1 py-0.5 text-[10px]">
                <span className="font-medium tabular-nums">#{index + 1}</span>
                {status === "ready" && <Check className="h-3 w-3 shrink-0" />}
                {status === "running" && <Loader className="h-3 w-3 shrink-0 animate-spin" />}
                {status === "stale" && <Volume2 className="h-3 w-3 shrink-0 opacity-70" />}
                {status === "failed" && <AlertTriangle className="h-3 w-3 shrink-0" />}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};

/** Resolve frame aspect from project.config (mediaWidth/mediaHeight or template path). */
export function frameAspectFromConfig(config: Record<string, unknown> | null | undefined): number {
  if (!config) return 16 / 9;
  const w = Number(config.mediaWidth ?? config.media_width ?? config.width);
  const h = Number(config.mediaHeight ?? config.media_height ?? config.height);
  if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) return w / h;

  const template = String(config.template ?? config.templatePath ?? config.template_path ?? "");
  const match = template.match(/(\d{3,5})\s*[xX×]\s*(\d{3,5})/);
  if (match) {
    const tw = Number(match[1]);
    const th = Number(match[2]);
    if (tw > 0 && th > 0) return tw / th;
  }
  return 16 / 9;
}
