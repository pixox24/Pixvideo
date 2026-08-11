import React, { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronUp, Pause, Play, RotateCcw, Square } from "lucide-react";
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
  run,
  busy,
  onStart,
  onPause,
  onResume,
  onCancel,
  onRetry,
  onLocateFailure,
  pendingCount,
  exportStatus = null,
  exportPurpose = null,
}) => {
  const [failuresOpen, setFailuresOpen] = useState(false);
  const status = run?.status ?? "idle";
  const terminal =
    status === "completed"
    || status === "completed_with_failures"
    || status === "cancelled"
    || status === "failed";
  const can = (action: string, fallback: boolean) =>
    (run?.allowedActions ? run.allowedActions.includes(action) : fallback);
  const progress = run && run.totalCount
    ? Math.round(
      ((run.completedCount + run.skippedCount + run.failedCount + run.candidateReviewCount)
        / run.totalCount) * 100,
    )
    : 0;
  const failedItems = run?.items.filter((item) => item.status === "failed") ?? [];
  const activeItem = run?.items.find((item) => item.sceneId === run.currentSceneId);
  const activeSceneLabel = activeItem
    ? `#${activeItem.position + 1}/${run?.totalCount || "?"} ${
      activeItem.status === "running_tts"
        ? "配音"
        : activeItem.status === "running_image"
          ? "画面"
          : "素材"
    }`
    : null;
  const exportActive = exportStatus === "pending" || exportStatus === "running";

  const detailCompact = !run
    ? "尚未开始生成"
    : !terminal
      ? `${activeSceneLabel || `待处理 ${pendingCount}`} · ${progress}% · ${STATUS_LABELS[status] || status}`
      : exportActive
        ? `素材已完成 · 正在${exportPurpose === "initial" ? "合成初稿" : "导出成片"}`
        : `${STATUS_LABELS[status] || status}${failedItems.length ? ` · ${failedItems.length} 失败` : ""}`;

  // Hide entirely when idle with no run — keeps workbench quiet after completion
  // unless there are failures or export running.
  if (!run && !exportActive) {
    return (
      <section className="grp shrink-0 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] px-3 py-1.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="min-w-0 truncate text-caption text-zinc-500">{detailCompact}</p>
          <button
            type="button"
            onClick={onStart}
            disabled={busy !== null}
            className="ui-btn ui-btn-primary ui-btn-sm"
          >
            <Play className="h-3.5 w-3.5" />
            开始生成
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="grp shrink-0 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] px-3 py-1.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span className="shrink-0 text-[11px] font-semibold text-zinc-200">生成</span>
          <p className="min-w-0 truncate text-caption text-zinc-500" title={detailCompact}>
            {detailCompact}
          </p>
          {run && !terminal && (
            <div className="hidden h-1 w-20 shrink-0 overflow-hidden rounded-full bg-[var(--color-surface-3)] sm:block md:w-28">
              <div
                className="h-full rounded-full bg-amber-500 transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {failedItems.length > 0 && (
            <button
              type="button"
              onClick={() => setFailuresOpen((open) => !open)}
              className="ui-btn ui-btn-outline ui-btn-sm !h-7 border-rose-500/30 text-rose-200"
            >
              <AlertTriangle className="h-3 w-3" />
              {failedItems.length} 失败
              {failuresOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
          )}
          {!run || (terminal && status !== "completed_with_failures") ? (
            <button type="button" onClick={onStart} disabled={busy !== null} className="ui-btn ui-btn-primary ui-btn-sm !h-7">
              <Play className="h-3.5 w-3.5" />
              开始生成
            </button>
          ) : null}
          {run && can("pause", status === "queued" || status === "running") && (
            <button type="button" onClick={onPause} disabled={busy !== null} className="ui-btn ui-btn-secondary ui-btn-sm !h-7">
              <Pause className="h-3.5 w-3.5" />
              暂停
            </button>
          )}
          {run && can("resume", status === "paused") && (
            <button type="button" onClick={onResume} disabled={busy !== null} className="ui-btn ui-btn-primary ui-btn-sm !h-7">
              <Play className="h-3.5 w-3.5" />
              继续
            </button>
          )}
          {run && can("cancel", !terminal) && (
            <button type="button" onClick={onCancel} disabled={busy !== null} className="ui-btn ui-btn-danger ui-btn-sm !h-7">
              <Square className="h-3.5 w-3.5" />
              取消
            </button>
          )}
          {run && can("retry-failed", status === "completed_with_failures") && (
            <button
              type="button"
              onClick={onRetry}
              disabled={busy !== null}
              className="ui-btn ui-btn-outline ui-btn-sm !h-7 text-amber-200"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              重试失败
            </button>
          )}
        </div>
      </div>

      {run && !terminal && (
        <div className="mt-1.5 h-0.5 overflow-hidden rounded-full bg-[var(--color-surface-3)] sm:hidden">
          <div className="h-full rounded-full bg-amber-500 transition-all" style={{ width: `${progress}%` }} />
        </div>
      )}

      {terminal && exportActive && (
        <p className="mt-1.5 text-[11px] leading-snug text-amber-100/80">
          分镜素材已齐，后台正在合成 MP4（通常 1–3 分钟），不是某一镜卡住。
        </p>
      )}

      {failuresOpen && failedItems.length > 0 && (
        <div role="alert" className="mt-1.5 max-h-28 overflow-y-auto rounded-[var(--radius-sm)] border border-rose-500/25 bg-rose-950/20 p-1.5">
          <div className="grid gap-0.5">
            {failedItems.map((item) => (
              <button
                key={item.itemId}
                type="button"
                onClick={() => onLocateFailure(item.sceneId)}
                className="flex items-center justify-between gap-2 rounded px-2 py-1 text-left text-[11px] text-rose-100 hover:bg-rose-900/25"
              >
                <span className="shrink-0">
                  #{item.position + 1} · {failedStage(item)}失败
                </span>
                <span className="min-w-0 truncate text-rose-200/80" title={item.error || undefined}>
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
