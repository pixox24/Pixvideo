import React, { useState, useEffect, useRef } from "react";
import { Select } from "./components/Select";
import {
  Sparkles,
  History,
  Settings as SettingsIcon,
  Cpu,
  Tv,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Sliders,
  Play,
  Activity,
  Download,
  Menu,
  PanelRightOpen,
  PanelRightClose,
  X,
} from "lucide-react";
import { ActiveTab, Preset, QuickCreateInput, Task, SystemSettings } from "./types";
import { Toast, ToastMessage } from "./components/Toast";
import { QuickCreate } from "./components/QuickCreate";
import { HistoryList } from "./components/HistoryList";
import { SystemSettingsTab } from "./components/SystemSettingsTab";
import { ConsolePanel } from "./components/ConsolePanel";
import { ProjectWorkbench } from "./components/ProjectWorkbench";
import {
  buildConfigPayload,
  cancelTask,
  deleteHistoryTask,
  EMPTY_WORKBENCH_RESOURCES,
  fetchHistoryTasks,
  fetchQuickCreateResources,
  fetchTask,
  formatApiErrorValue,
  mapApiTask,
  mapBackendConfigToSettings,
  mapHistoryTask,
  optimisticTaskFromInput,
  resumeHistoryTask,
  submitVideoTask,
} from "./lib/api";
import { createProject } from "./lib/workbenchApi";
import { createProjectFromHistory } from "./lib/workbenchApi";

const PENDING_TASK_ID_PREFIX = "pending-";

const isPendingTaskId = (taskId: string) => taskId.startsWith(PENDING_TASK_ID_PREFIX);

