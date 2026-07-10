import React, { useState } from "react";
import { Select } from "./Select";
import {
  History,
  Search,
  CheckCircle2,
  XCircle,
  Clock,
  Play,
  Download,
  Trash2,
  RefreshCw,
  Sliders,
  ChevronDown,
  ChevronUp,
  SlidersHorizontal,
} from "lucide-react";
import { Task } from "../types";
import { VideoPreview } from "./VideoPreview";

interface HistoryListProps {
  tasks: Task[];
  onDeleteTask: (id: string) => void;
  onResumeTask: (task: Task) => void;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

export const HistoryList: React.FC<HistoryListProps> = ({
  tasks,
  onDeleteTask,
  onResumeTask,
  addToast,
}) => {
  const [filter, setFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<"createdTime" | "sceneCount" | "title">("createdTime");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [expandedTaskId, setExpandedTaskId] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedTaskId(expandedTaskId === id ? null : id);
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
    <div className="space-y-4 max-w-5xl animate-fade-in">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-zinc-800 pb-4">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-lg font-semibold text-zinc-100 flex items-center gap-2 font-display">
            <History className="w-5 h-5 text-amber-500" />
            历史生产记录
          </h2>
          <p className="text-xs text-zinc-400">
            查看、管理与下载您所有的历史生成视频任务，支持快速配置重新生成。
          </p>
        </div>

        {/* Search */}
        <div className="relative max-w-xs w-full">
          <input
            type="text"
            placeholder="搜索任务名称或工作流..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[#101114] border border-zinc-800 rounded pl-8 pr-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 placeholder-zinc-500"
          />
          <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-2.5" />
        </div>
      </div>

      {/* Filters and Sorters */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#101114] border border-zinc-900 px-3 py-2 rounded-md">
        <div className="flex items-center gap-1">
          <span className="text-[10px] uppercase text-zinc-500 tracking-wider mr-2 font-mono">状态筛选:</span>
          {["all", "completed", "generating", "failed"].map((status) => (
            <button
              key={status}
              onClick={() => setFilter(status)}
              className={`px-2.5 py-1 text-xs rounded transition-colors ${
                filter === status
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/20 font-medium"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {status === "all" && "全部"}
              {status === "completed" && "已完成"}
              {status === "generating" && "生成中"}
              {status === "failed" && "生成失败"}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <SlidersHorizontal className="w-3.5 h-3.5 text-zinc-500" />
          <span className="text-[10px] uppercase text-zinc-500 tracking-wider font-mono">排序:</span>
          <Select
            value={sortBy}
            onChange={(e: any) => setSortBy(e.target.value)}
            className="bg-[#17181c] border border-zinc-800 text-xs rounded text-zinc-300 py-0.5 px-2 focus:outline-none"
          >
            <option value="createdTime">创建时间</option>
            <option value="sceneCount">分镜数量</option>
            <option value="title">任务标题</option>
          </Select>

          <button
            onClick={() => setSortOrder(sortOrder === "desc" ? "asc" : "desc")}
            className="p-1 hover:bg-zinc-850 rounded text-zinc-300"
          >
            {sortOrder === "desc" ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />}
          </button>
        </div>
      </div>

      {/* Task List */}
      <div className="space-y-3">
        {filteredTasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-12 bg-[#101114] rounded-lg border border-zinc-900 border-dashed">
            <History className="w-8 h-8 text-zinc-650 mb-3 animate-pulse" />
            <p className="text-xs text-zinc-400">没有找到匹配的历史任务。</p>
          </div>
        ) : (
          filteredTasks.map((task) => {
            const isExpanded = expandedTaskId === task.id;
            return (
              <div
                key={task.id}
                className="bg-[#101114] border border-zinc-900 rounded hover:border-zinc-850 transition-all duration-200"
              >
                <div className="p-3 flex items-center justify-between gap-4 flex-wrap md:flex-nowrap">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    {/* Icon indicator */}
                    <div className="flex-shrink-0">
                      {task.status === "completed" && (
                        <div className="w-8 h-8 rounded-full bg-emerald-500/10 flex items-center justify-center text-emerald-400 border border-emerald-500/20">
                          <CheckCircle2 className="w-4 h-4" />
                        </div>
                      )}
                      {task.status === "failed" && (
                        <div className="w-8 h-8 rounded-full bg-rose-500/10 flex items-center justify-center text-rose-400 border border-rose-500/20">
                          <XCircle className="w-4 h-4" />
                        </div>
                      )}
                      {task.status === "generating" && (
                        <div className="w-8 h-8 rounded-full bg-amber-500/10 flex items-center justify-center text-amber-400 border border-amber-500/20">
                          <RefreshCw className="w-4 h-4 animate-spin" />
                        </div>
                      )}
                    </div>

                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-medium text-zinc-200 truncate">{task.title}</h4>
                        <span className="text-[9px] uppercase font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                          {task.tabType === "quick-create" && "快捷创作"}
                          {task.tabType === "custom-media" && "自定义素材"}
                          {task.tabType === "digital-human" && "数字人口播"}
                          {task.tabType === "image-to-video" && "图生视频"}
                          {task.tabType === "action-transfer" && "动作迁移"}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-xs text-zinc-450 font-mono">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3 text-zinc-500" /> {task.createdTime}
                        </span>
                        <span>•</span>
                        <span>{task.sceneCount} 帧分镜</span>
                        <span>•</span>
                        <span className="text-zinc-500">{task.configSummary}</span>
                      </div>
                    </div>
                  </div>

                  {/* Actions right */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <button
                      onClick={() => toggleExpand(task.id)}
                      className="px-2.5 py-1 text-xs rounded border border-zinc-800 text-zinc-300 hover:bg-zinc-850 flex items-center gap-1 font-mono"
                    >
                      {isExpanded ? "收起参数" : "展开详情"}
                      <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isExpanded ? "rotate-180" : ""}`} />
                    </button>

                    {task.status === "completed" && task.videoUrl && (
                      <a
                        href={task.videoUrl}
                        download
                        className="p-1.5 bg-amber-500 text-black hover:bg-amber-400 rounded transition-colors"
                        title="下载成片视频"
                        onClick={(e) => {
                          addToast("开始下载高质量 MP4 成片", "success");
                        }}
                      >
                        <Download className="w-3.5 h-3.5" />
                      </a>
                    )}

                    {task.status === "failed" && (
                      <button
                        onClick={() => onResumeTask(task)}
                        className="px-2 py-1 bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20 rounded flex items-center gap-1 text-xs"
                        title="继续/重新生成"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        <span className="text-[10px]">重试</span>
                      </button>
                    )}

                    <button
                      onClick={() => onDeleteTask(task.id)}
                      className="p-1.5 hover:bg-rose-950/25 text-zinc-500 hover:text-rose-400 rounded border border-transparent hover:border-rose-950 transition-all"
                      title="删除任务"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {/* Expanded Details Panel */}
                {isExpanded && (
                  <div className="border-t border-zinc-900 bg-[#0c0d10] p-4 text-xs space-y-4 rounded-b">
                    {task.errorMsg && (
                      <div className="bg-rose-500/10 text-rose-400 p-2.5 rounded border border-rose-500/20 font-mono">
                        <strong className="font-semibold block mb-0.5">报错日志 Output:</strong>
                        {task.errorMsg}
                      </div>
                    )}

                    {/* Details lists */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-wider block">运行参数摘要:</span>
                        <div className="bg-[#121318] p-2.5 rounded border border-zinc-900 space-y-1 font-mono text-zinc-450">
                          <p><span className="text-zinc-500">成片时长:</span> {task.duration || "自动预估"}s</p>
                          <p><span className="text-zinc-500">主渲染流:</span> {task.configSummary?.split("/")[1]?.trim() || "未配置"}</p>
                          <p><span className="text-zinc-500">音频配音:</span> {task.configSummary?.split("/")[0]?.trim() || "Edge TTS"}</p>
                          <p><span className="text-zinc-500">伴奏配轨:</span> {task.configSummary?.split("/")[2]?.trim() || "无配乐"}</p>
                        </div>
                      </div>

                      {task.status === "completed" && task.videoUrl && (
                        <div>
                          <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-wider block mb-1">高清成片预览:</span>
                          <VideoPreview
                            src={task.videoUrl}
                            poster={task.scenes?.[0]?.imageUrl}
                          />
                        </div>
                      )}
                    </div>

                    {/* Scene breakdown if present */}
                    {task.scenes && task.scenes.length > 0 && (
                      <div className="space-y-2 pt-2 border-t border-zinc-900">
                        <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-wider block">分镜脚本切片 ({task.scenes.length}):</span>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                          {task.scenes.map((scene, index) => (
                            <div key={scene.id} className="bg-[#121318] rounded border border-zinc-850 p-2.5 flex flex-col justify-between space-y-2">
                              <div>
                                <div className="flex justify-between items-center mb-1 pb-1 border-b border-zinc-800/60">
                                  <span className="text-amber-500 font-mono font-bold">#SCENE 0{index + 1}</span>
                                  <span className={`text-[9px] font-mono px-1 rounded ${
                                    scene.status === "completed" ? "bg-emerald-500/10 text-emerald-400" : "bg-rose-500/10 text-rose-400"
                                  }`}>
                                    {scene.status === "completed" ? "绘制成功" : "未绘制"}
                                  </span>
                                </div>
                                <p className="text-zinc-300 mb-1 leading-relaxed">{scene.ttsText}</p>
                                <p className="text-[10px] text-zinc-500 italic leading-relaxed font-mono">
                                  Prompt: {scene.visualPrompt}
                                </p>
                              </div>
                              {scene.imageUrl && (
                                <img
                                  src={scene.imageUrl}
                                  alt={`Scene ${scene.id}`}
                                  className="w-full h-24 object-cover rounded border border-zinc-800/80 mt-2"
                                  onError={(e) => {
                                    (e.target as any).style.display = 'none';
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
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
