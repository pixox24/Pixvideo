export type ActiveTab =
  | "quick-create"
  | "project-workbench"
  | "history"
  | "settings";

export type TaskSource =
  | "quick-create"
  | "custom-media"
  | "digital-human"
  | "image-to-video"
  | "action-transfer";

export interface Preset {
  id: string;
  name: string;
  createdAt?: string;
  updatedAt?: string;
  ttsMode: "edge" | "comfyui" | "minimax";
  voice: string;
  speed: number;
  workflow: string;
  bgm: string;
  bgmVolume: number;
  promptPrefix: string;
  splitType: "paragraph" | "line" | "sentence";
  enableMotion?: boolean;
  enableSubtitles?: boolean;
  minimaxModel?: string;
  emotion?: string;
  sceneCount?: number;
  copyCharCount?: number;
  copyCharCountMode?: "around" | "within";
  copyDraftMode?: "full" | "segmented";
  mediaWidth?: number;
  mediaHeight?: number;
  imageAspectRatio?: string;
  subtitleStyle?: SubtitleStyle;
}

export interface Task {
  id: string;
  title: string;
  tabType: TaskSource;
  status: "ready" | "generating" | "completed" | "failed" | "cancelled";
  progress: number;
  currentStep: string;
  progressEventType?: string;
  progressFrameCurrent?: number;
  progressFrameTotal?: number;
  progressStep?: number;
  progressAction?: string;
  progressExtraInfo?: string;
  sceneCount: number;
  createdTime: string;
  duration?: number; // estimated or real seconds
  videoUrl?: string; // final preview url
  errorMsg?: string;
  configSummary?: string;
  // Deep details for historical analysis
  scenes?: {
    id: number;
    ttsText: string;
    visualPrompt: string;
    imageUrl?: string;
    status: "pending" | "completed" | "failed";
  }[];
}

export interface LLMConfig {
  provider: "gemini" | "openai" | "deepseek" | "anthropic";
  apiKey: string;
  baseUrl: string;
  model: string;
}

export interface ImageGenerationConfig {
  apiKey: string;
  baseUrl: string;
  model: string;
}

export interface ComfyConfig {
  url: string;
  apiKey: string;
}

export interface RunningHubConfig {
  apiKey: string;
  concurrency: number;
  instanceType: "24G" | "48G";
}

export interface SystemSettings {
  llm: LLMConfig;
  imageGeneration: ImageGenerationConfig;
  comfy: ComfyConfig;
  runninghub: RunningHubConfig;
  bizyairKey: string;
  minimaxKey: string;
}

export interface WorkflowOption {
  id: string;
  name: string;
  source: string;
  type: string;
  resolution: string;
  desc: string;
}

export interface BgmOption {
  id: string;
  name: string;
  source?: string;
  author?: string;
  duration?: string;
  src?: string;
}

export interface SubtitleStyle {
  mode: "drawtext" | "ass" | "hyperframes";
  preset: "clean-white" | "short-video-bold" | "cinema-soft" | "caption-box";
  fontFamily?: string;
  fontPath?: string;
  fontSize: number;
  primaryColor: string;
  accentColor: string;
  outlineColor: string;
  backColor: string;
  outlineWidth: number;
  shadow: number;
  marginV: number;
  alignment: number;
  maxCharsPerLine: number;
  maxLines: number;
  animation: "none" | "fade" | "pop" | "word-pop";
  segmentMode: "line" | "sentence" | "phrase";
  highlightWords?: string[];
  /** Optional per-keyword hex colors; falls back to accentColor. */
  keywordColors?: Record<string, string>;
  highlightStyle?: "accent" | "pop" | "badge";
  highlightScale?: number;
  backgroundOpacity?: number;
  /** Ease-in duration in ms (ASS fad / dynamic overlay). */
  fadeInMs?: number;
  /** Ease-out duration in ms. */
  fadeOutMs?: number;
}

export interface FontOption {
  name: string;
  path: string;
  source: string;
}

export interface WorkbenchResources {
  workflows: WorkflowOption[];
  bgm: BgmOption[];
  fonts: FontOption[];
}

export type WorkbenchJobStatus = "pending" | "running" | "completed" | "failed" | "cancelled";
export interface AssetVersion { versionId: string; source: "ai" | "upload"; imageUrl: string; thumbnailUrl?: string; promptSnapshot?: string; createdAt: string; }
export interface WorkbenchScene { sceneId: string; position: number; narration: string; visualPrompt: string; currentVersionId: string | null; audioUrl?: string; durationSeconds: number; manualHoldSeconds: number; status: string; versions: AssetVersion[]; }
export interface GenerationJob { jobId: string; taskId: string; sceneId?: string; kind: "scene" | "image" | "tts" | "export"; status: WorkbenchJobStatus; progress: number; error?: string; }
export interface Project { projectId: string; title: string; source?: string; config: Record<string, unknown>; scenes: WorkbenchScene[]; jobs: GenerationJob[]; updatedAt: string; }
export interface QuickCreateInput { title: string; scenes: Array<{ id?: number; ttsText: string; visualPrompt: string }>; [key: string]: unknown; }
export interface ExportSubmission { exportId: string; jobId: string; taskId: string; status: WorkbenchJobStatus; blockingScenes: string[]; }
