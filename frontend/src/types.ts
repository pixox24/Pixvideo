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

export type DirectorMode = "auto" | "custom";
export type StoryboardDensity = "sparse" | "standard" | "dense";

export interface StoryboardDirectorConfig {
  directorMode: DirectorMode;
  density: StoryboardDensity;
  targetSceneCount: number | null;
}

export interface StoryboardAnalysisUnit {
  index: number;
  text: string;
  chars: number;
  estimatedSeconds: number;
  boundaryReason: string;
  visualFocus: string;
  textAnchors: string[];
}

export interface StoryboardAnalysis {
  recommendedSceneCount: number;
  actualSceneCount: number;
  targetSceneCount: number | null;
  density: StoryboardDensity;
  estimatedDurationSeconds: number;
  semanticUnits: StoryboardAnalysisUnit[];
  warnings: string[];
}

export interface Preset {
  id: string;
  name: string;
  createdAt?: string;
  updatedAt?: string;
  ttsMode: "edge" | "comfyui" | "minimax" | "mimo" | "qwen_audio";
  voice: string;
  speed: number;
  /** continuous = one multi-scene synth then split (recommended); per_scene = legacy */
  ttsDelivery?: "continuous" | "per_scene";
  workflow: string;
  bgm: string;
  bgmVolume: number;
  promptPrefix: string;
  splitType: "auto" | "paragraph" | "line" | "sentence";
  enableMotion?: boolean;
  enableSubtitles?: boolean;
  /** When true, call image API / workflows; when false (default), use local 素材库. */
  useApiImage?: boolean;
  minimaxModel?: string;
  emotion?: string;
  mimoModel?: string;
  mimoStyle?: string;
  qwenAudioModel?: string;
  qwenAudioMode?: "preset" | "instruct" | "design" | "clone";
  qwenAudioInstruction?: string;
  qwenAudioRefAudio?: string;
  sceneCount?: number;
  copyCharCount?: number;
  copyCharCountMode?: "around" | "within";
  copyDraftMode?: "full" | "segmented";
  mediaWidth?: number;
  mediaHeight?: number;
  /** Final video fps (成片帧率), default 30 */
  videoFps?: number;
  imageAspectRatio?: string;
  subtitleStyle?: SubtitleStyle;
  directorMode?: DirectorMode;
  density?: StoryboardDensity;
  targetSceneCount?: number | null;
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
  apiKeyMasked?: string;
  baseUrl: string;
  model: string;
}

export interface ImageGenerationConfig {
  apiKey: string;
  apiKeyMasked?: string;
  baseUrl: string;
  model: string;
}

export interface VisionUnderstandingConfig {
  enabled: boolean;
  provider: string;
  apiKey: string;
  apiKeyMasked?: string;
  baseUrl: string;
  model: string;
  fallbackModel: string;
  timeoutSeconds: number;
}

export interface ComfyConfig {
  url: string;
  apiKey: string;
  apiKeyMasked?: string;
}

export interface RunningHubConfig {
  apiKey: string;
  apiKeyMasked?: string;
  concurrency: number;
  instanceType: "24G" | "48G";
}

