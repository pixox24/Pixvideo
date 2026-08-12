import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  Circle,
  Loader,
  Pause,
  Play,
  RotateCcw,
  Square,
  X,
} from "lucide-react";
import { GenerationRun, PipelineCellStatus, PipelineProgress, Project } from "../types";

interface Props {
  project: Project;
  run: GenerationRun | null;
  busy: string | null;
  pendingCount: number;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
  onRetryFailed: () => void;
  onRetryExport: () => void;
  onCancelExport?: () => void;
  onLocateScene: (sceneId: string) => void;
}

const CELL_LABEL: Record<string, string> = {
  idle: "—",
  queued: "等",
  running: "…",
  ready: "✓",
  failed: "✕",
  skipped: "跳",
  missing: "缺",
  stale: "旧",
  candidate: "选",
};

const cellClass = (status: string) => {
  switch (status) {
    case "ready":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-300";
    case "running":
      return "border-amber-500/40 bg-amber-500/10 text-amber-200 animate-pulse";
    case "failed":
      return "border-rose-500/40 bg-rose-500/10 text-rose-300";
    case "candidate":
      return "border-violet-500/40 bg-violet-500/10 text-violet-200";
    case "stale":
      return "border-sky-500/40 bg-sky-500/10 text-sky-200";
    case "missing":
      return "border-rose-500/20 bg-rose-950/20 text-rose-200/70";
    case "queued":
      return "border-zinc-700 bg-zinc-900/60 text-zinc-400";
    default:
      return "border-zinc-800 bg-zinc-950/40 text-zinc-600";
  }
};

const Cell: React.FC<{ status: string; title: string }> = ({ status, title }) => (
  <span
    title={`${title}: ${status}`}
    className={`inline-flex h-6 min-w-[1.5rem] items-center justify-center rounded border px-1 text-[10px] font-semibold ${cellClass(status)}`}
  >
    {status === "running" ? <Loader className="h-3 w-3 animate-spin" /> : CELL_LABEL[status] || status.slice(0, 1)}
  </span>
);

function buildFallbackProgress(project: Project, run: GenerationRun | null, pendingCount: number): PipelineProgress {
  const exportActive =
    project.latestExport?.status === "pending" || project.latestExport?.status === "running";
  const exportDone = project.latestExport?.status === "completed";
  const exportFailed = project.latestExport?.status === "failed";
  const runTerminal = run
    ? ["completed", "completed_with_failures", "cancelled", "failed"].includes(run.status)
    : true;

  const scenes = project.scenes.map((scene, index) => {
    const item = run?.items.find((entry) => entry.sceneId === scene.sceneId);
    let tts: PipelineCellStatus = "idle";
    let image: PipelineCellStatus = "idle";
    if (item) {
      if (item.ttsStatus === "failed" || item.status === "failed") tts = "failed";
      else if (item.status === "running_tts") tts = "running";
      else if (item.ttsStatus === "completed" || item.status === "completed" || item.status === "skipped") tts = "ready";
      else if (item.status === "queued") tts = "queued";
      if (item.imageStatus === "failed") image = "failed";
      else if (item.status === "running_image") image = "running";
      else if (item.imageStatus === "completed" || item.status === "completed") image = "ready";
      else if (item.status === "candidate_review") image = "candidate";
      else if (item.status === "queued") image = "queued";
    } else {
      const gs = scene.generationState;
      if (gs?.audio === "ready") tts = "ready";
      else if (gs?.audio === "missing") tts = "missing";
      else if (gs?.audio === "stale") tts = "stale";
      if (gs?.image === "ready") image = "ready";
      else if (gs?.image === "missing") image = "missing";
      else if (gs?.image === "stale") image = "stale";
    }
    let segment: PipelineCellStatus = "idle";
    const expProg = project.latestExport?.progress;
    if (exportDone) segment = "ready";
    else if (exportActive || exportFailed) {
      const row = expProg?.segments?.find((s) => s.sceneId === scene.sceneId);
      segment = (row?.status as PipelineCellStatus) || "queued";
    }
    return {
      sceneId: scene.sceneId,
      position: scene.position ?? index,
      narration: (scene.narration || "").slice(0, 48),
      tts,
      image,
      segment,
    };
  });

  let phase = "idle";
  let summary = "尚未开始";
  if (exportActive) {
    phase = "export";
    const cur = project.latestExport?.progress?.segmentCurrent || 0;
    const total = project.latestExport?.progress?.segmentTotal || project.scenes.length;
    const stage = project.latestExport?.progress?.stage;
    if (stage === "concat") summary = "素材完成 · 正在合并成片";
    else summary = `素材完成 · 导出编码 ${cur}/${total}`;
  } else if (run && !runTerminal) {
    phase = "assets";
    summary = `素材 ${run.completedCount}/${run.totalCount}${pendingCount ? ` · 待处理 ${pendingCount}` : ""}`;
  } else if (exportFailed) {
    phase = "failed";
    summary = "导出失败";
  } else if (exportDone) {
    phase = "done";
    summary = project.latestExport?.purpose === "initial" ? "初稿已就绪" : "成片已就绪";
  } else if (run && runTerminal) {
    phase = "assets_done";
    summary = run.status === "completed_with_failures" ? "素材有失败项" : "素材已完成 · 待导出";
  }

  return {
    phase,
    summary,
    updatedAt: project.latestExport?.updatedAt || run?.updatedAt || project.updatedAt,
    assets: run
      ? {
          runId: run.runId,
          status: run.status,
          completed: run.completedCount,
          total: run.totalCount,
          failed: run.failedCount,
          currentSceneId: run.currentSceneId,
        }
      : null,
    export: project.latestExport
      ? {
          exportId: project.latestExport.exportId,
          status: project.latestExport.status,
          purpose: project.latestExport.purpose,
          stage: project.latestExport.progress?.stage,
          segmentCurrent: project.latestExport.progress?.segmentCurrent,
          segmentTotal: project.latestExport.progress?.segmentTotal,
          segments: project.latestExport.progress?.segments,
          error: project.latestExport.status === "failed" ? "导出失败" : null,
          updatedAt: project.latestExport.updatedAt,
        }
      : null,
    scenes,
    focus: null,
  };
}

