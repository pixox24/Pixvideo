import React from "react";
import { Pause, Play, RotateCcw, Square } from "lucide-react";
import { GenerationRun } from "../types";

interface Props {
  run: GenerationRun | null;
  busy: string | null;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
  onRetry: () => void;
  pendingCount: number;
}

export const GenerationRunPanel: React.FC<Props> = ({ run, busy, onStart, onPause, onResume, onCancel, onRetry, pendingCount }) => {
  const status = run?.status ?? "idle";
  const terminal = status === "completed" || status === "completed_with_failures" || status === "cancelled" || status === "failed";
  const can = (action: string, fallback: boolean) => run?.allowedActions ? run.allowedActions.includes(action) : fallback;
  const progress = run && run.totalCount
    ? Math.round(((run.completedCount + run.skippedCount + run.failedCount + run.candidateReviewCount) / run.totalCount) * 100)
    : 0;

  return (
    <section className="border-b border-zinc-800 bg-[#15161a] px-3 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold text-zinc-100">项目生成</div>
          <div className="text-[11px] text-zinc-500">
            待生成 {pendingCount} 项{run ? ` · ${progress}% · ${status}` : ""}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!run || terminal ? <button type="button" onClick={onStart} disabled={busy !== null} className="flex items-center gap-1 bg-amber-500 px-3 py-2 text-xs font-semibold text-black disabled:opacity-40"><Play className="h-3.5 w-3.5" />开始生成</button> : null}
          {run && can("pause", status === "queued" || status === "running") && <button type="button" onClick={onPause} disabled={busy !== null} className="flex items-center gap-1 border border-zinc-700 px-3 py-2 text-xs text-zinc-200 disabled:opacity-40"><Pause className="h-3.5 w-3.5" />暂停</button>}
          {run && can("resume", status === "paused") && <button type="button" onClick={onResume} disabled={busy !== null} className="flex items-center gap-1 bg-amber-500 px-3 py-2 text-xs font-semibold text-black disabled:opacity-40"><Play className="h-3.5 w-3.5" />继续生成</button>}
          {run && can("cancel", !terminal) && <button type="button" onClick={onCancel} disabled={busy !== null} className="flex items-center gap-1 border border-red-900 px-3 py-2 text-xs text-red-300 disabled:opacity-40"><Square className="h-3.5 w-3.5" />取消</button>}
          {run && can("retry-failed", status === "completed_with_failures") && <button type="button" onClick={onRetry} disabled={busy !== null} className="flex items-center gap-1 border border-zinc-700 px-3 py-2 text-xs text-zinc-200 disabled:opacity-40"><RotateCcw className="h-3.5 w-3.5" />仅重试失败项</button>}
        </div>
      </div>
      {run && !terminal && <div className="mt-3 h-1 overflow-hidden bg-zinc-800"><div className="h-full bg-amber-500 transition-all" style={{ width: `${progress}%` }} /></div>}
    </section>
  );
};
