import React, { useState } from "react";
import { Select } from "./Select";
import {
  History,
  Search,
  CheckCircle2,
  XCircle,
  Clock,
  Download,
  Trash2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  SlidersHorizontal,
  Film,
  Layers,
} from "lucide-react";
import { Task } from "../types";
import { VideoPreview } from "./VideoPreview";
import { ConfirmModal } from "./ConfirmModal";
import { EmptyState } from "./EmptyState";

interface HistoryListProps {
  tasks: Task[];
  onDeleteTask: (id: string) => void | Promise<void>;
  onResumeTask: (task: Task) => void;
  onCancelTask: (task: Task) => void;
  onOpenWorkbench: (task: Task) => void;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

const STATUS_FILTERS = [
  { id: "all", label: "全部" },
  { id: "completed", label: "已完成" },
  { id: "generating", label: "生成中" },
  { id: "failed", label: "失败" },
  { id: "cancelled", label: "已取消" },
] as const;

const tabTypeLabel = (tabType: Task["tabType"]) => {
  if (tabType === "quick-create") return "快捷创作";
  if (tabType === "custom-media") return "自定义素材";
  if (tabType === "digital-human") return "数字人口播";
  if (tabType === "image-to-video") return "图生视频";
  if (tabType === "action-transfer") return "动作迁移";
  return tabType;
};

const statusChip = (status: Task["status"]) => {
  if (status === "completed") return { label: "已完成", className: "ui-chip ui-chip-success" };
  if (status === "failed") return { label: "失败", className: "ui-chip ui-chip-danger" };
  if (status === "generating") return { label: "生成中", className: "ui-chip ui-chip-warning" };
  if (status === "cancelled") return { label: "已取消", className: "ui-chip" };
  return { label: "就绪", className: "ui-chip" };
};

export const HistoryList: React.FC<HistoryListProps> = ({
  tasks,
  onDeleteTask,
  onResumeTask,
  onCancelTask,
  onOpenWorkbench,
  addToast,
}) => {
  const [filter, setFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<"createdTime" | "sceneCount" | "title">("createdTime");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null);
  const [deleting, setDeleting] = useState(false);

  const toggleExpand = (id: string) => {
    setExpandedTaskId(expandedTaskId === id ? null : id);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await onDeleteTask(deleteTarget.id);
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  const filteredTasks = tasks
    .filter((task) => {
      if (filter !== "all" && task.status !== filter) return false;
      if (searchQuery.trim() !== "") {
        return (
          task.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
          task.configSummary?.toLowerCase().includes(searchQuery.toLowerCase())
        );
      }
      return true;
    })
    .sort((a, b) => {
      let comparison = 0;
      if (sortBy === "createdTime") {
        comparison = new Date(a.createdTime).getTime() - new Date(b.createdTime).getTime();
      } else if (sortBy === "sceneCount") {
        comparison = a.sceneCount - b.sceneCount;
      } else if (sortBy === "title") {
        comparison = a.title.localeCompare(b.title);
      }
      return sortOrder === "desc" ? -comparison : comparison;
    });

  return (
    <div className="mx-auto max-w-6xl animate-fade-in space-y-5">
      <ConfirmModal
        open={Boolean(deleteTarget)}
        danger
        busy={deleting}
        title="删除历史任务？"
        description={
          deleteTarget
            ? `将删除「${deleteTarget.title}」。此操作不可撤销，成片与任务记录会从历史中移除。`
            : undefined
        }
        confirmLabel="确认删除"
        onCancel={() => {
          if (!deleting) setDeleteTarget(null);
        }}
        onConfirm={confirmDelete}
      />

      {/* Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div className="space-y-1">
          <h2 className="font-display flex items-center gap-2 text-lg font-semibold text-zinc-100">
            <History className="h-5 w-5 text-amber-500" />
            作品库
          </h2>
          <p className="text-sm text-zinc-400">
            查看与下载历史成片，也可复制为可编辑项目继续精修。
          </p>
        </div>
        <div className="relative w-full max-w-xs">
          <input
            type="text"
            placeholder="搜索标题或配置…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="ui-input pl-9"
          />
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
        </div>
      </div>

      {/* Filters */}
      <div className="ui-panel flex flex-wrap items-center justify-between gap-3 !py-2">
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-caption mr-1 font-medium">状态</span>
          {STATUS_FILTERS.map((status) => (
            <button
              key={status.id}
              type="button"
              onClick={() => setFilter(status.id)}
              className={`rounded-full px-2.5 py-1 text-xs transition-colors ${
                filter === status.id
                  ? "bg-amber-500/10 font-medium text-amber-300 ring-1 ring-amber-500/25"
                  : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
              }`}
            >
              {status.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <SlidersHorizontal className="h-3.5 w-3.5 text-zinc-500" />
          <span className="text-caption">排序</span>
          <Select
            value={sortBy}
            onChange={(e: any) => setSortBy(e.target.value)}
            className="ui-input !h-8 !w-auto !py-0"
          >
            <option value="createdTime">创建时间</option>
            <option value="sceneCount">分镜数量</option>
            <option value="title">任务标题</option>
          </Select>
          <button
            type="button"
            onClick={() => setSortOrder(sortOrder === "desc" ? "asc" : "desc")}
            className="ui-btn ui-btn-ghost ui-btn-icon !h-8 !w-8"
            aria-label={sortOrder === "desc" ? "降序" : "升序"}
          >
            {sortOrder === "desc" ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>

      {/* Card grid */}
      {filteredTasks.length === 0 ? (
        <EmptyState
          icon={<Film className="h-10 w-10" />}
          title={tasks.length === 0 ? "还没有作品" : "没有找到匹配的作品"}
          description={
            tasks.length === 0
              ? "完成一次创作后，成片会显示在这里，可下载或复制为可编辑项目。"
              : "试试调整筛选条件或清空搜索关键词。"
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filteredTasks.map((task) => {
            const isExpanded = expandedTaskId === task.id;
            const thumb = task.scenes?.find((scene) => scene.imageUrl)?.imageUrl;
            const chip = statusChip(task.status);
            return (
              <article
                key={task.id}
                className="ui-card group flex flex-col overflow-hidden !p-0 transition-shadow hover:shadow-[var(--shadow-soft)]"
              >
                {/* Cover */}
                <div className="relative aspect-video w-full overflow-hidden bg-[var(--color-surface-0)]">
                  {thumb ? (
                    <img
                      src={thumb}
                      alt=""
                      className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
                    />
                  ) : task.videoUrl && task.status === "completed" ? (
                    <div className="flex h-full items-center justify-center gap-2 text-xs text-zinc-500">
                      <Film className="h-5 w-5" />
                      成片就绪
                    </div>
                  ) : (
                    <div className="flex h-full items-center justify-center text-xs text-zinc-600">
                      暂无预览
                    </div>
                  )}
                  <div className="absolute left-2 top-2 flex flex-wrap gap-1">
                    <span className={chip.className}>{chip.label}</span>
                  </div>
                  {task.status === "generating" && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/40">
                      <RefreshCw className="h-6 w-6 animate-spin text-amber-400" />
                    </div>
                  )}
                </div>

                {/* Body */}
                <div className="flex flex-1 flex-col gap-3 p-4">
                  <div className="min-w-0 space-y-1.5">
                    <h3 className="truncate text-sm font-semibold text-zinc-100" title={task.title}>
                      {task.title}
                    </h3>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption">
                      <span className="inline-flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {task.createdTime}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <Layers className="h-3 w-3" />
                        {task.sceneCount} 分镜
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      <span className="ui-chip !py-0">{tabTypeLabel(task.tabType)}</span>
                      {task.configSummary && (
                        <span className="ui-chip max-w-full truncate !py-0" title={task.configSummary}>
                          {task.configSummary}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="mt-auto flex flex-wrap items-center gap-1.5 border-t border-[var(--color-border-subtle)] pt-3">
                    {(task.status === "completed" || task.status === "failed") && (
                      <button
                        type="button"
                        onClick={() => onOpenWorkbench(task)}
                        className="ui-btn ui-btn-secondary ui-btn-sm"
                        title="从该历史创建一份新的可编辑项目，原记录保留"
                      >
                        复制为项目
                      </button>
                    )}
                    {task.status === "completed" && task.videoUrl && (
                      <a
                        href={task.videoUrl}
                        download
                        className="ui-btn ui-btn-primary ui-btn-sm"
                        title="下载成片视频"
                        onClick={() => {
                          addToast("开始下载高质量 MP4 成片", "success");
                        }}
                      >
                        <Download className="h-3.5 w-3.5" />
                        下载
                      </a>
                    )}
                    {task.status === "failed" && (
                      <button
                        type="button"
                        onClick={() => onResumeTask(task)}
                        className="ui-btn ui-btn-outline ui-btn-sm text-amber-300"
                        title="继续/重新生成"
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                        重试
                      </button>
                    )}
                    {task.status === "generating" && (
                      <button
                        type="button"
                        onClick={() => onCancelTask(task)}
                        className="ui-btn ui-btn-secondary ui-btn-sm"
                        aria-label={`取消任务 ${task.title}`}
                      >
                        <XCircle className="h-3.5 w-3.5" />
                        取消
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => toggleExpand(task.id)}
                      className="ui-btn ui-btn-ghost ui-btn-sm ml-auto"
                    >
                      {isExpanded ? "收起" : "详情"}
                      <ChevronDown
                        className={`h-3.5 w-3.5 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                      />
                    </button>
                    {task.status !== "generating" && (
                      <button
                        type="button"
                        onClick={() => setDeleteTarget(task)}
                        className="ui-btn ui-btn-ghost ui-btn-icon !h-8 !w-8 text-zinc-500 hover:text-rose-400"
                        title="删除任务"
                        aria-label={`删除任务 ${task.title}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                {/* Expanded details */}
                {isExpanded && (
                  <div className="space-y-4 border-t border-[var(--color-border-subtle)] bg-[var(--color-surface-0)]/60 p-4 text-xs animate-fade-in">
                    {task.errorMsg && (
                      <div className="rounded-[var(--radius-md)] border border-rose-500/20 bg-rose-500/10 p-2.5 font-mono text-rose-300">
                        <strong className="mb-0.5 block font-semibold">报错日志:</strong>
                        {task.errorMsg}
                      </div>
                    )}

                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                      <div className="space-y-1.5">
                        <span className="text-caption font-medium uppercase tracking-wider">运行参数</span>
                        <div className="ui-panel space-y-1 font-mono text-zinc-400">
                          <p>
                            <span className="text-zinc-500">成片时长:</span> {task.duration || "自动预估"}s
                          </p>
                          <p>
                            <span className="text-zinc-500">主渲染流:</span>{" "}
                            {task.configSummary?.split("/")[1]?.trim() || "未配置"}
                          </p>
                          <p>
                            <span className="text-zinc-500">音频配音:</span>{" "}
                            {task.configSummary?.split("/")[0]?.trim() || "Edge TTS"}
                          </p>
                          <p>
                            <span className="text-zinc-500">伴奏配轨:</span>{" "}
                            {task.configSummary?.split("/")[2]?.trim() || "无配乐"}
                          </p>
                        </div>
                      </div>

                      {task.status === "completed" && task.videoUrl && (
                        <div>
                          <span className="text-caption mb-1 block font-medium uppercase tracking-wider">
                            成片预览
                          </span>
                          <VideoPreview
                            src={task.videoUrl}
                            poster={task.scenes?.[0]?.imageUrl}
                          />
                        </div>
                      )}
                    </div>

                    {task.scenes && task.scenes.length > 0 && (
                      <div className="space-y-2 border-t border-[var(--color-border-subtle)] pt-3">
                        <span className="text-caption font-medium uppercase tracking-wider">
                          分镜 ({task.scenes.length})
                        </span>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          {task.scenes.map((scene, index) => (
                            <div
                              key={scene.id}
                              className="ui-panel flex flex-col space-y-2 !p-2.5"
                            >
                              <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] pb-1">
                                <span className="font-mono text-xs font-bold text-amber-500">
                                  #{index + 1}
                                </span>
                                <span
                                  className={
                                    scene.status === "completed"
                                      ? "ui-chip ui-chip-success !py-0"
                                      : "ui-chip ui-chip-danger !py-0"
                                  }
                                >
                                  {scene.status === "completed" ? "就绪" : "未完成"}
                                </span>
                              </div>
                              <p className="leading-relaxed text-zinc-300">{scene.ttsText}</p>
                              <p className="font-mono text-caption italic leading-relaxed">
                                {scene.visualPrompt}
                              </p>
                              {scene.imageUrl && (
                                <img
                                  src={scene.imageUrl}
                                  alt={`Scene ${scene.id}`}
                                  className="mt-1 h-24 w-full rounded-[var(--radius-sm)] border border-[var(--color-border-subtle)] object-cover"
                                  onError={(e) => {
                                    (e.target as HTMLImageElement).style.display = "none";
                                  }}
                                />
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
};
