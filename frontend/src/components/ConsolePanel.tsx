import React from "react";
import { XCircle, Download, ChevronRight } from "lucide-react";
import { Task } from "../types";
import { VideoPreview } from "./VideoPreview";

interface ConsolePanelProps {
  activeTask: Task | null;
  recentTasks: Task[];
  onSelectTask: (task: Task) => void;
  onCancelTask: (task: Task) => void;
  addToast: (text: string, type: "success" | "error" | "info") => void;
  isOpen: boolean;
  onClose: () => void;
}

type ProgressStageKey =
  | "submit"
  | "content"
  | "title"
  | "visuals"
  | "audio"
  | "media"
  | "compose"
  | "segment"
  | "post"
  | "completed";

const GENERATION_PROGRESS_STEPS: { key: ProgressStageKey; label: string }[] = [
  { key: "submit", label: "任务提交" },
  { key: "content", label: "文案/旁白处理" },
  { key: "title", label: "标题生成" },
  { key: "visuals", label: "视觉提示词" },
  { key: "audio", label: "逐帧配音" },
  { key: "media", label: "图片/视频素材" },
  { key: "compose", label: "画面字幕合成" },
  { key: "segment", label: "视频片段生成" },
  { key: "post", label: "合并/BGM" },
  { key: "completed", label: "成片完成" },
];

const FRAME_ACTION_STAGE: Record<string, ProgressStageKey> = {
  audio: "audio",
  media: "media",
  compose: "compose",
  video: "segment",
};

const FRAME_ACTION_LABEL: Record<string, string> = {
  audio: "逐帧配音",
  media: "图片/视频素材生成",
  compose: "画面字幕合成",
  video: "视频片段生成",
};

function getProgressStageKey(task: Task): ProgressStageKey {
  if (task.status === "completed") return "completed";

  if (task.progressEventType === "generating_narrations" || task.progressEventType === "splitting_script") {
    return "content";
  }
  if (task.progressEventType === "generating_title") return "title";
  if (task.progressEventType === "generating_image_prompts") return "visuals";
  if (task.progressEventType === "processing_frame") return "audio";
  if (task.progressEventType === "frame_step" && task.progressAction) {
    return FRAME_ACTION_STAGE[task.progressAction] || "audio";
  }
  if (task.progressEventType === "concatenating") return "post";
  if (task.progressEventType === "completed") return "completed";

  return "submit";
}

function getProgressStageLabel(task: Task): string {
  if (task.status === "cancelled") return "任务已取消";
  if (task.progressEventType === "splitting_script") return "拆分固定文案";
  if (task.progressEventType === "generating_narrations") return "生成旁白文案";
  if (task.progressEventType === "generating_title") return "生成视频标题";
  if (task.progressEventType === "generating_image_prompts") return "生成视觉提示词";
  if (task.progressEventType === "processing_frame") return "准备逐帧处理";
  if (task.progressEventType === "frame_step" && task.progressAction) {
    return FRAME_ACTION_LABEL[task.progressAction] || "逐帧处理";
  }
  if (task.progressEventType === "concatenating") return "合并片段 / BGM 混音";
  if (task.status === "completed" || task.progressEventType === "completed") return "成片完成";
  if (task.status === "failed") return task.currentStep || "任务失败";
  return task.currentStep || "任务提交";
}

function formatLiveProgressLabel(task: Task): string {
  const stageLabel = getProgressStageLabel(task);
  const frameLabel =
    task.progressFrameCurrent && task.progressFrameTotal
      ? `第 ${task.progressFrameCurrent}/${task.progressFrameTotal} 帧`
      : "";
  const extraLabel = task.progressExtraInfo ? ` · ${task.progressExtraInfo}` : "";

  return `${frameLabel ? `${frameLabel} - ` : ""}${stageLabel}${extraLabel}`;
}

function getStepStatus(task: Task, idx: number) {
  const activeStage = getProgressStageKey(task);
  const activeStepIdx = GENERATION_PROGRESS_STEPS.findIndex((step) => step.key === activeStage);

  if (task.status === "completed") return "completed";
  if (task.status === "failed") {
    if (idx < activeStepIdx) return "completed";
    if (idx === activeStepIdx) return "failed";
    return "pending";
  }
  if (task.status === "cancelled") {
    if (idx < activeStepIdx) return "completed";
    if (idx === activeStepIdx) return "cancelled";
    return "pending";
  }

  if (idx < activeStepIdx) return "completed";
  if (idx === activeStepIdx) return "current";
  return "pending";
}