export const ProgressObservatory: React.FC<Props> = ({
  project,
  run,
  busy,
  pendingCount,
  onStart,
  onPause,
  onResume,
  onCancel,
  onRetryFailed,
  onRetryExport,
  onCancelExport,
  onLocateScene,
}) => {
  const [open, setOpen] = useState(false);
  const progress = useMemo(
    () => project.pipelineProgress || buildFallbackProgress(project, run, pendingCount),
    [project, run, pendingCount],
  );

  const exportActive =
    project.latestExport?.status === "pending" || project.latestExport?.status === "running";
  const runTerminal = run
    ? ["completed", "completed_with_failures", "cancelled", "failed"].includes(run.status)
    : true;
  const active = Boolean((run && !runTerminal) || exportActive);
  const failedExport = project.latestExport?.status === "failed";
  // Stuck/running exports also need a force-retry (retry API now accepts running).
  const canForceRetryExport =
    failedExport
    || project.latestExport?.status === "cancelled"
    || exportActive;
  const failedAssets = run?.status === "completed_with_failures" || (run?.failedCount || 0) > 0;

  // Stall hint: same summary for >90s
  const [stall, setStall] = useState(false);
  useEffect(() => {
    if (!active) {
      setStall(false);
      return;
    }
    const stamp = progress.updatedAt || project.updatedAt;
    const started = Date.now();
    const timer = window.setInterval(() => {
      const age = Date.now() - started;
      // If parent reloads and updatedAt advances, reset via dependency
      setStall(age > 90_000);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [active, progress.summary, progress.updatedAt, project.updatedAt]);

  const assetsPct = progress.assets?.total
    ? Math.round(((progress.assets.completed || 0) / progress.assets.total) * 100)
    : 0;
  const exportPct =
    progress.export?.segmentTotal
      ? Math.round(((progress.export.segmentCurrent || 0) / progress.export.segmentTotal) * 100)
      : exportActive
        ? 5
        : progress.phase === "done"
          ? 100
          : 0;
  const barPct = exportActive || progress.phase === "export" || progress.phase === "done"
    ? Math.min(100, 50 + exportPct / 2)
    : assetsPct;

  const can = (action: string, fallback: boolean) =>
    run?.allowedActions ? run.allowedActions.includes(action) : fallback;

  const pipelineSteps = [
    { key: "assets", label: "素材", done: ["assets_done", "export", "done", "failed"].includes(progress.phase) || (runTerminal && Boolean(run)) },
    { key: "export", label: "导出", done: progress.phase === "done", active: progress.phase === "export" || exportActive },
    { key: "ready", label: "可验收", done: progress.phase === "done" },
  ];

  return (
    <section className="shrink-0 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]">
      {/* L0 top bar */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-1.5">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left hover:opacity-90"
          aria-expanded={open}
          title="打开进度观测台"
        >
          <span className="shrink-0 text-[11px] font-semibold text-zinc-200">进度</span>
          <p
            className={`min-w-0 truncate text-caption ${
              failedExport || progress.phase === "failed"
                ? "text-rose-300"
                : stall
                  ? "text-amber-200"
                  : "text-zinc-500"
            }`}
          >
            {progress.summary}
            {stall ? " · 较久无更新" : ""}
          </p>
          {active && (
            <div className="hidden h-1 w-20 shrink-0 overflow-hidden rounded-full bg-[var(--color-surface-3)] sm:block md:w-28">
              <div className="h-full rounded-full bg-amber-500 transition-all" style={{ width: `${barPct}%` }} />
            </div>
          )}
          {open ? <ChevronUp className="h-3.5 w-3.5 shrink-0 text-zinc-500" /> : <ChevronDown className="h-3.5 w-3.5 shrink-0 text-zinc-500" />}
        </button>

        <div className="flex flex-wrap items-center gap-1.5">
          {failedAssets && run && (
            <button type="button" onClick={onRetryFailed} disabled={busy !== null} className="ui-btn ui-btn-outline ui-btn-sm !h-7 text-amber-200">
              <RotateCcw className="h-3.5 w-3.5" />
              重试失败
            </button>
          )}
          {exportActive && onCancelExport && (
            <button
              type="button"
              onClick={onCancelExport}
              disabled={busy !== null}
              className="ui-btn ui-btn-danger ui-btn-sm !h-7"
              title="取消当前导出（结束本进程内的编码任务）"
            >
              <Square className="h-3.5 w-3.5" />
              取消导出
            </button>
          )}
          {canForceRetryExport && (
            <button
              type="button"
              onClick={onRetryExport}
              disabled={busy !== null}
              className={`ui-btn ui-btn-outline ui-btn-sm !h-7 ${exportActive && !failedExport ? "text-amber-200" : "text-rose-200"}`}
              title={exportActive && !failedExport ? "强制结束卡住的导出并重新开始" : "重新导出成片"}
            >
              <RotateCcw className="h-3.5 w-3.5" />
              {exportActive && !failedExport ? "强制重试导出" : "重试导出"}
            </button>
          )}
          {(!run || (runTerminal && run.status !== "completed_with_failures")) && !exportActive && (
            <button type="button" onClick={onStart} disabled={busy !== null} className="ui-btn ui-btn-primary ui-btn-sm !h-7">
              <Play className="h-3.5 w-3.5" />
              开始生成
            </button>
          )}
          {run && can("pause", run.status === "queued" || run.status === "running") && (
            <button type="button" onClick={onPause} disabled={busy !== null} className="ui-btn ui-btn-secondary ui-btn-sm !h-7">
              <Pause className="h-3.5 w-3.5" />
              暂停
            </button>
          )}
          {run && can("resume", run.status === "paused") && (
            <button type="button" onClick={onResume} disabled={busy !== null} className="ui-btn ui-btn-primary ui-btn-sm !h-7">
              <Play className="h-3.5 w-3.5" />
              继续
            </button>
          )}
          {run && can("cancel", !runTerminal) && (
            <button type="button" onClick={onCancel} disabled={busy !== null} className="ui-btn ui-btn-danger ui-btn-sm !h-7">
              <Square className="h-3.5 w-3.5" />
              取消
            </button>
          )}
        </div>
      </div>

      {active && (
        <div className="h-0.5 overflow-hidden bg-[var(--color-surface-3)] sm:hidden">
          <div className="h-full bg-amber-500 transition-all" style={{ width: `${barPct}%` }} />
        </div>
      )}

      {/* L1 observatory panel */}
      {open && (
        <div className="border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] px-3 py-3 animate-fade-in">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-zinc-400">
              {pipelineSteps.map((step, index) => (
                <React.Fragment key={step.key}>
                  {index > 0 && <span className="text-zinc-700">→</span>}
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 ${
                      step.done
                        ? "border-emerald-500/30 text-emerald-300"
                        : step.active
                          ? "border-amber-500/40 text-amber-200"
                          : "border-zinc-800 text-zinc-500"
                    }`}
                  >
                    {step.done ? <Check className="h-3 w-3" /> : step.active ? <Loader className="h-3 w-3 animate-spin" /> : <Circle className="h-2.5 w-2.5" />}
                    {step.label}
                  </span>
                </React.Fragment>
              ))}
            </div>
            <button type="button" onClick={() => setOpen(false)} className="ui-btn ui-btn-ghost ui-btn-sm !h-7 text-zinc-400">
              <X className="h-3.5 w-3.5" />
              收起
            </button>
          </div>

          <p className="mb-1 text-xs text-zinc-300">
            当前：{progress.summary}
            {progress.focus?.cell === "segment" && progress.focus.sceneIndex
              ? ` · 编码第 ${progress.focus.sceneIndex}/${progress.focus.sceneTotal || "?"} 镜`
              : ""}
          </p>
          {stall && (
            <p className="mb-2 flex items-center gap-1 text-[11px] text-amber-200/90">
              <AlertTriangle className="h-3 w-3" />
              本步较久无更新；若持续不动可重试导出或刷新页面
            </p>
          )}
          {progress.export?.error && (
            <p className="mb-2 text-[11px] text-rose-300" role="alert">
              {progress.export.error}
            </p>
          )}

          <div className="max-h-56 overflow-auto rounded-[var(--radius-md)] border border-[var(--color-border-subtle)]">
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-[var(--color-surface-2)] text-zinc-500">
                <tr>
                  <th className="px-2 py-1.5 font-medium">#</th>
                  <th className="px-2 py-1.5 font-medium">旁白</th>
                  <th className="px-2 py-1.5 font-medium text-center">配音</th>
                  <th className="px-2 py-1.5 font-medium text-center">画面</th>
                  <th className="px-2 py-1.5 font-medium text-center">编码</th>
                  <th className="px-2 py-1.5 font-medium" />
                </tr>
              </thead>
              <tbody>
                {(progress.scenes || []).map((row) => {
                  const highlight =
                    progress.focus?.sceneId === row.sceneId
                    || (progress.focus?.sceneIndex != null && progress.focus.sceneIndex === row.position + 1);
                  return (
                    <tr
                      key={row.sceneId}
                      className={`border-t border-[var(--color-border-subtle)] ${highlight ? "bg-amber-500/5" : ""}`}
                    >
                      <td className="px-2 py-1.5 font-mono text-zinc-400">{row.position + 1}</td>
                      <td className="max-w-[12rem] truncate px-2 py-1.5 text-zinc-300" title={row.narration}>
                        {row.narration || "（空）"}
                      </td>
                      <td className="px-2 py-1.5 text-center"><Cell status={row.tts} title="配音" /></td>
                      <td className="px-2 py-1.5 text-center"><Cell status={row.image} title="画面" /></td>
                      <td className="px-2 py-1.5 text-center"><Cell status={row.segment} title="编码" /></td>
                      <td className="px-2 py-1.5 text-right">
                        <button
                          type="button"
                          className="text-amber-400/90 hover:text-amber-300"
                          onClick={() => onLocateScene(row.sceneId)}
                        >
                          定位
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {(!progress.scenes || progress.scenes.length === 0) && (
                  <tr>
                    <td colSpan={6} className="px-2 py-4 text-center text-zinc-600">
                      开始生成后将显示每镜配音 / 画面 / 编码状态
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <p className="mt-2 text-[10px] text-zinc-600">
            配音/画面=素材阶段 · 编码=导出阶段（素材期显示 —）· 预览进度为近似，以导出成片为准
          </p>
        </div>
      )}
    </section>
  );
};
