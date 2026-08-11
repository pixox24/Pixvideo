import React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { GenerationJob } from "../types";

export const GenerationQueue: React.FC<{
  jobs: GenerationJob[];
  expanded?: boolean;
  onToggle?: () => void;
}> = ({ jobs, expanded = false, onToggle }) => {
  const running = jobs.filter((j) => j.status === "pending" || j.status === "running").length;
  const summary =
    jobs.length === 0
      ? "暂无生成任务"
      : running > 0
        ? `${jobs.length} 个任务 · ${running} 进行中`
        : `${jobs.length} 个任务`;

  return (
    <section className="shrink-0 border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-white/5"
        aria-expanded={expanded}
      >
        <span className="text-caption font-semibold uppercase tracking-wider text-zinc-500">
          任务队列 · {summary}
        </span>
        {expanded ? (
          <ChevronUp className="h-3.5 w-3.5 text-zinc-500" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-zinc-500" />
        )}
      </button>
      {expanded && (
        <div className="flex gap-2 overflow-x-auto px-3 pb-3">
          {jobs.length === 0 ? (
            <span className="text-xs text-zinc-600">暂无生成任务</span>
          ) : (
            jobs.map((job) => (
              <div
                key={job.jobId}
                className="min-w-40 rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-3)] px-2 py-1.5 text-xs text-zinc-300"
              >
                {job.kind === "export" ? "导出" : job.kind} · {job.status} · {Math.round(job.progress)}%
                {job.error && <div className="mt-1 text-rose-400">{job.error}</div>}
              </div>
            ))
          )}
        </div>
      )}
    </section>
  );
};