export interface SystemSettings {
  llm: LLMConfig;
  imageGeneration: ImageGenerationConfig;
  comfy: ComfyConfig;
  runninghub: RunningHubConfig;
  bizyairKey: string;
  bizyairKeyMasked?: string;
  minimaxKey: string;
  minimaxKeyMasked?: string;
  mimoKey: string;
  mimoKeyMasked?: string;
  qwenAudioKey: string;
  qwenAudioKeyMasked?: string;
  qwenAudioWorkspaceId: string;
  visionUnderstanding: VisionUnderstandingConfig;
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
  /** Intent: background box (caption-box). Server dual-writes legacy fields. */
  boxEnabled?: boolean;
  boxColor?: string;
  boxOpacity?: number;
  boxPadding?: number;
  boxRadius?: number;
  /** Intent: text stroke (non box presets). */
  strokeWidth?: number;
  strokeColor?: string;
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
export type StoryboardField = "narration" | "visualPrompt" | "visualFocus" | "textAnchors";
export interface WorkbenchScene {
  sceneId: string;
  position: number;
  narration: string;
  visualPrompt: string;
  visualFocus?: string;
  textAnchors?: string[];
  lockedFields?: StoryboardField[];
  editedFields?: StoryboardField[];
  locked?: boolean;
  currentVersionId: string | null;
  audioUrl?: string;
  durationSeconds: number;
  manualHoldSeconds: number;
  status: string;
  versions: AssetVersion[];
  generationState?: GenerationState;
}
export type GenerationRunStatus = "queued" | "running" | "paused" | "completed" | "completed_with_failures" | "cancelled" | "failed";
export type GenerationRunItemStatus = "queued" | "running_tts" | "running_image" | "completed" | "skipped" | "failed" | "cancelled" | "candidate_review";
export interface GenerationState { image: "ready" | "missing" | "stale"; audio: "ready" | "missing" | "stale"; candidateCount: number; }
export interface GenerationRunItem { itemId: string; sceneId: string; position: number; status: GenerationRunItemStatus; phase: string; ttsStatus: string; imageStatus: string; skipReason?: string | null; candidateVersionId?: string | null; error?: string | null; updatedAt: string; }
export interface GenerationRun { runId: string; projectId: string; taskId: string; status: GenerationRunStatus; currentSceneId?: string | null; totalCount: number; completedCount: number; skippedCount: number; failedCount: number; candidateReviewCount: number; pauseRequested: boolean; cancelRequested: boolean; error?: string | null; createdAt: string; updatedAt: string; allowedActions?: string[]; items: GenerationRunItem[]; }
export interface GenerationRunError { status?: number; detail?: unknown; currentRunId?: string; blockingScenes?: string[]; }
export interface GenerationJob { jobId: string; taskId: string; sceneId?: string; kind: "scene" | "image" | "tts" | "export"; status: WorkbenchJobStatus; progress: number; error?: string; }
export interface LatestExport {
  exportId: string;
  purpose?: "initial" | "manual" | null;
  status: WorkbenchJobStatus;
  outputUrl?: string | null;
  createdAt: string;
  updatedAt: string;
  progress?: ExportProgressDetail | null;
  /** In-flight export task id (for cancel). */
  taskId?: string | null;
}
export type PipelineCellStatus =
  | "idle"
  | "queued"
  | "running"
  | "ready"
  | "failed"
  | "skipped"
  | "missing"
  | "stale"
  | "candidate";
export interface ExportProgressDetail {
  stage?: string;
  segmentCurrent?: number;
  segmentTotal?: number;
  segments?: Array<{ sceneId: string; position: number; status: string }>;
  updatedAt?: string;
  error?: string;
}
export interface PipelineSceneCell {
  sceneId: string;
  position: number;
  narration: string;
  tts: PipelineCellStatus | string;
  image: PipelineCellStatus | string;
  segment: PipelineCellStatus | string;
}
export interface PipelineProgress {
  phase: string;
  summary: string;
  updatedAt?: string | null;
  assets?: {
    runId?: string;
    status?: string;
    completed?: number;
    total?: number;
    failed?: number;
    currentSceneId?: string | null;
  } | null;
  export?: {
    exportId?: string;
    status?: string;
    purpose?: string | null;
    stage?: string;
    segmentCurrent?: number;
    segmentTotal?: number;
    segments?: Array<{ sceneId: string; position: number; status: string }>;
    error?: string | null;
    updatedAt?: string;
  } | null;
  scenes: PipelineSceneCell[];
  focus?: {
    phase?: string;
    sceneId?: string | null;
    sceneIndex?: number | null;
    sceneTotal?: number | null;
    cell?: string | null;
    stage?: string;
  } | null;
}
export interface Project {
  projectId: string;
  title: string;
  source?: string;
  config: Record<string, unknown>;
  scenes: WorkbenchScene[];
  jobs: GenerationJob[];
  updatedAt: string;
  latestExport?: LatestExport | null;
  dirty?: boolean;
  pipelineProgress?: PipelineProgress | null;
}
export interface QuickCreateInput {
  title: string;
  scenes: Array<{
    id?: number;
    ttsText: string;
    visualPrompt: string;
    visualFocus?: string;
    textAnchors?: string[];
    lockedFields?: StoryboardField[];
    editedFields?: StoryboardField[];
    locked?: boolean;
  }>;
  [key: string]: unknown;
}
export interface ExportSubmission { exportId: string; jobId: string; taskId: string; status: WorkbenchJobStatus; blockingScenes: string[]; candidateWarnings?: string[]; }
