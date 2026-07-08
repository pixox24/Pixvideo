import {
  ActiveTab,
  BgmOption,
  SystemSettings,
  Task,
  TemplateOption,
  WorkbenchResources,
  WorkflowOption,
} from "../types";

export const EMPTY_WORKBENCH_RESOURCES: WorkbenchResources = {
  workflows: [],
  bgm: [{ id: "bgm-none", name: "无背景音乐" }],
  templates: [],
};

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.error || data.message || `Request failed: ${response.status}`);
  }
  return data as T;
}

function normalizeStatus(status?: string): Task["status"] {
  if (status === "completed") return "completed";
  if (status === "failed" || status === "cancelled") return "failed";
  if (status === "pending" || status === "running" || status === "generating") return "generating";
  return "ready";
}

function formatDate(value?: string): string {
  if (!value) return new Date().toLocaleString();
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function apiFileUrl(path?: string): string | undefined {
  if (!path) return undefined;
  if (/^https?:\/\//.test(path)) return path;
  return `/api/files/${path.replace(/^output\//, "")}`;
}

export async function fetchQuickCreateResources(): Promise<WorkbenchResources> {
  const [workflowsRes, templatesRes, bgmRes] = await Promise.all([
    fetchJson<any>("/api/resources/workflows/media"),
    fetchJson<any>("/api/resources/templates"),
    fetchJson<any>("/api/resources/bgm"),
  ]);

  const workflows: WorkflowOption[] = (workflowsRes.workflows || []).map((workflow: any) => ({
    id: workflow.key || workflow.path || workflow.name,
    name: workflow.display_name || workflow.name,
    source: workflow.source || "unknown",
    type: workflow.name?.startsWith("video_") ? "video" : "image",
    resolution: workflow.resolution || "-",
    desc: workflow.path || workflow.key || "",
  }));

  const templates: TemplateOption[] = (templatesRes.templates || []).map((template: any) => ({
    id: template.key || template.path,
    name: template.display_name || template.name,
    type: template.name?.startsWith("video_")
      ? "video"
      : template.name?.startsWith("static_")
        ? "static"
        : "image",
    dimensions: template.size || `${template.width || ""}x${template.height || ""}`,
    orientation: template.orientation || "",
    desc: template.path || template.key || "",
  }));

  const bgm: BgmOption[] = [
    { id: "bgm-none", name: "无背景音乐" },
    ...(bgmRes.bgm_files || []).map((item: any) => ({
      id: item.path || item.name,
      name: item.name,
      source: item.source,
      src: apiFileUrl(item.path),
    })),
  ];

  return { workflows, templates, bgm };
}

export function buildConfigPayload(settings: SystemSettings) {
  return {
    llm: {
      api_key: settings.llm.apiKey || undefined,
      base_url: settings.llm.baseUrl || undefined,
      model: settings.llm.model || undefined,
    },
    image_generation: {
      api_key: settings.imageGeneration.apiKey || undefined,
      base_url: settings.imageGeneration.baseUrl || undefined,
      model: settings.imageGeneration.model || undefined,
    },
    comfyui: {
      comfyui_url: settings.comfy.url || undefined,
      comfyui_api_key: settings.comfy.apiKey || undefined,
      runninghub_api_key: settings.runninghub.apiKey || undefined,
      runninghub_concurrent_limit: settings.runninghub.concurrency,
      runninghub_instance_type: settings.runninghub.instanceType,
      bizyair_api_key: settings.bizyairKey || undefined,
      minimax_api_key: settings.minimaxKey || undefined,
    },
  };
}

export function mapBackendConfigToSettings(data: any, fallback: SystemSettings): SystemSettings {
  return {
    ...fallback,
    llm: {
      ...fallback.llm,
      apiKey: data.llm?.api_key_set ? fallback.llm.apiKey : "",
      baseUrl: data.llm?.base_url || fallback.llm.baseUrl,
      model: data.llm?.model || fallback.llm.model,
    },
    imageGeneration: {
      ...fallback.imageGeneration,
      apiKey: data.image_generation?.api_key_set ? fallback.imageGeneration.apiKey : "",
      baseUrl: data.image_generation?.base_url || fallback.imageGeneration.baseUrl,
      model: data.image_generation?.model || fallback.imageGeneration.model,
    },
    comfy: {
      ...fallback.comfy,
      url: data.comfyui?.comfyui_url || fallback.comfy.url,
      apiKey: data.comfyui?.comfyui_api_key_set ? fallback.comfy.apiKey : "",
    },
    runninghub: {
      ...fallback.runninghub,
      apiKey: data.comfyui?.runninghub_api_key_set ? fallback.runninghub.apiKey : "",
      concurrency: data.comfyui?.runninghub_concurrent_limit || fallback.runninghub.concurrency,
      instanceType: data.comfyui?.runninghub_instance_type || fallback.runninghub.instanceType,
    },
    bizyairKey: data.comfyui?.bizyair_api_key_set ? fallback.bizyairKey : "",
    minimaxKey: data.comfyui?.minimax_api_key_set ? fallback.minimaxKey : "",
  };
}

export function optimisticTaskFromInput(input: any, id: string): Task {
  return {
    id,
    title: input.title || "未命名任务",
    tabType: input.tabType || "quick-create",
    status: "generating",
    progress: 2,
    currentStep: "正在提交任务到后端",
    sceneCount: input.scenes?.length || 1,
    createdTime: new Date().toLocaleString(),
    configSummary: `${input.ttsMode || "edge"} / ${input.workflowId || "default"} / ${input.bgm || "无配乐"}`,
    scenes: (input.scenes || []).map((scene: any) => ({
      id: scene.id,
      ttsText: scene.ttsText || "",
      visualPrompt: scene.visualPrompt || "",
      status: "pending",
    })),
  };
}

function buildVideoPayload(input: any) {
  const scenes = input.scenes || [];
  const text = scenes.map((scene: any) => scene.ttsText).filter(Boolean).join("\n") || input.title;
  const ttsMode = input.ttsMode === "minimax" ? "minimax" : input.ttsMode === "comfyui" ? "comfyui" : "local";
  const bgmPath = input.bgm && input.bgm !== "bgm-none" ? input.bgm : undefined;
  const bgmVolume = input.bgmVolume > 1 ? input.bgmVolume / 100 : input.bgmVolume;

  return {
    pipeline: "standard",
    text,
    title: input.title,
    mode: "fixed",
    split_mode: input.splitType || "line",
    n_scenes: scenes.length || 1,
    media_workflow: input.workflowId || undefined,
    prompt_prefix: input.promptPrefix || undefined,
    frame_template: input.templateId || undefined,
    composition_mode: input.viewMode === "pure-image" ? "plain_image" : "template",
    image_motion_enabled: Boolean(input.enableMotion),
    subtitle_enabled: input.enableSubtitles !== false,
    tts_inference_mode: ttsMode,
    tts_voice: input.voice || undefined,
    tts_speed: input.speed,
    minimax_model: input.minimaxModel || undefined,
    minimax_emotion: input.emotion || undefined,
    media_width: input.mediaWidth || undefined,
    media_height: input.mediaHeight || undefined,
    bgm_path: bgmPath,
    bgm_volume: bgmVolume ?? 0.3,
  };
}

export async function submitVideoTask(input: any): Promise<{ task_id: string }> {
  return fetchJson<{ task_id: string }>("/api/video/generate/async", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildVideoPayload(input)),
  });
}