export default function App() {
  // Global States
  const [activeTab, setActiveTab] = useState<ActiveTab>("quick-create");
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [activePreset, setActivePreset] = useState<Preset | null>(null);
  const [defaultPresetId, setDefaultPresetId] = useState<string | null>(null);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [resources, setResources] = useState(EMPTY_WORKBENCH_RESOURCES);
  const [serviceStatus, setServiceStatus] = useState({
    llm: false,
    image_generation: false,
    comfyui: false,
    runninghub: false,
    bizyair: false,
    minimax: false,
  });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [consoleOpen, setConsoleOpen] = useState(() =>
    typeof window !== "undefined" ? window.innerWidth >= 1024 : true,
  );
  const mainScrollRef = useRef<HTMLDivElement | null>(null);
  const pendingCancellationIdsRef = useRef(new Set<string>());

  useEffect(() => {
    mainScrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
    setSidebarOpen(false);
  }, [activeTab]);

  // Default system settings state
  const [settings, setSettings] = useState<SystemSettings>({
    llm: {
      provider: "gemini",
      apiKey: "",
      baseUrl: "",
      model: "gemini-3.5-flash"
    },
    imageGeneration: {
      apiKey: "",
      baseUrl: "https://img-cn.65535.space/v1",
      model: "gpt-image-2"
    },
    comfy: {
      url: "http://127.0.0.1:8188",
      apiKey: ""
    },
    runninghub: {
      apiKey: "",
      concurrency: 3,
      instanceType: "24G"
    },
    bizyairKey: "",
    minimaxKey: ""
  });

  // Toaster helper
  const addToast = (text: unknown, type: "success" | "error" | "info" = "info") => {
    const id = `toast-${Date.now()}`;
    const safeText = formatApiErrorValue(text) || "未知错误";
    setToasts((prev) => [...prev, { id, text: safeText, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const refreshHistory = async () => {
    const history = await fetchHistoryTasks();
    const persistedTasks = history.map(mapHistoryTask);
    setTasks((prev) => {
      const persistedIds = new Set(persistedTasks.map((task) => task.id));
      const localOnlyTasks = prev.filter(
        (task) => isPendingTaskId(task.id) || (task.status === "generating" && !persistedIds.has(task.id)),
      );
      return [
        ...localOnlyTasks,
        ...persistedTasks,
      ];
    });
  };

  const refreshResources = async () => {
    setResources(await fetchQuickCreateResources());
  };

  const applyPresetResponse = (data: any) => {
    const loadedPresets = data.presets || [];
    setPresets(loadedPresets);
    setDefaultPresetId(data.defaultPresetId || null);
    if (data.preset) {
      setActivePreset(data.preset);
    } else if (loadedPresets[0]) {
      setActivePreset(loadedPresets[0]);
    }
  };

  // Load persisted backend state
  useEffect(() => {
    const loadBackendState = async () => {
      try {
        const [presetsRes, configRes] = await Promise.all([
          fetch("/api/presets"),
          fetch("/api/config"),
        ]);

        if (presetsRes.ok) {
          const data = await presetsRes.json();
          if (data.success) {
            applyPresetResponse(data);
          }
        }

        if (configRes.ok) {
          const data = await configRes.json();
          setSettings((current) => mapBackendConfigToSettings(data, current));
          if (data.service_status) setServiceStatus(data.service_status);
        }
      } catch (err) {
        console.warn("Could not load backend configuration.", err);
      }

      try {
        await refreshResources();
      } catch (err) {
        console.warn("Could not load backend resources.", err);
      }

      try {
        await refreshHistory();
      } catch (err) {
        console.warn("Could not load backend history.", err);
      }
    };

    loadBackendState();
  }, []);

  // Preset handlers
  const handleCreatePreset = async (presetInput: Omit<Preset, "id">) => {
    try {
      const res = await fetch("/api/presets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(presetInput),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        applyPresetResponse(data);
        addToast(`已另存为工作台预设: ${data.preset.name}`, "success");
      } else {
        addToast(data.detail || data.error || "保存预设失败", "error");
      }
    } catch (err) {
      addToast("保存失败：无法连接后端配置服务。", "error");
    }
  };

  const handleUpdatePreset = async (presetId: string, presetInput: Preset) => {
    try {
      const res = await fetch(`/api/presets/${presetId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(presetInput),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        applyPresetResponse(data);
        addToast(`已覆盖当前预设: ${data.preset.name}`, "success");
      } else {
        addToast(data.detail || data.error || "覆盖预设失败", "error");
      }
    } catch (err) {
      addToast("覆盖失败：无法连接后端配置服务。", "error");
    }
  };

  const handleDeletePreset = async (presetId: string) => {
    try {
      const res = await fetch(`/api/presets/${presetId}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (res.ok && data.success) {
        applyPresetResponse(data);
        addToast("预设已删除。", "success");
      } else {
        addToast(data.detail || data.error || "删除预设失败", "error");
      }
    } catch (err) {
      addToast("删除失败：无法连接后端配置服务。", "error");
    }
  };

  const handleSetDefaultPreset = async (presetId: string) => {
    try {
      const res = await fetch(`/api/presets/${presetId}/default`, {
        method: "PUT",
      });
      const data = await res.json();
      if (res.ok && data.success) {
        applyPresetResponse(data);
        addToast(`已设为默认预设: ${data.preset.name}`, "success");
      } else {
        addToast(data.detail || data.error || "设置默认预设失败", "error");
      }
    } catch (err) {
      addToast("设置失败：无法连接后端配置服务。", "error");
    }
  };

  const handleSavePromptPrefix = async (promptPrefix: string) => {
    const response = await fetch("/api/prompt-prefix", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ promptPrefix, presetId: activePreset?.id }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(
        formatApiErrorValue(data.detail) ||
        formatApiErrorValue(data.error) ||
        "保存提示词失败",
      );
    }

    const savedPreset = data.preset;
    if (savedPreset) {
      setPresets((currentPresets) =>
        currentPresets.map((preset) =>
          preset.id === savedPreset.id
            ? savedPreset
            : preset.id === activePreset?.id
            ? { ...preset, promptPrefix: savedPreset.promptPrefix }
            : preset
        )
      );
      setActivePreset((currentPreset) =>
        currentPreset?.id === savedPreset.id
          ? savedPreset
          : currentPreset
          ? { ...currentPreset, promptPrefix: savedPreset.promptPrefix }
          : savedPreset
      );
    }
    addToast("提示词前缀已保存，下次打开会自动使用。", "success");
    return data.promptPrefix;
  };

  // Delete task handler
  const handleDeleteTask = async (id: string) => {
    if (isPendingTaskId(id)) {
      setTasks((prev) => prev.filter((t) => t.id !== id));
      setActiveTask((prev) => (prev?.id === id ? null : prev));
      addToast("本地临时任务已移除，后端尚未创建对应历史记录。", "info");
      return;
    }

    try {
      await deleteHistoryTask(id);
      addToast("任务已成功从后端历史记录删除", "info");
    } catch (err: any) {
      addToast(err.message || "后端历史中未找到该任务，已从当前列表移除。", "info");
    }

    setTasks((prev) => prev.filter((t) => t.id !== id));
    setActiveTask((prev) => (prev?.id === id ? null : prev));
  };

  const handleCancelTask = async (task: Task) => {
    if (isPendingTaskId(task.id)) {
      pendingCancellationIdsRef.current.add(task.id);
      const cancellingTask = { ...task, currentStep: "等待后端确认后取消" };
      setTasks((prev) => prev.map((item) => (item.id === task.id ? cancellingTask : item)));
      setActiveTask((prev) => (prev?.id === task.id ? cancellingTask : prev));
      addToast("已记录取消请求，后端任务创建后将立即取消。", "info");
      return;
    }

    try {
      await cancelTask(task.id);
      const cancelledTask: Task = {
        ...task,
        status: "cancelled",
        currentStep: "任务已取消",
      };
      setTasks((prev) => prev.map((item) => (item.id === task.id ? cancelledTask : item)));
      setActiveTask((prev) => (prev?.id === task.id ? cancelledTask : prev));
      addToast(`任务已取消: ${task.title}`, "info");
    } catch (err: any) {
      addToast(err.message || "取消任务失败。", "error");
      return;
    }

    try {
      await refreshHistory();
    } catch (err) {
      console.warn("Task was cancelled, but history refresh failed.", err);
    }
  };

  const pollBackendTask = async (taskId: string, fallback: Task) => {
    if (isPendingTaskId(taskId)) {
      const failedTask: Task = {
        ...fallback,
        status: "failed",
        currentStep: "任务尚未提交到后端",
        errorMsg: "本地临时任务尚未拿到后端任务 ID，无法读取生成状态。",
      };
      setTasks((prev) => prev.map((task) => (task.id === taskId ? failedTask : task)));
      setActiveTask((prev) => (prev?.id === taskId ? failedTask : prev));
      addToast("任务还没有后端 ID，已停止状态轮询。", "error");
      return;
    }

    try {
      const apiTask = await fetchTask(taskId);
      const mappedTask = mapApiTask(apiTask, fallback);

      setTasks((prev) =>
        prev.map((task) => (task.id === taskId ? mappedTask : task))
      );
      setActiveTask((prev) => (prev?.id === taskId ? mappedTask : prev));

      if (mappedTask.status === "completed") {
        addToast("视频生成成功！成片已经渲染就绪。", "success");
        await refreshHistory();
        return;
      }

      if (mappedTask.status === "failed") {
        addToast(mappedTask.errorMsg || "视频生成失败，请查看控制台错误信息。", "error");
        await refreshHistory();
        return;
      }

      if (mappedTask.status === "cancelled") {
        addToast("视频生成任务已取消。", "info");
        await refreshHistory();
        return;
      }

      window.setTimeout(() => pollBackendTask(taskId, mappedTask), 2000);
    } catch (err: any) {
      const failedTask: Task = {
        ...fallback,
        id: taskId,
        status: "failed",
        progress: fallback.progress,
        currentStep: "无法读取后端任务状态",
        errorMsg: err.message,
      };
      setTasks((prev) => prev.map((task) => (task.id === taskId ? failedTask : task)));
      setActiveTask((prev) => (prev?.id === taskId ? failedTask : prev));
      addToast(err.message || "任务状态轮询失败。", "error");
    }
  };

  // Launch new video generation task
  const handleGenerateTask = async (taskInput: any) => {
    const tempTaskId = `${PENDING_TASK_ID_PREFIX}${crypto.randomUUID()}`;
    const optimisticTask = optimisticTaskFromInput(taskInput, tempTaskId);

    setTasks((prev) => [optimisticTask, ...prev]);
    setActiveTask(optimisticTask);
    addToast(`开始提交视频渲染任务: ${taskInput.title}`, "info");

    try {
      const response = await submitVideoTask(taskInput);
      const backendTask = { ...optimisticTask, id: response.task_id };
      setTasks((prev) =>
        prev.map((task) => (task.id === tempTaskId ? backendTask : task))
      );
      setActiveTask(backendTask);
      addToast(`后端任务已创建: ${response.task_id}`, "success");

      if (pendingCancellationIdsRef.current.delete(tempTaskId)) {
        try {
          await cancelTask(response.task_id);
          const cancelledTask: Task = {
            ...backendTask,
            status: "cancelled",
            currentStep: "任务已取消",
          };
          setTasks((prev) =>
            prev.map((task) => (task.id === response.task_id ? cancelledTask : task))
          );
          setActiveTask(cancelledTask);
          addToast(`任务已取消: ${taskInput.title}`, "info");
          try {
            await refreshHistory();
          } catch (err) {
            console.warn("Task was cancelled, but history refresh failed.", err);
          }
          return null;
        } catch (err: any) {
          addToast(err.message || "自动取消失败，任务将继续运行。", "error");
        }
      }

      await pollBackendTask(response.task_id, backendTask);
      return response.task_id;
    } catch (err: any) {
      pendingCancellationIdsRef.current.delete(tempTaskId);
      const failedTask: Task = {
        ...optimisticTask,
        status: "failed",
        currentStep: "任务提交失败",
        errorMsg: err.message,
      };
      setTasks((prev) =>
        prev.map((task) => (task.id === tempTaskId ? failedTask : task))
      );
      setActiveTask(failedTask);
      addToast(err.message || "任务提交失败，请检查后端服务。", "error");
      return null;
    }
  };

  // Resume or Retry failed task
  const handleResumeTask = async (task: Task) => {
    if (isPendingTaskId(task.id)) {
      const failedTask = {
        ...task,
        status: "failed" as const,
        currentStep: "任务尚未提交到后端",
        errorMsg: "该任务只存在于本地，后端没有可恢复的历史记录。请重新点击生成视频。",
      };
      setTasks((prev) => prev.map((item) => (item.id === task.id ? failedTask : item)));
      setActiveTask(failedTask);
      addToast("这个任务还没有后端 ID，无法从历史记录恢复。请重新生成。", "error");
      return;
    }

    const updatedTask = {
      ...task,
      status: "generating" as const,
      progress: 0,
      currentStep: "后端正在恢复历史任务...",
    };

    setTasks((prev) => prev.map((item) => (item.id === task.id ? updatedTask : item)));
    setActiveTask(updatedTask);
    addToast(`正在恢复生成: ${task.title}`, "info");

    try {
      await resumeHistoryTask(task.id);
      addToast("历史任务恢复完成。", "success");
      await refreshHistory();
    } catch (err: any) {
      const failedTask = {
        ...task,
        status: "failed" as const,
        errorMsg: err.message || "恢复任务失败",
      };
      setTasks((prev) => prev.map((item) => (item.id === task.id ? failedTask : item)));
      setActiveTask(failedTask);
      addToast(err.message || "恢复任务失败。", "error");
    }
  };

  const handleSaveSettings = async (nextSettings: SystemSettings) => {
    try {
      const response = await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildConfigPayload(nextSettings)),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(
          formatApiErrorValue(data.detail) ||
          formatApiErrorValue(data.error) ||
          "保存配置失败",
        );
      }
      setSettings((current) => mapBackendConfigToSettings(data, { ...current, ...nextSettings }));
      if (data.service_status) setServiceStatus(data.service_status);
      addToast("系统连接配置已保存到后端配置文件。", "success");
    } catch (err: any) {
      addToast(err.message || "保存系统配置失败。", "error");
    }
  };

  const handleCreateProject = async (input: QuickCreateInput) => {
    try {
      const project = await createProject(input);
      setActiveProjectId(project.projectId);
      setActiveTab("project-workbench");
      addToast("项目草稿已创建，正在打开剪辑工作台。", "success");
    } catch (error) {
      addToast(error, "error");
      throw error;
    }
  };

  const handleOpenHistoryWorkbench = async (task: Task) => {
    try {
      const project = await createProjectFromHistory(task.id);
      setActiveProjectId(project.projectId);
      setActiveTab("project-workbench");
      addToast("历史任务已打开为可编辑项目。", "success");
    } catch (error) {
      addToast(error, "error");
    }
  };

  // Sidebar connectivity widgets indicator
  const hasLlmKey = serviceStatus.llm || settings.llm.apiKey !== "";
  const hasComfyUrl = serviceStatus.comfyui || settings.comfy.url !== "";
  const hasRunningHub = serviceStatus.runninghub || settings.runninghub.apiKey !== "";
  const hasImageGeneration = serviceStatus.image_generation || settings.imageGeneration.apiKey !== "";
  const hasMiniMax = serviceStatus.minimax || settings.minimaxKey !== "";
  const latestCompletedQuickCreateTaskId = tasks.find(
    (task) => task.tabType === "quick-create" && task.status === "completed" && !isPendingTaskId(task.id),
  )?.id || null;

  return (
    <div className="flex h-screen w-full bg-[#07080a] text-zinc-100 overflow-hidden font-sans relative antialiased">
      {/* Toast Notification Container */}
      <Toast toasts={toasts} onClose={removeToast} />

      {sidebarOpen && (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-label="关闭导航遮罩"
        />
      )}

      {/* 1. LEFT SIDEBAR NAVIGATION */}
      <aside className={`fixed inset-y-0 left-0 z-40 w-64 bg-[#101114] border-r border-zinc-900 flex flex-col justify-between flex-shrink-0 h-full transition-transform lg:static lg:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex flex-col min-h-0 flex-1">
          {/* Brand header */}
          <div className="p-4 border-b border-zinc-900 flex items-center gap-2.5 bg-[#0c0d10]">
            <div className="w-7 h-7 rounded bg-amber-500 flex items-center justify-center shadow-lg shadow-amber-500/10">
              <Tv className="w-4 h-4 text-black stroke-[2.5]" />
            </div>
            <button
              type="button"
              onClick={() => setSidebarOpen(false)}
              className="ml-auto p-1 text-zinc-400 lg:hidden"
              aria-label="关闭导航"
            >
              <X className="w-4 h-4" />
            </button>
            <div>
              <h1 className="text-sm font-black font-display text-zinc-100 tracking-wider">
                PIXELLE-VIDEO
              </h1>
              <span className="text-[9px] text-amber-500 font-bold uppercase tracking-widest block mt-0.5">
                AI 视频工作台
              </span>
            </div>
          </div>

          {/* Navigation Items */}
          <nav className="p-3 space-y-1 overflow-y-auto flex-1">
            <span className="text-[9px] font-bold text-zinc-650 tracking-wider uppercase block px-2.5 mb-1.5 font-mono">
              创造引擎 / Workspace
            </span>
            
            <button
              onClick={() => setActiveTab("quick-create")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded transition-all ${
                activeTab === "quick-create"
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/15"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-[#15161c]"
              }`}
            >
              <Sparkles className="w-4 h-4" />
              <span>快捷创作 Quick Create</span>
            </button>

            <div className="pt-4 pb-1">
              <span className="text-[9px] font-bold text-zinc-650 tracking-wider uppercase block px-2.5 mb-1.5 font-mono">
                资产管理 / Logs
              </span>
            </div>

            <button
              onClick={() => activeProjectId && setActiveTab("project-workbench")}
              disabled={!activeProjectId}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded transition-all ${
                activeTab === "project-workbench" ? "bg-amber-500/10 text-amber-400 border border-amber-500/15" : "text-zinc-400 hover:text-zinc-200 hover:bg-[#15161c] disabled:opacity-40"
              }`}
            >
              <Tv className="w-4 h-4" />
              <span>项目工作台 Project</span>
            </button>

            <button
              onClick={() => setActiveTab("history")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded transition-all ${
                activeTab === "history"
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/15"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-[#15161c]"
              }`}
            >
              <History className="w-4 h-4" />
              <span>历史记录 History</span>
            </button>

            <button
              onClick={() => setActiveTab("settings")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded transition-all ${
                activeTab === "settings"
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/15"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-[#15161c]"
              }`}
            >
              <SettingsIcon className="w-4 h-4" />
              <span>系统设置 Settings</span>
            </button>
          </nav>
        </div>

        {/* Bottom system connectivity states */}
        <div className="p-3 border-t border-zinc-900 bg-[#0c0d10] space-y-2.5">
          <span className="text-[9px] font-bold text-zinc-500 tracking-wider uppercase block font-mono">
            物理算力网络节点 / Status
          </span>

          <div className="space-y-1.5 text-[11px] font-mono">
            {/* LLM */}
            <div className="flex items-center justify-between">
              <span className="text-zinc-500 flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-zinc-600" />
                {settings.llm.provider.toUpperCase()} · {settings.llm.model}
              </span>
              <span className={`flex items-center gap-1 text-[10px] font-semibold px-1 rounded ${serviceStatus.llm ? "text-emerald-400 bg-emerald-500/5" : "text-amber-400 bg-amber-500/5"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${serviceStatus.llm ? "bg-emerald-500" : "bg-amber-500"}`}></span>
                {serviceStatus.llm ? "已连接" : "未检测"}
              </span>
            </div>

            {/* Image Generation */}
            <div className="flex items-center justify-between">
              <span className="text-zinc-500 flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-zinc-600" />
                Image API
              </span>
              <span className={`flex items-center gap-1 text-[10px] px-1 rounded font-semibold ${
                hasImageGeneration ? "text-emerald-400 bg-emerald-500/5" : "text-amber-400 bg-amber-500/5"
              }`}>
                <span className={`h-1.5 w-1.5 rounded-full ${hasImageGeneration ? "bg-emerald-500" : "bg-amber-500"}`}></span>
                {hasImageGeneration ? "已就绪" : "待配置"}
              </span>
            </div>

            {/* ComfyUI */}
            <div className="flex items-center justify-between">
              <span className="text-zinc-500 flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-zinc-600" />
                ComfyUI Local
              </span>
              <span className="flex items-center gap-1 text-[10px] text-zinc-500 bg-zinc-800 px-1 rounded">
                <span className="h-1.5 w-1.5 rounded-full bg-zinc-600"></span>
                待监听
              </span>
            </div>

            {/* RunningHub */}
            <div className="flex items-center justify-between">
              <span className="text-zinc-500 flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-zinc-600" />
                RunningHub
              </span>
              <span className={`flex items-center gap-1 text-[10px] px-1 rounded font-semibold ${
                hasRunningHub ? "text-emerald-400 bg-emerald-500/5" : "text-amber-400 bg-amber-500/5"
              }`}>
                <span className={`h-1.5 w-1.5 rounded-full ${hasRunningHub ? "bg-emerald-500" : "bg-amber-500"}`}></span>
                {hasRunningHub ? "已就绪" : "待配置"}
              </span>
            </div>

            {/* BizyAir */}
            <div className="flex items-center justify-between">
              <span className="text-zinc-500 flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-zinc-600" />
                BizyAir Cloud
              </span>
              <span className={`flex items-center gap-1 text-[10px] px-1 rounded font-semibold ${serviceStatus.bizyair ? "text-emerald-400 bg-emerald-500/5" : "text-amber-400 bg-amber-500/5"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${serviceStatus.bizyair ? "bg-emerald-500" : "bg-amber-500"}`}></span>
                {serviceStatus.bizyair ? "已连接" : "未检测"}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-zinc-500 flex items-center gap-1">
                <Cpu className="w-3.5 h-3.5 text-zinc-600" />
                MiniMax TTS
              </span>
              <span className={`flex items-center gap-1 text-[10px] px-1 rounded font-semibold ${serviceStatus.minimax ? "text-emerald-400 bg-emerald-500/5" : hasMiniMax ? "text-amber-400 bg-amber-500/5" : "text-zinc-500 bg-zinc-800"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${serviceStatus.minimax ? "bg-emerald-500" : hasMiniMax ? "bg-amber-500" : "bg-zinc-600"}`}></span>
                {serviceStatus.minimax ? "已连接" : hasMiniMax ? "已配置" : "未配置"}
              </span>
            </div>
          </div>

          {/* Quick presets picker summary */}
          {presets.length > 0 && (
            <div className="pt-2 border-t border-zinc-900/60">
              <label className="block text-[9px] text-zinc-650 font-mono uppercase mb-1">
                已载入云端预设:
              </label>
              <Select
                onChange={(e) => {
                  const p = presets.find((pr) => pr.id === e.target.value);
                  if (p) setActivePreset(p);
                }}
                className="w-full bg-[#15161c] border border-zinc-850 text-[10px] text-zinc-400 rounded py-1 px-2 focus:outline-none focus:border-amber-500/40"
              >
                <option value="">-- 点击快速应用预设 --</option>
                {presets.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </Select>
            </div>
          )}
        </div>
      </aside>

      <div className="flex-1 min-w-0 h-full flex justify-center">
        <div className="w-full max-w-[1680px] h-full flex min-w-0">
      {/* 2. CENTER WORKSPACE WITH HEADER & BODY */}
      <main className="flex-1 flex flex-col min-w-0 h-full">
        {/* TOP STATUS BAR */}
        <header className="h-12 bg-[#101114] border-b border-zinc-900 px-4 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="p-1.5 text-zinc-400 hover:text-zinc-100 lg:hidden"
              aria-label="打开导航"
            >
              <Menu className="w-4 h-4" />
            </button>
            <span className="text-sm font-semibold text-zinc-200 font-display">
              {activeTab === "quick-create" && "快捷创作工作室 / Quick Create Studio"}
              {activeTab === "history" && "生产日志与历史项目 / Production History"}
              {activeTab === "settings" && "系统算力网络配置 / Server Configurations"}
            </span>
          </div>

          <div className="flex items-center gap-3">
            {/* Quick monitor indicators */}
            <div className="hidden sm:flex items-center gap-2 text-[10px] font-mono text-zinc-500 bg-zinc-900/80 px-2.5 py-1 rounded border border-zinc-850">
              <span className={`flex items-center gap-1 ${serviceStatus.llm ? "text-emerald-400" : "text-amber-400"}`}>
                <span className={`h-1 w-1 rounded-full ${serviceStatus.llm ? "bg-emerald-500" : "bg-amber-500"}`}></span>
                {settings.llm.provider} {serviceStatus.llm ? "已连接" : "未检测"}
              </span>
              <span className="text-zinc-700">|</span>
              <span className={`flex items-center gap-1 ${serviceStatus.bizyair ? "text-emerald-400" : "text-amber-400"}`}>
                <span className={`h-1 w-1 rounded-full ${serviceStatus.bizyair ? "bg-emerald-500" : "bg-amber-500"}`}></span>
                BizyAir {serviceStatus.bizyair ? "已连接" : "未检测"}
              </span>
            </div>

            <button
              type="button"
              onClick={() => setConsoleOpen((open) => !open)}
              className="p-1.5 bg-[#17181c] border border-zinc-800 rounded text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1 text-xs"
              aria-label={consoleOpen ? "关闭任务面板" : "打开任务面板"}
            >
              {consoleOpen ? <PanelRightClose className="w-3.5 h-3.5" /> : <PanelRightOpen className="w-3.5 h-3.5" />}
              <span className="hidden sm:inline text-[10px]">任务</span>
            </button>
          </div>
        </header>

        {/* MAIN BODY AREA */}
        <div ref={mainScrollRef} className="flex-1 overflow-y-auto p-3 sm:p-5 xl:p-6">
          {activeTab === "quick-create" && (
            <QuickCreate
              onGenerateTask={handleGenerateTask}
              latestCompletedTaskId={latestCompletedQuickCreateTaskId}
              presets={presets}
              activePreset={activePreset}
              defaultPresetId={defaultPresetId}
              onSelectPreset={setActivePreset}
              onCreatePreset={handleCreatePreset}
              onUpdatePreset={handleUpdatePreset}
              onDeletePreset={handleDeletePreset}
              onSetDefaultPreset={handleSetDefaultPreset}
              onSavePromptPrefix={handleSavePromptPrefix}
              onRefreshResources={refreshResources}
              resources={resources}
              addToast={addToast}
              onCreateProject={handleCreateProject}
            />
          )}

          {activeTab === "project-workbench" && activeProjectId && <ProjectWorkbench projectId={activeProjectId} addToast={addToast} />}

          {activeTab === "history" && (
            <HistoryList
              tasks={tasks}
              onDeleteTask={handleDeleteTask}
              onResumeTask={handleResumeTask}
              onCancelTask={handleCancelTask}
              onOpenWorkbench={handleOpenHistoryWorkbench}
              addToast={addToast}
            />
          )}

          {activeTab === "settings" && (
            <SystemSettingsTab
              settings={settings}
              onUpdateSettings={setSettings}
              onSaveSettings={handleSaveSettings}
              addToast={addToast}
            />
          )}
        </div>
      </main>

      {/* 3. RIGHT RUNNING PANEL (THE CONSOLE) */}
      {consoleOpen && <button type="button" className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setConsoleOpen(false)} aria-label="关闭任务面板遮罩" />}
      <ConsolePanel
        activeTask={activeTask}
        recentTasks={tasks}
        isOpen={consoleOpen}
        onClose={() => setConsoleOpen(false)}
        onCancelTask={handleCancelTask}
        onSelectTask={(t) => {
          // Open details by switching tab to History or showing popup
          setActiveTab("history");
          addToast(`正在聚焦查看任务: ${t.title}`, "info");
        }}
        addToast={addToast}
      />
        </div>
      </div>
    </div>
  );
}
