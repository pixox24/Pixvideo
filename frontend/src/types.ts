export type ActiveTab =
  | "quick-create"
  | "custom-media"
  | "digital-human"
  | "image-to-video"
  | "action-transfer"
  | "history"
  | "settings";

export interface Preset {
  id: string;
  name: string;
  ttsMode: "edge" | "comfyui" | "minimax";
  voice: string;
  speed: number;
  workflow: string;
  bgm: string;
  bgmVolume: number;
  promptPrefix: string;
  splitType: "paragraph" | "line" | "sentence";
  template?: string;
  viewMode?: "template" | "pure-image";
  enableMotion?: boolean;
  enableSubtitles?: boolean;
  minimaxModel?: string;
  emotion?: string;
}

export interface Task {
  id: string;
  title: string;
  tabType: ActiveTab;
  status: "ready" | "generating" | "completed" | "failed";
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

export interface TemplateOption {
  id: string;
  name: string;
  type: string;
  dimensions: string;
  orientation: string;
  desc: string;
}

export interface WorkbenchResources {
  workflows: WorkflowOption[];
  bgm: BgmOption[];
  templates: TemplateOption[];
}
