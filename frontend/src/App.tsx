import React, { useState, useEffect } from "react";
import {
  Sparkles,
  Layers,
  User,
  History,
  Settings as SettingsIcon,
  Cpu,
  Tv,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Sliders,
  Play,
  Languages,
  Activity,
  Workflow,
  Download,
} from "lucide-react";
import { ActiveTab, Preset, Task, SystemSettings } from "./types";
import { Toast, ToastMessage } from "./components/Toast";
import { QuickCreate } from "./components/QuickCreate";
import { CustomMedia } from "./components/CustomMedia";
import { DigitalHuman } from "./components/DigitalHuman";
import { ImageToVideo } from "./components/ImageToVideo";
import { ActionTransfer } from "./components/ActionTransfer";
import { HistoryList } from "./components/HistoryList";
import { SystemSettingsTab } from "./components/SystemSettingsTab";
import { ConsolePanel } from "./components/ConsolePanel";
import {
  buildConfigPayload,
  deleteHistoryTask,
  EMPTY_WORKBENCH_RESOURCES,
  fetchHistoryTasks,
  fetchQuickCreateResources,
  fetchTask,
  mapApiTask,
  mapBackendConfigToSettings,
  mapHistoryTask,
  optimisticTaskFromInput,
  resumeHistoryTask,
  submitVideoTask,
} from "./lib/api";

