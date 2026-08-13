import {
  BgmOption,
  FontOption,
  SystemSettings,
  Task,
  TaskSource,
  WorkbenchResources,
  WorkflowOption,
} from "../types";

export const EMPTY_WORKBENCH_RESOURCES: WorkbenchResources = {
  workflows: [],
  bgm: [{ id: "bgm-none", name: "无背景音乐" }],
  fonts: [],
};

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(getApiErrorMessage(data, response.status));
  }
  return data as T;
}

export const requestJson = fetchJson;

export function formatApiErrorValue(value: unknown): string | undefined {
  if (typeof value === "string" && value.trim()) return value;

  // Error / DOMException / fetch failures often land here via addToast(error).
  if (value instanceof Error) {
    const msg = value.message?.trim();
    if (msg && msg !== "{}" && msg !== "null" && msg !== "undefined") return msg;
    return undefined;
  }

  if (Array.isArray(value)) {
    const messages = value
      .map((item) => {
        if (item && typeof item === "object") {
          const detail = item as { loc?: unknown; msg?: unknown };
          if (typeof detail.msg === "string") {
            const location = Array.isArray(detail.loc)
              ? detail.loc.filter((part) => part !== "body").join(".")
              : "";
            return location ? `${location}: ${detail.msg}` : detail.msg;
          }
        }
        return formatApiErrorValue(item);
      })
      .filter((message): message is string => Boolean(message));
    return messages.length > 0 ? messages.join("; ") : undefined;
  }

  if (value && typeof value === "object") {
    const nested = value as { detail?: unknown; error?: unknown; message?: unknown; statusText?: unknown };
    const nestedMessage = (
      formatApiErrorValue(nested.detail) ||
      formatApiErrorValue(nested.error) ||
      formatApiErrorValue(nested.message) ||
      (typeof nested.statusText === "string" ? nested.statusText : undefined)
    );
    if (nestedMessage) return nestedMessage;
    // Avoid toast showing bare "{}" for empty FastAPI/network bodies.
    try {
      const keys = Object.keys(value as object);
      if (keys.length === 0) return undefined;
      const text = JSON.stringify(value);
      if (!text || text === "{}" || text === "[]" || text === "null") return undefined;
      return text;
    } catch {
      return undefined;
    }
  }

  return undefined;
}

function getApiErrorMessage(data: unknown, status: number): string {
  return formatApiErrorValue(data) || `Request failed: ${status}`;
}

function normalizeStatus(status?: string): Task["status"] {
  if (status === "completed") return "completed";
  if (status === "cancelled") return "cancelled";
  if (status === "failed") return "failed";
  if (status === "pending" || status === "running" || status === "generating") return "generating";
  return "ready";
}

function normalizeTaskSource(source?: string): TaskSource {
  if (
    source === "custom-media" ||
    source === "digital-human" ||
    source === "image-to-video" ||
    source === "action-transfer"
  ) {
    return source;
  }
  return "quick-create";
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
  const [workflowsRes, bgmRes, fontsRes] = await Promise.all([
    fetchJson<any>("/api/resources/workflows/media"),
    fetchJson<any>("/api/resources/bgm"),
    fetchJson<any>("/api/resources/fonts"),
  ]);

  const workflows: WorkflowOption[] = (workflowsRes.workflows || []).map((workflow: any) => ({
    id: workflow.key || workflow.path || workflow.name,
    name: workflow.display_name || workflow.name,
    source: workflow.source || "unknown",
    type: workflow.name?.startsWith("video_") ? "video" : "image",
    resolution: workflow.resolution || "-",
    desc: workflow.path || workflow.key || "",
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

  const fonts: FontOption[] = (fontsRes.fonts || []).map((font: any) => ({
    name: font.name,
    path: font.path,
    source: font.source,
  }));

  return { workflows, bgm, fonts };
}

export function buildConfigPayload(settings: SystemSettings) {
  return {
    llm: {
      provider: settings.llm.provider,
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
      mimo_api_key: settings.mimoKey || undefined,
    },
  };
}

export function mapBackendConfigToSettings(data: any, fallback: SystemSettings): SystemSettings {
  return {
    ...fallback,
    llm: {
      ...fallback.llm,
      provider: data.llm?.provider || fallback.llm.provider,
      apiKey: data.llm?.api_key_set ? fallback.llm.apiKey : "",
      apiKeyMasked: data.llm?.api_key_masked || "",
      baseUrl: data.llm?.base_url || fallback.llm.baseUrl,
      model: data.llm?.model || fallback.llm.model,
    },
    imageGeneration: {
      ...fallback.imageGeneration,
      apiKey: data.image_generation?.api_key_set ? fallback.imageGeneration.apiKey : "",
      apiKeyMasked: data.image_generation?.api_key_masked || "",
      baseUrl: data.image_generation?.base_url || fallback.imageGeneration.baseUrl,
      model: data.image_generation?.model || fallback.imageGeneration.model,
    },
    comfy: {
      ...fallback.comfy,
      url: data.comfyui?.comfyui_url || fallback.comfy.url,
      apiKey: data.comfyui?.comfyui_api_key_set ? fallback.comfy.apiKey : "",
      apiKeyMasked: data.comfyui?.comfyui_api_key_masked || "",
    },
    runninghub: {
      ...fallback.runninghub,
      apiKey: data.comfyui?.runninghub_api_key_set ? fallback.runninghub.apiKey : "",
      apiKeyMasked: data.comfyui?.runninghub_api_key_masked || "",
      concurrency: data.comfyui?.runninghub_concurrent_limit || fallback.runninghub.concurrency,
      instanceType: data.comfyui?.runninghub_instance_type || fallback.runninghub.instanceType,
    },
    bizyairKey: data.comfyui?.bizyair_api_key_set ? fallback.bizyairKey : "",
    bizyairKeyMasked: data.comfyui?.bizyair_api_key_masked || "",
    minimaxKey: data.comfyui?.minimax_api_key_set ? fallback.minimaxKey : "",
    minimaxKeyMasked: data.comfyui?.minimax_api_key_masked || "",
    mimoKey: data.comfyui?.mimo_api_key_set ? fallback.mimoKey : "",
    mimoKeyMasked: data.comfyui?.mimo_api_key_masked || "",
  };
}

export type KeywordExtractionStyle = "balanced" | "concept" | "selling_point" | "emotion" | "numeric" | "action";
export type KeywordExtractionDensity = "low" | "standard" | "high";

export interface KeywordExtractionOptions {
  maxKeywords?: number;
  style?: KeywordExtractionStyle;
  density?: KeywordExtractionDensity;
  avoidWords?: string[];
}

export async function extractHighlightKeywords(
  text: string,
  options: KeywordExtractionOptions = {},
): Promise<Array<{ word: string; color: string }>> {
  const data = await fetchJson<{ keywords?: Array<{ word: string; color: string }> }>(
    "/api/content/keywords",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        max_keywords: options.maxKeywords ?? 8,
        style: options.style ?? "balanced",
        density: options.density ?? "standard",
        avoid_words: options.avoidWords ?? [],
      }),
    },
  );
  return (data.keywords || [])
    .map((item) => ({
      word: String(item.word || "").trim(),
      color: String(item.color || "#FFD43B").trim() || "#FFD43B",
    }))
    .filter((item) => item.word);
}

