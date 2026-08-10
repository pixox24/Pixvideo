import React from "react";
import { AlertTriangle, Check, Image as ImageIcon, Loader, Volume2 } from "lucide-react";
import { GenerationRun, WorkbenchScene } from "../types";

interface Props {
  scenes: WorkbenchScene[];
  run: GenerationRun | null;
  onSelect: (sceneId: string) => void;
  selectedSceneId: string | null;
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
  ready: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  running: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  failed: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  stale: "border-sky-500/40 bg-sky-500/10 text-sky-200",
  missing: "border-zinc-700 bg-zinc-900 text-zinc-500",
  candidate: "border-violet-500/40 bg-violet-500/10 text-violet-200",
  queued: "border-zinc-600 bg-zinc-900/80 text-zinc-400",
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

export const SceneProgressGrid: React.FC<Props> = ({ scenes, run, onSelect, selectedSceneId }) => {
  if (scenes.length === 0) return null;
  return (
    <div className="border-b border-zinc-800 bg-[#0d0e11] px-3 py-2">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-xs font-medium text-zinc-300">镜头进度</p>
        <p className="text-caption text-zinc-500">点击镜头可定位</p>
      </div>
      <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-10">
        {scenes.map((scene, index) => {
          const status = resolveStatus(scene, run);
          const thumb =
            scene.versions.find((version) => version.versionId === scene.currentVersionId)?.thumbnailUrl ||
            scene.versions.find((version) => version.versionId === scene.currentVersionId)?.imageUrl;
          const selected = selectedSceneId === scene.sceneId;
          return (
            <button
              key={scene.sceneId}
              type="button"
              onClick={() => onSelect(scene.sceneId)}
              title={`分镜 #${index + 1} · ${STATUS_LABEL[status]}`}
              className={`relative overflow-hidden rounded border text-left transition-colors ${STATUS_STYLE[status]} ${
                selected ? "ring-1 ring-amber-400" : ""
              }`}
            >
              <div className="flex aspect-video items-center justify-center bg-black/40">
                {thumb ? (
                  <img src={thumb} alt="" className="h-full w-full object-cover opacity-90" />
                ) : status === "running" ? (
                  <Loader className="h-3.5 w-3.5 animate-spin" />
                ) : status === "failed" ? (
                  <AlertTriangle className="h-3.5 w-3.5" />
                ) : (
                  <ImageIcon className="h-3.5 w-3.5 opacity-60" />
                )}
              </div>
              <div className="flex items-center justify-between px-1 py-0.5 text-[10px]">
                <span>#{index + 1}</span>
                {status === "ready" && <Check className="h-3 w-3" />}
                {status === "running" && <Loader className="h-3 w-3 animate-spin" />}
                {status === "stale" && <Volume2 className="h-3 w-3 opacity-70" />}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
