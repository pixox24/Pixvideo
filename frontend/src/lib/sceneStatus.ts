import { GenerationRun, WorkbenchScene } from "../types";

/** Unified visual status for timeline / list / progress. */
export type SceneVisualStatus =
  | "ready"
  | "running"
  | "failed"
  | "stale"
  | "missing"
  | "candidate"
  | "queued";

export const SCENE_STATUS_LABEL: Record<SceneVisualStatus, string> = {
  ready: "就绪",
  running: "生成中",
  failed: "失败",
  stale: "已过期",
  missing: "缺失",
  candidate: "待选版本",
  queued: "排队",
};

export function resolveSceneVisualStatus(
  scene: WorkbenchScene,
  run: GenerationRun | null | undefined,
): SceneVisualStatus {
  const item = run?.items.find((entry) => entry.sceneId === scene.sceneId);
  if (item) {
    if (item.status === "failed") return "failed";
    if (item.status === "candidate_review") return "candidate";
    if (item.status === "completed" || item.status === "skipped") return "ready";
    if (item.status === "queued") return "queued";
    if (
      item.status === "running_tts"
      || item.status === "running_image"
      || String(item.status).startsWith("running")
    ) {
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
  if (scene.status === "failed") return "failed";
  return "missing";
}

export interface SceneStatusSummary {
  ready: number;
  running: number;
  failed: number;
  queued: number;
  stale: number;
  missing: number;
  candidate: number;
  total: number;
  /** Scene ids in timeline order for each failed item. */
  failedSceneIds: string[];
  runningSceneId: string | null;
}

export function summarizeSceneStatuses(
  scenes: WorkbenchScene[],
  run: GenerationRun | null | undefined,
): SceneStatusSummary {
  const summary: SceneStatusSummary = {
    ready: 0,
    running: 0,
    failed: 0,
    queued: 0,
    stale: 0,
    missing: 0,
    candidate: 0,
    total: scenes.length,
    failedSceneIds: [],
    runningSceneId: null,
  };
  for (const scene of scenes) {
    const status = resolveSceneVisualStatus(scene, run);
    summary[status] += 1;
    if (status === "failed") summary.failedSceneIds.push(scene.sceneId);
    if (status === "running" && !summary.runningSceneId) summary.runningSceneId = scene.sceneId;
  }
  if (run?.currentSceneId && !summary.runningSceneId) {
    const current = scenes.find((s) => s.sceneId === run.currentSceneId);
    if (current && resolveSceneVisualStatus(current, run) === "running") {
      summary.runningSceneId = run.currentSceneId;
    } else if (run.currentSceneId) {
      summary.runningSceneId = run.currentSceneId;
    }
  }
  return summary;
}

export function isRunActive(run: GenerationRun | null | undefined): boolean {
  if (!run) return false;
  return run.status === "queued" || run.status === "running" || run.status === "paused";
}

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