export function optimisticTaskFromInput(input: any, id: string): Task {
  return {
    id,
    title: input.title || "未命名任务",
    tabType: "quick-create",
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
  const sceneTexts = scenes.map((scene: any) => scene.ttsText).filter(Boolean);
  const text = sceneTexts.join("\n\n") || input.title;
  const ttsMode = input.ttsMode === "minimax" ? "minimax" : input.ttsMode === "mimo" ? "mimo" : input.ttsMode === "comfyui" ? "comfyui" : "local";
  const bgmPath = input.bgm && input.bgm !== "bgm-none" ? input.bgm : undefined;
  const bgmVolume = input.bgmVolume > 1 ? input.bgmVolume / 100 : input.bgmVolume;
  const subtitleStyle = input.subtitleStyle
    ? {
        ...input.subtitleStyle,
        fontSize: Math.min(120, Math.max(12, Number(input.subtitleStyle.fontSize) || 52)),
      }
    : undefined;

  return {
    pipeline: "standard",
    text,
    title: input.title,
    mode: "fixed",
    split_mode: scenes.length > 0 ? "paragraph" : input.splitType || "line",
    n_scenes: scenes.length || 1,
    scenes: scenes.map((scene: any) => ({
      narration: String(scene.ttsText || "").trim(),
      visual_prompt: String(scene.visualPrompt || "").trim(),
    })),
    client_request_key: input.clientRequestKey || undefined,
    reuse_assets_from_task_id: input.reuseTaskId || undefined,
    media_workflow: input.workflowId || undefined,
    prompt_prefix: input.promptPrefix || undefined,
    composition_mode: "plain_image",
    image_motion_enabled: Boolean(input.enableMotion),
    subtitle_enabled: input.enableSubtitles !== false,
    subtitle_style: subtitleStyle,
    use_api_image: Boolean(input.useApiImage),
    tts_inference_mode: ttsMode,
    tts_voice: input.voice || undefined,
    tts_speed: input.speed,
    minimax_model: input.minimaxModel || undefined,
    minimax_emotion: input.emotion || undefined,
    mimo_model: input.mimoModel || undefined,
    mimo_style: input.mimoStyle || undefined,
    media_width: input.mediaWidth || undefined,
    media_height: input.mediaHeight || undefined,
    video_fps: input.videoFps || undefined,
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

export async function cancelTask(taskId: string): Promise<void> {
  await fetchJson(`/api/tasks/${taskId}`, { method: "DELETE" });
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
    progressEventType: apiTask.progress?.event_type || fallback.progressEventType,
    progressFrameCurrent: apiTask.progress?.frame_current ?? fallback.progressFrameCurrent,
    progressFrameTotal: apiTask.progress?.frame_total ?? fallback.progressFrameTotal,
    progressStep: apiTask.progress?.step ?? fallback.progressStep,
    progressAction: apiTask.progress?.action || fallback.progressAction,
    progressExtraInfo: apiTask.progress?.extra_info || fallback.progressExtraInfo,
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
  const params = metadata.input || metadata.params || metadata.request_params || task.request_params || {};
  const storyboard = task.storyboard || metadata.storyboard || {};
  const frames = storyboard.frames || metadata.frames || [];

  return {
    id: task.task_id || metadata.task_id || metadata.id,
    title: metadata.title || params.title || "历史任务",
    tabType: normalizeTaskSource(metadata.tab_type),
    status: normalizeStatus(metadata.status || task.status),
    progress: metadata.status === "completed" || task.status === "completed" ? 100 : 0,
    currentStep: metadata.status || task.status || "历史记录",
    sceneCount: frames.length || task.n_frames || metadata.n_frames || params.n_scenes || 1,
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
