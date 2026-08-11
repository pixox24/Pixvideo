import React from "react";
import { AlertTriangle, Pause, Play, RotateCcw, Square } from "lucide-react";
import { GenerationRun, GenerationRunItem } from "../types";

interface Props {
  run: GenerationRun | null;
  busy: string | null;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
  onRetry: () => void;
  onLocateFailure: (sceneId: string) => void;
  pendingCount: number;
  /** When generation finished but draft/final export is still running. */
  exportStatus?: string | null;
  exportPurpose?: string | null;
}

const STATUS_LABELS: Record<string, string> = {
  queued: "等待开始",
  running: "正在生成",
  paused: "已暂停",
  completed: "已完成",
  completed_with_failures: "有失败项",
  cancelled: "已取消",
  failed: "生成失败",
};

const failedStage = (item: GenerationRunItem) => {
  if (item.imageStatus === "failed") return "图片";
  if (item.ttsStatus === "failed") return "配音";
  return "素材";
};

export const GenerationRunPanel: React.FC<Props> = ({
  run, busy, onStart, onPause, onResume, onCancel, onRetry, onLocateFailure, pendingCount,
  exportStatus = null,
  exportPurpose = null,
}) => {
  const status = run?.status ?? "idle";
  const terminal = status === "completed" || status === "completed_with_failures" || status === "cancelled" || status === "failed";
  const can = (action: string, fallback: boolean) => run?.allowedActions ? run.allowedActions.includes(action) : fallback;
  const progress = run && run.totalCount
    ? Math.round(((run.completedCount + run.skippedCount + run.failedCount + run.candidateReviewCount) / run.totalCount) * 100)
    : 0;
  const failedItems = run?.items.filter((item) => item.status === "failed") ?? [];
  const activeItem = run?.items.find((item) => item.sceneId === run.currentSceneId);
  const activeSceneLabel = activeItem
    ? `正在处理分镜 #${activeItem.position + 1}/${run?.totalCount || "?"}（${activeItem.status === "running_tts" ? "配音" : activeItem.status === "running_image" ? "画面" : "素材"}）`
    : null;
  const exportActive = exportStatus === "pending" || exportStatus === "running";
  const detailLine = !run
    ? "尚未开始生成"
    : !terminal
      ? `${activeSceneLabel || `待处理 ${pendingCount} 项`} · ${progress}% · ${STATUS_LABELS[status] || status}`
      : exportActive
        ? `分镜素材已全部完成 · 正在${exportPurpose === "initial" ? "合成初稿视频" : "导出成片"}（与最后一镜无关，通常还需约 1–3 分钟）`
        : `分镜素材 ${progress}% · ${STATUS_LABELS[status] || status}`;

  return (
    <section className="shrink-0 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs font-semibold text-zinc-100">项目生成</div>
          <div className="text-caption leading-relaxed text-zinc-500">
            {detailLine}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!run || (terminal && status !== "completed_with_failures") ? (
            <button type="button" onClick={onStart} disabled={busy !== null} className="ui-btn ui-btn-primary ui-btn-sm">
              <Play className="h-3.5 w-3.5" />开始生成
            </button>
          ) : null}
          {run && can("pause", status === "queued" || status === "running") && (
            <button type="button" onClick={onPause} disabled={busy !== null} className="ui-btn ui-btn-secondary ui-btn-sm">
              <Pause className="h-3.5 w-3.5" />暂停
            </button>
          )}
          {run && can("resume", status === "paused") && (
            <button type="button" onClick={onResume} disabled={busy !== null} className="ui-btn ui-btn-primary ui-btn-sm">
              <Play className="h-3.5 w-3.5" />继续生成
            </button>
          )}
          {run && can("cancel", !terminal) && (
            <button type="button" onClick={onCancel} disabled={busy !== null} className="ui-btn ui-btn-danger ui-btn-sm">
              <Square className="h-3.5 w-3.5" />取消
            </button>
          )}
          {run && can("retry-failed", status === "completed_with_failures") && (
            <button type="button" onClick={onRetry} disabled={busy !== null} className="ui-btn ui-btn-outline ui-btn-sm text-amber-200">
              <RotateCcw className="h-3.5 w-3.5" />仅重试失败项
            </button>
          )}
        </div>
      </div>
      {run && !terminal && (
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-[var(--color-surface-3)]">
          <div className="h-full rounded-full bg-amber-500 transition-all" style={{ width: `${progress}%` }} />
        </div>
      )}
      {terminal && exportActive && (
        <div className="mt-2 rounded-[var(--radius-md)] border border-amber-500/25 bg-amber-500/5 px-2.5 py-2 text-[11px] text-amber-100/90">
          分镜配音/画面已经生成完毕。当前在后台把各镜头合成初稿 MP4，界面可能仍显示忙碌，但不是某一镜卡住。
        </div>
      )}
      {failedItems.length > 0 && (
        <div role="alert" className="mt-2 rounded-[var(--radius-md)] border border-rose-500/30 bg-rose-950/20 p-2 text-xs text-rose-100">
          <div className="flex items-center gap-1 font-semibold">
            <AlertTriangle className="h-3.5 w-3.5" />
            {failedItems.length} 个分镜生成失败
          </div>
          <div className="mt-2 grid gap-1">
            {failedItems.map((item) => (
              <button
                key={item.itemId}
                type="button"
                onClick={() => onLocateFailure(item.sceneId)}
                className="flex items-center justify-between gap-2 rounded-[var(--radius-sm)] border border-rose-500/20 px-2 py-1.5 text-left hover:bg-rose-900/20"
              >
                <span>分镜 #{item.position + 1} · {failedStage(item)}失败</span>
                <span className="max-w-[55%] truncate text-rose-200" title={item.error || undefined}>
                  {item.error || "请重试"}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};