export default function App() {
  // Global States
  const [activeTab, setActiveTab] = useState<ActiveTab>("quick-create");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [activePreset, setActivePreset] = useState<Preset | null>(null);
  const [lang, setLang] = useState<"zh" | "en">("zh");
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [resources, setResources] = useState(EMPTY_WORKBENCH_RESOURCES);
  const [serviceStatus, setServiceStatus] = useState({
    llm: false,
    comfyui: false,
    runninghub: false,
    bizyair: false,
    minimax: false,
  });

  // Default system settings state
  const [settings, setSettings] = useState<SystemSettings>({
    llm: {
      provider: "gemini",
      apiKey: "",
      baseUrl: "",
      model: "gemini-3.5-flash"
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
  const addToast = (text: string, type: "success" | "error" | "info" = "info") => {
    const id = `toast-${Date.now()}`;
    setToasts((prev) => [...prev, { id, text, type }]);
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
      const runningTasks = prev.filter((task) => task.status === "generating");
      const runningIds = new Set(runningTasks.map((task) => task.id));
      return [
        ...runningTasks,
        ...persistedTasks.filter((task) => !runningIds.has(task.id)),
      ];
    });
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
          if (data.success) setPresets(data.presets || []);
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
        setResources(await fetchQuickCreateResources());
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

  // Save preset handler
  const handleSavePreset = async (presetInput: Omit<Preset, "id">) => {
    try {
      const res = await fetch("/api/presets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(presetInput),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setPresets(data.presets || [data.preset]);
        addToast(`成功保存预设并同步至云端: ${data.preset.name}`, "success");
      } else {
        addToast(data.error || "保存预设失败", "error");
      }
    } catch (err) {
      addToast("保存失败：无法连接后端配置服务。", "error");
    }
  };

  // Delete task handler
  const handleDeleteTask = async (id: string) => {
    try {
      await deleteHistoryTask(id);
      addToast("任务已成功从后端历史记录删除", "info");
    } catch (err: any) {
      addToast(err.message || "后端历史中未找到该任务，已从当前列表移除。", "info");
    }

    setTasks((prev) => prev.filter((t) => t.id !== id));
    if (activeTask && activeTask.id === id) {
      setActiveTask(null);
    }
  };

  const pollBackendTask = async (taskId: string, fallback: Task) => {
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
    const tempTaskId = `pending-${Date.now()}`;
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
      await pollBackendTask(response.task_id, backendTask);
    } catch (err: any) {
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
    }
  };

  // Resume or Retry failed task
  const handleResumeTask = async (task: Task) => {
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
        throw new Error(data.detail || data.error || "保存配置失败");
      }
      setSettings((current) => mapBackendConfigToSettings(data, { ...current, ...nextSettings }));
      if (data.service_status) setServiceStatus(data.service_status);
      addToast("系统连接配置已保存到后端配置文件。", "success");
    } catch (err: any) {
      addToast(err.message || "保存系统配置失败。", "error");
    }
  };

  // Sidebar connectivity widgets indicator
  const hasLlmKey = serviceStatus.llm || settings.llm.apiKey !== "";
  const hasComfyUrl = serviceStatus.comfyui || settings.comfy.url !== "";
  const hasRunningHub = serviceStatus.runninghub || settings.runninghub.apiKey !== "";
  const hasMiniMax = serviceStatus.minimax || settings.minimaxKey !== "";

  return (
    <div className="flex h-screen w-full bg-[#07080a] text-zinc-100 overflow-hidden font-sans relative antialiased">
      {/* Toast Notification Container */}
      <Toast toasts={toasts} onClose={removeToast} />

      {/* 1. LEFT SIDEBAR NAVIGATION */}
      <aside className="w-64 bg-[#101114] border-r border-zinc-900 flex flex-col justify-between flex-shrink-0 h-full">
        <div className="flex flex-col min-h-0 flex-1">
          {/* Brand header */}
          <div className="p-4 border-b border-zinc-900 flex items-center gap-2.5 bg-[#0c0d10]">
            <div className="w-7 h-7 rounded bg-amber-500 flex items-center justify-center shadow-lg shadow-amber-500/10">
              <Tv className="w-4 h-4 text-black stroke-[2.5]" />
            </div>
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

            <button
              onClick={() => setActiveTab("custom-media")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded transition-all ${
                activeTab === "custom-media"
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/15"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-[#15161c]"
              }`}
            >
              <Layers className="w-4 h-4" />
              <span>自定义素材 Custom Media</span>
            </button>

            <button
              onClick={() => setActiveTab("digital-human")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded transition-all ${
                activeTab === "digital-human"
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/15"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-[#15161c]"
              }`}
            >
              <User className="w-4 h-4" />
              <span>数字人口播 Digital Human</span>
            </button>

            <button
              onClick={() => setActiveTab("image-to-video")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded transition-all ${
                activeTab === "image-to-video"
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/15"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-[#15161c]"
              }`}
            >
              <Tv className="w-4 h-4" />
              <span>图生视频 Image to Video</span>
            </button>

            <button
              onClick={() => setActiveTab("action-transfer")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs font-medium rounded transition-all ${
                activeTab === "action-transfer"
                  ? "bg-amber-500/10 text-amber-400 border border-amber-500/15"
                  : "text-zinc-400 hover:text-zinc-200 hover:bg-[#15161c]"
              }`}
            >
              <Workflow className="w-4 h-4" />
              <span>动作迁移 Action Transfer</span>
            </button>

            <div className="pt-4 pb-1">
              <span className="text-[9px] font-bold text-zinc-650 tracking-wider uppercase block px-2.5 mb-1.5 font-mono">
                资产管理 / Logs
              </span>
            </div>

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
                Gemini LLM
              </span>
              <span className="flex items-center gap-1 text-[10px] text-emerald-400 font-semibold bg-emerald-500/5 px-1 rounded">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                已就绪
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
              <span className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-500/5 px-1 rounded font-semibold">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                云托管
              </span>
            </div>
          </div>

          {/* Quick presets picker summary */}
          {presets.length > 0 && (
            <div className="pt-2 border-t border-zinc-900/60">
              <label className="block text-[9px] text-zinc-650 font-mono uppercase mb-1">
                已载入云端预设:
              </label>
              <select
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
              </select>
            </div>
          )}
        </div>
      </aside>

      {/* 2. CENTER WORKSPACE WITH HEADER & BODY */}
      <main className="flex-1 flex flex-col min-w-0 h-full">
        {/* TOP STATUS BAR */}
        <header className="h-12 bg-[#101114] border-b border-zinc-900 px-4 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-zinc-200 font-display">
              {activeTab === "quick-create" && "快捷创作工作室 / Quick Create Studio"}
              {activeTab === "custom-media" && "自定义素材混剪 / Custom Media Stitching"}
              {activeTab === "digital-human" && "数字人口播生成 / Digital Human Anchor"}
              {activeTab === "image-to-video" && "图片扩散图生视频 / Image to Video SVD"}
              {activeTab === "action-transfer" && "骨骼姿态动作迁移 / Action Transfer Control"}
              {activeTab === "history" && "生产日志与历史项目 / Production History"}
              {activeTab === "settings" && "系统算力网络配置 / Server Configurations"}
            </span>
          </div>

          <div className="flex items-center gap-3">
            {/* Quick monitor indicators */}
            <div className="hidden sm:flex items-center gap-2 text-[10px] font-mono text-zinc-500 bg-zinc-900/80 px-2.5 py-1 rounded border border-zinc-850">
              <span className="flex items-center gap-1 text-emerald-400">
                <span className="h-1 w-1 bg-emerald-500 rounded-full"></span> LLM Connected
              </span>
              <span className="text-zinc-700">|</span>
              <span className="flex items-center gap-1 text-emerald-400">
                <span className="h-1 w-1 bg-emerald-500 rounded-full"></span> BizyAir Ready
              </span>
            </div>

            {/* Language Selector */}
            <button
              onClick={() => {
                setLang(lang === "zh" ? "en" : "zh");
                addToast(lang === "zh" ? "Switched to English tags" : "已切换为中文标签", "info");
              }}
              className="p-1.5 bg-[#17181c] border border-zinc-800 rounded text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1 text-xs"
              title="切换语言 Language"
            >
              <Languages className="w-3.5 h-3.5" />
              <span className="font-mono text-[10px] uppercase font-semibold">{lang}</span>
            </button>
          </div>
        </header>

        {/* MAIN BODY AREA */}
        <div className="flex-1 overflow-y-auto p-5">
          {activeTab === "quick-create" && (
            <QuickCreate
              onGenerateTask={handleGenerateTask}
              activePreset={activePreset}
              onSavePreset={handleSavePreset}
              resources={resources}
              addToast={addToast}
            />
          )}

          {activeTab === "custom-media" && (
            <CustomMedia onGenerateTask={handleGenerateTask} addToast={addToast} />
          )}

          {activeTab === "digital-human" && (
            <DigitalHuman onGenerateTask={handleGenerateTask} addToast={addToast} />
          )}

          {activeTab === "image-to-video" && (
            <ImageToVideo onGenerateTask={handleGenerateTask} addToast={addToast} />
          )}

          {activeTab === "action-transfer" && (
            <ActionTransfer onGenerateTask={handleGenerateTask} addToast={addToast} />
          )}

          {activeTab === "history" && (
            <HistoryList
              tasks={tasks}
              onDeleteTask={handleDeleteTask}
              onResumeTask={handleResumeTask}
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
      <ConsolePanel
        activeTask={activeTask}
        recentTasks={tasks}
        onSelectTask={(t) => {
          // Open details by switching tab to History or showing popup
          setActiveTab("history");
          addToast(`正在聚焦查看任务: ${t.title}`, "info");
        }}
        addToast={addToast}
      />
    </div>
  );
}