export async function fetchTask(taskId: string): Promise<any> {
  return fetchJson<any>(`/api/tasks/${taskId}`);
}

export function mapApiTask(apiTask: any, fallback: Task): Task {
  const status = normalizeStatus(apiTask.status);
  const result = apiTask.result || {};
  return {
    ...fallback,
    id: apiTask.task_id || fallback.id,
    status,
    progress: status === "completed" ? 100 : Math.round(apiTask.progress?.percentage || fallback.progress || 0),
    currentStep: apiTask.progress?.message || fallback.currentStep,
    errorMsg: apiTask.error || fallback.errorMsg,
    videoUrl: result.video_url || fallback.videoUrl,
    duration: result.duration || fallback.duration,
  };
}

export async function fetchHistoryTasks(): Promise<any[]> {
  const data = await fetchJson<any>("/api/history?page=1&page_size=100");
  return data.tasks || [];
}

export function mapHistoryTask(task: any): Task {
  const metadata = task.metadata || task;
  const params = metadata.params || metadata.request_params || {};
  const storyboard = task.storyboard || metadata.storyboard || {};
  const frames = storyboard.frames || metadata.frames || [];

  return {
    id: task.task_id || metadata.task_id || metadata.id,
    title: metadata.title || params.title || "历史任务",
    tabType: (metadata.tab_type || "quick-create") as ActiveTab,
    status: normalizeStatus(metadata.status || task.status),
    progress: metadata.status === "completed" || task.status === "completed" ? 100 : 0,
    currentStep: metadata.status || task.status || "历史记录",
    sceneCount: frames.length || params.n_scenes || 1,
    createdTime: formatDate(metadata.created_at || task.created_at),
    duration: metadata.duration,
    videoUrl: task.video_url || metadata.video_url,
    errorMsg: metadata.error,
    configSummary: `${params.tts_inference_mode || "tts"} / ${params.media_workflow || "workflow"} / ${params.bgm_path || "无配乐"}`,
    scenes: frames.map((frame: any, index: number) => ({
      id: index + 1,
      ttsText: frame.narration || frame.text || "",
      visualPrompt: frame.image_prompt || frame.prompt || "",
      imageUrl: frame.image_url || apiFileUrl(frame.image_path),
      status: frame.image_path || frame.image_url ? "completed" : "pending",
    })),
  };
}

export async function deleteHistoryTask(id: string): Promise<void> {
  await fetchJson(`/api/history/${id}`, { method: "DELETE" });
}

export async function resumeHistoryTask(id: string): Promise<void> {
  await fetchJson(`/api/history/${id}/resume`, { method: "POST" });
}
