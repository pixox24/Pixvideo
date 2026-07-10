import React from "react";
import { Sliders, RefreshCw, FileText, CheckCircle2, XCircle, Play, Download, Settings, ChevronRight } from "lucide-react";
import { Task } from "../types";
import { VideoPreview } from "./VideoPreview";

interface ConsolePanelProps {
  activeTask: Task | null;
  recentTasks: Task[];
  onSelectTask: (task: Task) => void;
  addToast: (text: string, type: "success" | "error" | "info") => void;
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

  if (idx < activeStepIdx) return "completed";
  if (idx === activeStepIdx) return "current";
  return "pending";
}

export const ConsolePanel: React.FC<ConsolePanelProps> = ({
  activeTask,
  recentTasks,
  onSelectTask,
  addToast,
}) => {
  return (
    <div className="bg-[#101114] border-l border-zinc-900 w-full lg:w-96 xl:w-[400px] flex-shrink-0 flex flex-col h-full overflow-y-auto">
      {/* 1. Header Title */}
      <div className="p-3 border-b border-zinc-900 bg-[#0c0d10] flex items-center justify-between">
        <span className="text-xs font-semibold text-zinc-300 font-mono tracking-wider uppercase">
          运行控制后台 / Console
        </span>
        <span className="flex h-2 w-2 relative">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
        </span>
      </div>

      {/* 2. Active Run Monitor or Config Summary */}
      <div className="p-4 border-b border-zinc-900 bg-[#121318]/50 space-y-4">
        {activeTask ? (
          <div className="space-y-4">
            <div className="flex justify-between items-start">
              <div>
                <span className="text-[10px] text-amber-500 font-mono uppercase tracking-wider block font-bold">
                  ●正在生成视频...
                </span>
                <h4 className="text-sm font-semibold text-zinc-100 mt-1 line-clamp-1">{activeTask.title}</h4>
              </div>
              <span className="text-xs font-mono font-semibold text-amber-400">{activeTask.progress}%</span>
            </div>

            {/* Flat styled progress bar */}
            <div className="w-full bg-zinc-850 h-1.5 rounded-full overflow-hidden">
              <div
                className="bg-gradient-to-r from-amber-600 to-amber-400 h-full rounded-full transition-all duration-300"
                style={{ width: `${activeTask.progress}%` }}
              />
            </div>

            <div className="bg-zinc-950/50 border border-zinc-850 rounded px-2.5 py-2 text-[10px] font-mono leading-relaxed">
              <span className="text-zinc-500 uppercase mr-1.5">当前步骤:</span>
              <span className="text-amber-300">{formatLiveProgressLabel(activeTask)}</span>
            </div>

            {/* Multi-step list indicator */}
            <div className="space-y-2 pt-1">
              <span className="text-[10px] text-zinc-500 font-mono uppercase block">时序生成进度:</span>
              <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
                {GENERATION_PROGRESS_STEPS.map((step, idx) => {
                  const status = getStepStatus(activeTask, idx);
                  return (
                    <div
                      key={step.key}
                      className={`px-2 py-1 rounded flex items-center justify-between transition-colors ${
                        status === "completed"
                          ? "bg-emerald-500/5 text-emerald-400 border border-emerald-500/10"
                          : status === "current"
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/20 font-bold animate-pulse"
                          : status === "failed"
                          ? "bg-rose-500/10 text-rose-400 border border-rose-500/20 font-bold"
                          : "bg-zinc-900/60 text-zinc-550 border border-transparent"
                      }`}
                    >
                      <span>{String(idx + 1).padStart(2, "0")} {step.label}</span>
                      {status === "completed" && <span className="text-[8px] uppercase">OK</span>}
                      {status === "current" && <span className="text-[8px] uppercase">RUN</span>}
                      {status === "failed" && <span className="text-[8px] uppercase">ERR</span>}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Quick output preview if completed right in sidebar */}
            {activeTask.status === "completed" && activeTask.videoUrl && (
              <div className="space-y-2 pt-2 border-t border-zinc-900 animate-fade-in">
                <span className="text-[10px] text-zinc-500 font-mono uppercase block">成片即时预览:</span>
                <VideoPreview
                  src={activeTask.videoUrl}
                  poster={activeTask.scenes?.[0]?.imageUrl}
                  className="border-zinc-850"
                />
                <a
                  href={activeTask.videoUrl}
                  download
                  onClick={() => addToast("开始下载高清成品视频", "success")}
                  className="w-full py-1.5 bg-amber-500 hover:bg-amber-400 text-black text-xs font-semibold rounded flex items-center justify-center gap-1.5 transition-colors"
                >
                  <Download className="w-3.5 h-3.5 text-black" />
                  下载最终成片视频 (MP4)
                </a>
              </div>
            )}

            {/* Error Output if failed */}
            {activeTask.status === "failed" && (
              <div className="bg-rose-500/10 border border-rose-500/20 text-rose-400 p-2.5 rounded text-[11px] font-mono leading-relaxed animate-fade-in">
                <strong className="font-semibold block mb-0.5 flex items-center gap-1">
                  <XCircle className="w-3.5 h-3.5" /> 错误日志:
                </strong>
                {activeTask.errorMsg || "未知配置错误，检查底层算力秘钥是否就绪。"}
              </div>
            )}
          </div>
        ) : (
          <div className="py-4 text-center space-y-2">
            <Sliders className="w-6 h-6 text-zinc-600 mx-auto animate-pulse-slow" />
            <p className="text-xs text-zinc-400 font-medium">控制台就绪，等待生产任务</p>
            <p className="text-[10px] text-zinc-500 max-w-[180px] mx-auto leading-normal">
              在左侧中心工作台中配置大模型及配乐，点击“生成视频”开始。
            </p>
          </div>
        )}
      </div>

      {/* 3. Recent Tasks Queue */}
      <div className="p-4 flex-1 flex flex-col min-h-0">
        <h3 className="text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-2.5 block font-bold">
          最近生产队列 / Recent Jobs
        </h3>

        <div className="space-y-2.5 overflow-y-auto flex-1 pr-1">
          {recentTasks.map((t) => (
            <div
              key={t.id}
              onClick={() => onSelectTask(t)}
              className="bg-[#14151a] border border-zinc-900 rounded p-2.5 hover:border-zinc-800 transition-all cursor-pointer text-xs flex justify-between gap-3 items-center"
            >
              <div className="min-w-0">
                <span className="font-medium text-zinc-350 block truncate group-hover:text-zinc-200">
                  {t.title}
                </span>
                <span className="text-[9px] font-mono text-zinc-550 block mt-1">
                  {t.createdTime.split(" ")[1]} • {t.sceneCount} 帧分镜
                </span>
              </div>

              <div className="flex-shrink-0 flex items-center gap-1.5">
                {t.status === "completed" && (
                  <span className="text-[9px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1 py-0.5 rounded font-mono">
                    已就绪
                  </span>
                )}
                {t.status === "failed" && (
                  <span className="text-[9px] bg-rose-500/10 text-rose-400 border border-rose-500/20 px-1 py-0.5 rounded font-mono">
                    失败
                  </span>
                )}
                {t.status === "generating" && (
                  <span className="text-[9px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-1 py-0.5 rounded font-mono animate-pulse">
                    渲染中
                  </span>
                )}
                <ChevronRight className="w-3 h-3 text-zinc-650" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