export const ConsolePanel: React.FC<ConsolePanelProps> = ({
  activeTask,
  recentTasks,
  onSelectTask,
  onCancelTask,
  addToast,
  isOpen,
  onClose,
}) => {
  return (
    <aside
      className={`${isOpen ? "flex" : "hidden"} fixed inset-y-0 right-0 z-40 h-full w-[min(400px,100vw)] flex-shrink-0 flex-col overflow-y-auto border-l border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] lg:static lg:w-96 xl:w-[400px]`}
      aria-label="任务运行面板"
    >
      {/* 1. Header Title */}
      <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-3">
        <span className="text-xs font-semibold tracking-wide text-zinc-300">
          任务进度
        </span>
        {activeTask?.status === "generating" ? (
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
          </span>
        ) : (
          <span className="h-2 w-2" />
        )}
        <button
          type="button"
          onClick={onClose}
          className="ui-btn ui-btn-ghost ui-btn-icon ml-2"
          aria-label="关闭任务面板"
        >
          <XCircle className="h-4 w-4" />
        </button>
      </div>

      {/* 2. Active Run Monitor or Config Summary */}
      <div className="space-y-4 border-b border-[var(--color-border-subtle)] bg-[var(--color-surface-2)]/60 p-4">
        {activeTask ? (
          <div className="ui-card space-y-3 !p-4">
            <div className="flex items-start justify-between gap-2">
              <h4 className="min-w-0 flex-1 text-sm font-semibold text-zinc-100 line-clamp-1">{activeTask.title}</h4>
              <span className="shrink-0 text-caption font-medium text-zinc-400">{activeTask.progress}%</span>
            </div>
            <div>
              {activeTask.status === "completed" && <span className="ui-chip ui-chip-success">成片已就绪</span>}
              {activeTask.status === "generating" && <span className="ui-chip ui-chip-brand">生成中</span>}
              {activeTask.status === "failed" && <span className="ui-chip ui-chip-danger">失败</span>}
              {activeTask.status === "cancelled" && <span className="ui-chip">已取消</span>}
            </div>

            <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--color-surface-4)]">
              <div
                className="h-full rounded-full bg-[var(--color-brand-500)] transition-all duration-300"
                style={{ width: `${activeTask.progress}%` }}
              />
            </div>

            <p className="text-caption leading-relaxed text-zinc-400">
              当前步骤 · {formatLiveProgressLabel(activeTask)}
            </p>

            {activeTask.status === "generating" && (
              <button
                type="button"
                onClick={() => onCancelTask(activeTask)}
                className="ui-btn ui-btn-secondary w-full"
              >
                <XCircle className="h-3.5 w-3.5" />
                取消任务
              </button>
            )}

            <ol className="space-y-1.5">
              {GENERATION_PROGRESS_STEPS.map((step, idx) => {
                const status = getStepStatus(activeTask, idx);
                return (
                  <li key={step.key} className="flex items-center justify-between gap-2">
                    <span className="text-caption text-zinc-400">
                      {String(idx + 1).padStart(2, "0")} {step.label}
                    </span>
                    {status === "completed" && <span className="ui-chip ui-chip-success">OK</span>}
                    {status === "current" && <span className="ui-chip ui-chip-brand">进行中</span>}
                    {status === "failed" && <span className="ui-chip ui-chip-danger">失败</span>}
                    {status === "cancelled" && <span className="ui-chip">已取消</span>}
                    {status === "pending" && <span className="text-caption text-zinc-600">待处理</span>}
                  </li>
                );
              })}
            </ol>

            {activeTask.status === "completed" && activeTask.videoUrl && (
              <div className="space-y-2 pt-2">
                <VideoPreview
                  src={activeTask.videoUrl}
                  poster={activeTask.scenes?.[0]?.imageUrl}
                />
                <a
                  href={activeTask.videoUrl}
                  download
                  onClick={() => addToast("开始下载高清成品视频", "success")}
                  className="ui-btn ui-btn-primary w-full"
                >
                  <Download className="h-3.5 w-3.5 text-black" />
                  下载最终成片视频 (MP4)
                </a>
              </div>
            )}

            {activeTask.status === "failed" && (
              <div className="ui-panel text-sm leading-relaxed text-rose-300">
                <strong className="mb-1 block font-semibold">生成失败</strong>
                {activeTask.errorMsg || "未知配置错误，检查底层算力秘钥是否就绪。"}
              </div>
            )}
          </div>
        ) : (
          <div className="ui-card space-y-1 py-6 text-center">
            <p className="text-sm font-medium text-zinc-300">还没有运行中的任务</p>
            <p className="text-caption mx-auto max-w-[220px] text-zinc-500">
              在开始创作里提交后，进度会出现在这里。
            </p>
          </div>
        )}
      </div>

      {/* 3. Recent Tasks Queue */}
      <div className="flex min-h-0 flex-1 flex-col p-4">
        <h3 className="mb-2.5 block text-caption font-semibold tracking-wider text-zinc-500">
          最近任务
        </h3>

        <div className="flex-1 space-y-2.5 overflow-y-auto pr-1">
          {recentTasks.map((t) => (
            <div
              key={t.id}
              onClick={() => onSelectTask(t)}
              className="flex cursor-pointer items-center justify-between gap-3 rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-3)] p-2.5 text-xs transition-colors hover:ring-1 hover:ring-amber-500/20"
            >
              <div className="min-w-0">
                <span className="block truncate font-medium text-zinc-200">
                  {t.title}
                </span>
                <span className="mt-1 block text-caption text-zinc-500">
                  {t.createdTime.split(" ")[1]} · {t.sceneCount} 镜
                </span>
              </div>

              <div className="flex flex-shrink-0 items-center gap-1.5">
                {t.status === "completed" && <span className="ui-chip ui-chip-success">已就绪</span>}
                {t.status === "failed" && <span className="ui-chip ui-chip-danger">失败</span>}
                {t.status === "generating" && <span className="ui-chip ui-chip-brand">渲染中</span>}
                {t.status === "cancelled" && <span className="ui-chip">已取消</span>}
                <ChevronRight className="h-3 w-3 text-zinc-500" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
};
