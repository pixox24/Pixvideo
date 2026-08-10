import React, { useState, useEffect, useRef } from "react";
import {
  Sparkles,
  History,
  Settings as SettingsIcon,
  Cpu,
  Tv,
  FolderOpen,
  Menu,
  PanelRightOpen,
  PanelRightClose,
  X,
  ChevronDown,
  ChevronUp,
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
import { createProject, startGenerationRun } from "./lib/workbenchApi";
import { createProjectFromHistory } from "./lib/workbenchApi";
import { loadRecentProjects, pushRecentProject, RecentProject } from "./lib/recentProjects";
import { FirstRunCoach } from "./components/FirstRunCoach";
import {
  dismissFirstRunCoach,
  isFirstRunCoachDismissed,
} from "./lib/onboarding";

const PENDING_TASK_ID_PREFIX = "pending-";

const isPendingTaskId = (taskId: string) => taskId.startsWith(PENDING_TASK_ID_PREFIX);

const TOAST_DURATION: Record<ToastMessage["type"], number> = {
  success: 3500,
  info: 4500,
  error: 0, // sticky until dismissed
};

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
    mimo: false,
  });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  /** Default collapsed; open automatically when a direct-render task is submitted. */
  const [consoleOpen, setConsoleOpen] = useState(false);
  const [statusExpanded, setStatusExpanded] = useState(false);
  const [recentProjects, setRecentProjects] = useState<RecentProject[]>(() => loadRecentProjects());
  const [coachOpen, setCoachOpen] = useState(false);
  const [configHydrated, setConfigHydrated] = useState(false);
  const mainScrollRef = useRef<HTMLDivElement | null>(null);
  const pendingCancellationIdsRef = useRef(new Set<string>());
  const toastTimersRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    mainScrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
    setSidebarOpen(false);
  }, [activeTab]);

  useEffect(() => () => {
    toastTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    toastTimersRef.current.clear();
  }, []);

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
    minimaxKey: "",
    mimoKey: ""
  });

  // Toaster helper — errors stay until dismissed; success/info auto-hide.
  const addToast = (text: unknown, type: "success" | "error" | "info" = "info") => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const safeText = formatApiErrorValue(text) || "未知错误";
    const sticky = type === "error";
    setToasts((prev) => [...prev, { id, text: safeText, type, sticky }]);
    const duration = TOAST_DURATION[type];
    if (duration > 0) {
      const timer = window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
        toastTimersRef.current.delete(id);
      }, duration);
      toastTimersRef.current.set(id, timer);
    }
  };

  const removeToast = (id: string) => {
    const timer = toastTimersRef.current.get(id);
    if (timer) {
      window.clearTimeout(timer);
      toastTimersRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const rememberProject = (projectId: string, title: string) => {
    setRecentProjects(
      pushRecentProject({
        projectId,
        title: title || "未命名项目",
        updatedAt: new Date().toISOString(),
      }),
    );
  };

  const openProject = (projectId: string, title?: string) => {
    setActiveProjectId(projectId);
    if (title) rememberProject(projectId, title);
    setActiveTab("project-workbench");
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
      let nextServiceStatus = serviceStatus;
      let nextSettings = settings;
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
          nextSettings = mapBackendConfigToSettings(data, settings);
          setSettings(nextSettings);
          if (data.service_status) {
            nextServiceStatus = data.service_status;
            setServiceStatus(data.service_status);
          }
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

      setConfigHydrated(true);
      if (!isFirstRunCoachDismissed()) {
        const llmOk = nextServiceStatus.llm || nextSettings.llm.apiKey !== "";
        const imageOk = nextServiceStatus.image_generation || nextSettings.imageGeneration.apiKey !== "";
        // Show coach when critical services look incomplete.
        if (!llmOk || !imageOk) {
          setCoachOpen(true);
        }
      }
    };

    loadBackendState();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- boot once
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
    setConsoleOpen(true);
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
    let project: Awaited<ReturnType<typeof createProject>>;
    try {
      project = await createProject(input);
      rememberProject(project.projectId, project.title || input.title);
      setActiveProjectId(project.projectId);
      setActiveTab("project-workbench");
      addToast("项目已创建，正在启动素材生成…", "info");
    } catch (error) {
      addToast(error, "error");
      throw error;
    }
    try {
      await startGenerationRun(project.projectId);
      addToast("初稿生成已启动，可在工作台查看镜头进度。", "success");
    } catch (error) {
      addToast(
        `项目已创建，但自动生成未启动：${formatApiErrorValue(error)}。请在工作台点击「开始生成」重试。`,
        "error",
      );
      // Keep user on workbench so they can retry manually.
    }
  };

  const handleOpenHistoryWorkbench = async (task: Task) => {
    try {
      const project = await createProjectFromHistory(task.id);
      rememberProject(project.projectId, project.title || task.title);
      setActiveProjectId(project.projectId);
      setActiveTab("project-workbench");
      addToast("已创建新的可编辑项目（原历史记录保留）。", "success");
    } catch (error) {
      addToast(error, "error");
    }
  };

  // Sidebar connectivity widgets indicator
  const hasLlm = serviceStatus.llm || settings.llm.apiKey !== "";
  const hasRunningHub = serviceStatus.runninghub || settings.runninghub.apiKey !== "";
  const hasImageGeneration = serviceStatus.image_generation || settings.imageGeneration.apiKey !== "";
  const hasMiniMax = serviceStatus.minimax || settings.minimaxKey !== "";
  const hasMimo = serviceStatus.mimo || settings.mimoKey !== "";
  const latestCompletedQuickCreateTask = tasks.find(
    (task) => task.tabType === "quick-create" && task.status === "completed" && !isPendingTaskId(task.id),
  ) || null;
  const statusItems: Array<{ key: string; label: string; ok: boolean; detail: string }> = [
    { key: "llm", label: "语言模型", ok: hasLlm, detail: serviceStatus.llm ? "已连接" : hasLlm ? "已配置" : "待配置" },
    { key: "image", label: "图像生成", ok: hasImageGeneration, detail: hasImageGeneration ? "已就绪" : "待配置" },
    { key: "minimax", label: "MiniMax 配音", ok: Boolean(serviceStatus.minimax || hasMiniMax), detail: serviceStatus.minimax ? "已连接" : hasMiniMax ? "已配置" : "未配置" },
    { key: "mimo", label: "MiMo 配音", ok: Boolean(serviceStatus.mimo || hasMimo), detail: serviceStatus.mimo ? "已连接" : hasMimo ? "已配置" : "未配置" },
    { key: "runninghub", label: "RunningHub", ok: hasRunningHub, detail: hasRunningHub ? "已就绪" : "待配置" },
    { key: "bizyair", label: "BizyAir", ok: Boolean(serviceStatus.bizyair), detail: serviceStatus.bizyair ? "已连接" : "未检测" },
  ];
  const readySummaryCount = statusItems.filter((item) => item.ok).length;
  const currentProjectTitle =
    recentProjects.find((item) => item.projectId === activeProjectId)?.title ||
    (activeProjectId ? "当前项目" : null);
  const navBtn = (tab: ActiveTab, active: boolean) =>
    `w-full flex items-center gap-2.5 px-3 py-2.5 text-sm font-medium rounded-md transition-all ${
      active
        ? "bg-amber-500/10 text-amber-400 border border-amber-500/15"
        : "text-zinc-400 hover:text-zinc-200 hover:bg-[#15161c] border border-transparent"
    }`;

  const coachNeeds = [
    {
      key: "llm",
      label: "语言模型",
      detail: hasLlm ? "已配置，可用于生成文案与分镜" : "用于主题生成口播稿与分镜脚本",
      required: !hasLlm,
    },
    {
      key: "image",
      label: "图像生成",
      detail: hasImageGeneration ? "已就绪，可用于画面素材" : "用于生成分镜画面（也可后续配置）",
      required: !hasImageGeneration,
    },
    {
      key: "tts",
      label: "配音",
      detail: hasMiniMax || hasMimo
        ? "已配置云端配音；也可使用免费 Edge"
        : "未配置云端 TTS 时将默认使用 Edge（免 Key）",
      required: false,
    },
  ].map((item) => ({
    ...item,
    // Keep list order but only surface missing required first visually via required flag
    required: item.required,
  }));

  return (
    <div className="flex h-screen w-full bg-[var(--color-surface-0)] text-zinc-100 overflow-hidden font-sans relative antialiased">
      <Toast toasts={toasts} onClose={removeToast} />
      <FirstRunCoach
        open={coachOpen && configHydrated}
        needs={coachNeeds}
        onDismiss={() => {
          dismissFirstRunCoach();
          setCoachOpen(false);
        }}
        onOpenSettings={() => setActiveTab("settings")}
        onStartCreate={() => setActiveTab("quick-create")}
      />

      {sidebarOpen && (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-label="关闭导航遮罩"
        />
      )}

      <aside className={`fixed inset-y-0 left-0 z-40 w-64 bg-[var(--color-surface-2)] border-r border-zinc-800/80 flex flex-col justify-between flex-shrink-0 h-full transition-transform lg:static lg:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="flex flex-col min-h-0 flex-1">
          <div className="p-4 border-b border-zinc-800/80 flex items-center gap-2.5 bg-[var(--color-surface-1)]">
            <div className="w-8 h-8 rounded-lg bg-amber-500 flex items-center justify-center shadow-lg shadow-amber-500/20">
              <Tv className="w-4 h-4 text-black stroke-[2.5]" />
            </div>
            <div className="min-w-0 flex-1">
              <h1 className="text-sm font-black font-display text-zinc-100 tracking-wide">
                PixVideo
              </h1>
              <span className="text-caption text-amber-500 font-semibold block mt-0.5">
                AI 短视频工作台
              </span>
            </div>
            <button
              type="button"
              onClick={() => setSidebarOpen(false)}
              className="p-1 text-zinc-400 lg:hidden"
              aria-label="关闭导航"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <nav className="p-3 space-y-1 overflow-y-auto flex-1">
            <span className="text-caption font-semibold tracking-wider uppercase block px-2.5 mb-1.5">
              创作
            </span>
            <button type="button" onClick={() => setActiveTab("quick-create")} className={navBtn("quick-create", activeTab === "quick-create")}>
              <Sparkles className="w-4 h-4" />
              <span>快捷创作</span>
            </button>

            <div className="pt-4 pb-1">
              <span className="text-caption font-semibold tracking-wider uppercase block px-2.5 mb-1.5">
                项目与资产
              </span>
            </div>

            <button
              type="button"
              onClick={() => setActiveTab("project-workbench")}
              className={navBtn("project-workbench", activeTab === "project-workbench")}
            >
              <FolderOpen className="w-4 h-4" />
              <span>项目工作台</span>
            </button>

            <button type="button" onClick={() => setActiveTab("history")} className={navBtn("history", activeTab === "history")}>
              <History className="w-4 h-4" />
              <span>历史记录</span>
            </button>

            <button type="button" onClick={() => setActiveTab("settings")} className={navBtn("settings", activeTab === "settings")}>
              <SettingsIcon className="w-4 h-4" />
              <span>系统设置</span>
            </button>
          </nav>
        </div>

        <div className="p-3 border-t border-zinc-900 bg-[#0c0d10] space-y-2">
          <button
            type="button"
            onClick={() => setStatusExpanded((open) => !open)}
            className="w-full flex items-center justify-between text-left"
          >
            <span className="text-caption font-semibold tracking-wider uppercase">
              服务状态 · {readySummaryCount}/{statusItems.length} 就绪
            </span>
            {statusExpanded ? <ChevronUp className="w-3.5 h-3.5 text-zinc-500" /> : <ChevronDown className="w-3.5 h-3.5 text-zinc-500" />}
          </button>

          {statusExpanded && (
            <div className="space-y-1">
              {statusItems.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setActiveTab("settings")}
                  className="w-full flex items-center justify-between rounded px-1.5 py-1 text-xs hover:bg-zinc-900/80"
                  title="点击前往系统设置"
                >
                  <span className="text-zinc-500 flex items-center gap-1.5">
                    <Cpu className="w-3.5 h-3.5 text-zinc-600" />
                    {item.label}
                  </span>
                  <span className={`flex items-center gap-1 text-caption font-semibold px-1 rounded ${item.ok ? "text-emerald-400" : "text-amber-400"}`}>
                    <span className={`h-1.5 w-1.5 rounded-full ${item.ok ? "bg-emerald-500" : "bg-amber-500"}`} />
                    {item.detail}
                  </span>
                </button>
              ))}
            </div>
          )}

          {activePreset && (
            <div className="pt-1 border-t border-zinc-900/60">
              <p className="text-caption text-zinc-500 mb-0.5">当前预设</p>
              <p className="text-xs text-zinc-300 truncate">{activePreset.name}</p>
            </div>
          )}
        </div>
      </aside>

      <div className="flex-1 min-w-0 h-full flex justify-center">
        <div className={`w-full h-full flex min-w-0 ${activeTab === "project-workbench" && activeProjectId ? "max-w-none" : "max-w-[1680px]"}`}>
      <main className="flex-1 flex flex-col min-w-0 h-full">
        <header className={`h-12 bg-[#101114] border-b border-zinc-900 px-4 flex items-center justify-between flex-shrink-0 ${activeTab === "project-workbench" && activeProjectId ? "lg:pl-4" : ""}`}>
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="p-1.5 text-zinc-400 hover:text-zinc-100 lg:hidden"
              aria-label="打开导航"
            >
              <Menu className="w-4 h-4" />
            </button>
            <span className="text-sm font-semibold text-zinc-200 font-display truncate">
              {activeTab === "quick-create" && "快捷创作"}
              {activeTab === "project-workbench" && (currentProjectTitle ? `工作台 · ${currentProjectTitle}` : "项目工作台")}
              {activeTab === "history" && "历史记录"}
              {activeTab === "settings" && "系统设置"}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setActiveTab("settings")}
              className="hidden sm:flex items-center gap-2 text-xs text-zinc-500 bg-zinc-900/80 px-2.5 py-1 rounded border border-zinc-800 hover:border-zinc-700 hover:text-zinc-300"
              title="查看服务配置"
            >
              <span className={`flex items-center gap-1 ${hasLlm ? "text-emerald-400" : "text-amber-400"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${hasLlm ? "bg-emerald-500" : "bg-amber-500"}`} />
                LLM
              </span>
              <span className="text-zinc-700">|</span>
              <span className={`flex items-center gap-1 ${hasImageGeneration ? "text-emerald-400" : "text-amber-400"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${hasImageGeneration ? "bg-emerald-500" : "bg-amber-500"}`} />
                图像
              </span>
            </button>

            {!(activeTab === "project-workbench" && activeProjectId) && (
              <button
                type="button"
                onClick={() => setConsoleOpen((open) => !open)}
                className="p-1.5 bg-[#17181c] border border-zinc-800 rounded text-zinc-400 hover:text-zinc-200 transition-colors flex items-center gap-1 text-xs"
                aria-label={consoleOpen ? "关闭任务面板" : "打开任务面板"}
              >
                {consoleOpen ? <PanelRightClose className="w-3.5 h-3.5" /> : <PanelRightOpen className="w-3.5 h-3.5" />}
                <span className="hidden sm:inline text-xs">任务</span>
              </button>
            )}
          </div>
        </header>

        <div
          ref={mainScrollRef}
          className={
            activeTab === "project-workbench" && activeProjectId
              ? "flex-1 min-h-0 overflow-hidden p-0"
              : "flex-1 overflow-y-auto p-3 sm:p-5 xl:p-6"
          }
        >
          {activeTab === "quick-create" && (
            <QuickCreate
              onGenerateTask={handleGenerateTask}
              latestCompletedTaskId={latestCompletedQuickCreateTask?.id || null}
              latestCompletedTaskTitle={latestCompletedQuickCreateTask?.title || null}
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
              serviceReady={{
                llm: hasLlm,
                image: hasImageGeneration,
                minimax: hasMiniMax || Boolean(serviceStatus.minimax),
                mimo: hasMimo || Boolean(serviceStatus.mimo),
              }}
              onOpenSettings={() => setActiveTab("settings")}
              onOpenConsole={() => setConsoleOpen(true)}
            />
          )}

          {activeTab === "project-workbench" && activeProjectId && (
            <div className="h-full min-h-0">
              <ProjectWorkbench projectId={activeProjectId} resources={resources} addToast={addToast} />
            </div>
          )}

          {activeTab === "project-workbench" && !activeProjectId && (
            <div className="mx-auto max-w-lg space-y-4 rounded-xl border border-dashed border-zinc-800 bg-[var(--color-surface-2)] p-8 text-center animate-soft-scale-in shadow-[var(--shadow-card)]">
              <FolderOpen className="mx-auto h-10 w-10 text-zinc-600" />
              <div>
                <h2 className="text-base font-semibold text-zinc-100 font-display">还没有打开的项目</h2>
                <p className="mt-1.5 text-sm text-zinc-400">
                  从快捷创作生成初稿，或从历史记录复制为可编辑项目。
                </p>
              </div>
              {recentProjects.length > 0 && (
                <div className="space-y-2 text-left">
                  <p className="text-xs font-medium text-zinc-500">最近项目</p>
                  {recentProjects.map((project) => (
                    <button
                      key={project.projectId}
                      type="button"
                      onClick={() => openProject(project.projectId, project.title)}
                      className="w-full rounded-md border border-zinc-800 bg-[#17181c] px-3 py-2.5 text-left hover:border-amber-500/40"
                    >
                      <div className="truncate text-sm text-zinc-200">{project.title}</div>
                      <div className="mt-0.5 text-caption text-zinc-500">
                        {new Date(project.updatedAt).toLocaleString()}
                      </div>
                    </button>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap justify-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setActiveTab("quick-create")}
                  className="rounded-md bg-amber-500 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-400"
                >
                  去快捷创作
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("history")}
                  className="rounded-md border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:border-zinc-500"
                >
                  查看历史记录
                </button>
              </div>
            </div>
          )}

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

      {/* Hide task console while immersed in project workbench */}
      {!(activeTab === "project-workbench" && activeProjectId) && consoleOpen && (
        <button type="button" className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setConsoleOpen(false)} aria-label="关闭任务面板遮罩" />
      )}
      {!(activeTab === "project-workbench" && activeProjectId) && (
        <ConsolePanel
          activeTask={activeTask}
          recentTasks={tasks}
          isOpen={consoleOpen}
          onClose={() => setConsoleOpen(false)}
          onCancelTask={handleCancelTask}
          onSelectTask={(t) => {
            setActiveTab("history");
            addToast(`已切换到历史记录查看：${t.title}`, "info");
          }}
          addToast={addToast}
        />
      )}
        </div>
      </div>
    </div>
  );
}
