import React, { useState } from "react";
import { Select } from "./Select";
import { FontSelect } from "./FontSelect";
import { SubtitleStylePreview } from "./SubtitleStylePreview";
import {
  Sparkles,
  Edit3,
  Layers,
  Music,
  Sliders,
  Volume2,
  Mic2,
  Play,
  FileVideo,
  Eye,
  Loader,
  AlertTriangle,
  Upload,
  Workflow,
  Download,
  Plus,
  Trash2,
  Save,
  ChevronDown,
  ChevronUp,
  FolderOpen,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { Preset, QuickCreateInput, SubtitleStyle, WorkbenchResources } from "../types";
import { VOICE_OPTIONS } from "../data";
import {
  extractHighlightKeywords,
  formatApiErrorValue,
  type KeywordExtractionDensity,
  type KeywordExtractionStyle,
} from "../lib/api";
import { ConfirmModal } from "./ConfirmModal";
import { type WizardStepId, WIZARD_STAGE_ID } from "./quickCreate/wizard";
import { CreateStepper } from "./quickCreate/CreateStepper";
import { CreateStickyFooter } from "./quickCreate/CreateStickyFooter";
import { dismissCreateTip, isCreateTipDismissed } from "../lib/onboarding";
import {
  analyzeStoryboardRecommendation,
  buildStoryboardNarrations,
  clampSceneCount,
  STORYBOARD_SCENE_MAX,
  STORYBOARD_SCENE_MIN,
  type DraftSplitType,
} from "../lib/storyboardSplit";

interface ServiceReadyState {
  llm: boolean;
  image: boolean;
  minimax: boolean;
  mimo: boolean;
}

interface QuickCreateProps {
  onGenerateTask: (taskInput: any) => Promise<string | null>;
  onCreateProject?: (input: QuickCreateInput) => Promise<void>;
  latestCompletedTaskId?: string | null;
  latestCompletedTaskTitle?: string | null;
  presets: Preset[];
  activePreset: Preset | null;
  defaultPresetId: string | null;
  onSelectPreset: (preset: Preset) => void;
  onCreatePreset: (presetInput: Omit<Preset, "id">) => void | Promise<void>;
  onUpdatePreset: (presetId: string, presetInput: Preset) => void | Promise<void>;
  onDeletePreset: (presetId: string) => void | Promise<void>;
  onSetDefaultPreset: (presetId: string) => void | Promise<void>;
  onSavePromptPrefix: (promptPrefix: string) => Promise<string | void>;
  onRefreshResources: () => Promise<void>;
  resources: WorkbenchResources;
  addToast: (text: string, type: "success" | "error" | "info") => void;
  serviceReady?: ServiceReadyState;
  onOpenSettings?: () => void;
  onOpenConsole?: () => void;
}

type FieldErrors = Partial<Record<"title" | "content" | "review" | "tts", string>>;

const DEFAULT_PREVIEW_TTS_TEXT = "这是一段 TTS 试听文案，用来检查音色、语速和发音效果。";
const QUICK_CREATE_DRAFT_KEY = "pixvideo.quick-create.draft.v1";

type KeywordStatus = "idle" | "loading" | "ready" | "stale" | "error";
type KeywordSuggestion = { word: string; color: string };
type KeywordPreferences = {
  autoExtract: boolean;
  style: KeywordExtractionStyle;
  density: KeywordExtractionDensity;
};

const DEFAULT_KEYWORD_PREFERENCES: KeywordPreferences = {
  autoExtract: true,
  style: "balanced",
  density: "standard",
};

const KEYWORD_DENSITY_LIMIT: Record<KeywordExtractionDensity, number> = {
  low: 4,
  standard: 8,
  high: 12,
};

const normalizeKeywordPreferences = (value: unknown): KeywordPreferences => {
  const input = value && typeof value === "object" ? value as Partial<KeywordPreferences> : {};
  return {
    autoExtract: typeof input.autoExtract === "boolean" ? input.autoExtract : true,
    style: ["balanced", "concept", "selling_point", "emotion", "numeric", "action"].includes(String(input.style))
      ? input.style as KeywordExtractionStyle
      : "balanced",
    density: ["low", "standard", "high"].includes(String(input.density))
      ? input.density as KeywordExtractionDensity
      : "standard",
  };
};

const extractPreviewSentenceFromCopyDraft = (rawDraftText: string) => {
  const draftText = rawDraftText
    .split(/\r?\n/)
    .map((line) =>
      line
        .replace(/^\s*(?:[-*•]|\d+[\.\、．)]|第\s*\d+\s*[分镜幕段]?[:：、.．]?)\s*/, "")
        .trim()
    )
    .filter(Boolean)
    .join("\n");
  const firstSentence = draftText.split(/[。\.]/)[0]?.split(/\r?\n/)[0]?.trim();
  return firstSentence || "";
};

const IMAGE_SIZE_PRESETS = [
  { id: "1024x1024", label: "1:1 正方形", width: 1024, height: 1024 },
  { id: "1024x1536", label: "2:3 竖版", width: 1024, height: 1536 },
  { id: "1536x1024", label: "3:2 横版", width: 1536, height: 1024 },
  { id: "2048x2048", label: "1:1 2K", width: 2048, height: 2048 },
  { id: "2560x1440", label: "16:9 QHD", width: 2560, height: 1440 },
  { id: "1440x2560", label: "9:16 QHD", width: 1440, height: 2560 },
  { id: "2880x2880", label: "1:1 4K", width: 2880, height: 2880 },
  { id: "3840x2160", label: "16:9 4K", width: 3840, height: 2160 },
  { id: "2160x3840", label: "9:16 4K", width: 2160, height: 3840 },
  { id: "custom", label: "自定义", width: 1024, height: 1536 },
];

const suggestCopyCharCount = (storyboardCount: number) =>
  Math.max(120, Math.min(600, storyboardCount * 35));

const estimateNarrationSeconds = (charCount: number) =>
  Math.max(1, Math.round((charCount / 260) * 60));

async function runWithConcurrency<T>(
  items: T[],
  concurrency: number,
  worker: (item: T) => Promise<void>,
) {
  const queue = [...items];
  const workers = Array.from(
    { length: Math.min(Math.max(1, concurrency), queue.length) },
    async () => {
      while (queue.length > 0) {
        const item = queue.shift();
        if (item) await worker(item);
      }
    },
  );
  await Promise.all(workers);
}

const parseHighlightWords = (value: string) => Array.from(new Set(
  value
    .split(/[，,、;；\n]/u)
    .map((word) => word.trim())
    .filter(Boolean),
)).slice(0, 24);

const clampNumber = (value: unknown, fallback: number, min: number, max: number) => {
  const parsed = Number(value);
  return Math.min(max, Math.max(min, Number.isFinite(parsed) ? parsed : fallback));
};

const DEFAULT_SUBTITLE_STYLE: SubtitleStyle = {
  mode: "hyperframes",
  preset: "caption-box",
  fontFamily: "",
  fontPath: "",
  fontSize: 80,
  primaryColor: "#FFFFFF",
  accentColor: "#F97316",
  outlineColor: "#000000",
  backColor: "#000000",
  outlineWidth: 0,
  shadow: 0,
  marginV: 200,
  alignment: 2,
  maxCharsPerLine: 20,
  maxLines: 1,
  animation: "fade",
  segmentMode: "sentence",
  highlightWords: [],
  keywordColors: {},
  highlightStyle: "accent",
  highlightScale: 125,
  backgroundOpacity: 72,
  fadeInMs: 120,
  fadeOutMs: 120,
};

const SUBTITLE_PRESET_STYLES: Record<SubtitleStyle["preset"], Partial<SubtitleStyle>> = {
  "short-video-bold": {
    fontSize: 56,
    primaryColor: "#FFFFFF",
    accentColor: "#FFD43B",
    outlineColor: "#000000",
    backColor: "#000000",
    outlineWidth: 4,
    shadow: 1,
    marginV: 120,
    maxLines: 2,
    animation: "fade",
  },
  "clean-white": {
    fontSize: 52,
    primaryColor: "#FFFFFF",
    accentColor: "#FFFFFF",
    outlineColor: "#000000",
    backColor: "#000000",
    outlineWidth: 1,
    shadow: 0,
    marginV: 120,
    maxLines: 2,
    animation: "fade",
  },
  "cinema-soft": {
    fontSize: 52,
    primaryColor: "#FFF7ED",
    accentColor: "#FBBF24",
    outlineColor: "#3F2A1D",
    backColor: "#000000",
    outlineWidth: 2,
    shadow: 2,
    marginV: 140,
    maxLines: 2,
    animation: "fade",
  },
  "caption-box": {
    fontSize: 52,
    primaryColor: "#FFFFFF",
    accentColor: "#FFD43B",
    outlineColor: "#000000",
    backColor: "#000000",
    outlineWidth: 0,
    shadow: 0,
    marginV: 120,
    maxLines: 2,
    backgroundOpacity: 72,
    animation: "fade",
  },
};

export const QuickCreate: React.FC<QuickCreateProps> = ({
  onGenerateTask,
  onCreateProject,
  latestCompletedTaskId,
  presets,
  activePreset,
  defaultPresetId,
  onSelectPreset,
  onCreatePreset,
  onUpdatePreset,
  onDeletePreset,
  onSetDefaultPreset,
  onSavePromptPrefix,
  onRefreshResources,
  resources,
  addToast,
  latestCompletedTaskTitle = null,
  serviceReady,
  onOpenSettings,
  onOpenConsole,
}) => {
  // Main states
  const [mode, setMode] = useState<"ai" | "manual" | "batch">("ai");
  const [title, setTitle] = useState("新品发布创意科技短视频");
  
  // AI Creation states
  const [aiTopic, setAiTopic] = useState("探索未来世界的智能机器人生活碎片");
  const [aiSceneCount, setAiSceneCount] = useState(5);
  /** True once the user manually edits scene count (or loads a preset/draft with an explicit count). */
  const [aiSceneCountTouched, setAiSceneCountTouched] = useState(false);
  /** Semantic suggestion (sentence/line units) after pure-copy step. */
  const [suggestedSceneCount, setSuggestedSceneCount] = useState<number | null>(null);
  /** Rhythm suggestion (chars ÷ ~40) — secondary, not forced. */
  const [rhythmSceneCount, setRhythmSceneCount] = useState<number | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  /** Default full: step1 pure copy → step2 semantic recommend (not locked to N). */
  const [copyDraftMode, setCopyDraftMode] = useState<"full" | "segmented">("full");
  const [copyDraft, setCopyDraft] = useState("");
  const [copyDraftLoading, setCopyDraftLoading] = useState(false);
  const [copyCharCount, setCopyCharCount] = useState(200);
  const [copyCharCountTouched, setCopyCharCountTouched] = useState(true);
  const [copyCharCountMode, setCopyCharCountMode] = useState<"around" | "within">("around");

  // Manual Creation states (Scenes list)
  const [scenes, setScenes] = useState<Array<{ id: number; ttsText: string; visualPrompt: string }>>([
    { id: 1, ttsText: "这是一个科技感爆棚的高能概念画卷。", visualPrompt: "Cinematic digital art of high-tech lab, warm amber lighting, futuristic, 4k" },
    { id: 2, ttsText: "每一个齿轮的咬合，都是精工美学的体现。", visualPrompt: "Macro close-up of amber golden machine gears interlocking in motion, cinematic depth of field" }
  ]);

  // Batch Creation states
  const [batchInput, setBatchInput] = useState("主题一: 智能机器人在雨夜撑伞\n主题二: 机械宠物狗在客厅嬉戏\n主题三: 未来城市空中飞车速递");
  const [batchCount, setBatchCount] = useState(3);
  const [splitType, setSplitType] = useState<DraftSplitType>("line");

  // BGM states
  const [bgm, setBgm] = useState("");
  const [volume, setVolume] = useState(30);
  const [playingBgm, setPlayingBgm] = useState<string | null>(null);
  const bgmPreviewRef = React.useRef<HTMLAudioElement | null>(null);

  // TTS States — default Edge (zero-config). Presets / MiniMax ready state may upgrade later.
  const [ttsMode, setTtsMode] = useState<"edge" | "comfyui" | "minimax" | "mimo">("edge");
  // Phase-1 recommended default: whole-script continuous synth + per-scene split.
  const [ttsDelivery, setTtsDelivery] = useState<"continuous" | "per_scene">("continuous");
  const [voice, setVoice] = useState("zh-CN-XiaoxiaoNeural");
  const [speed, setSpeed] = useState(1.0);
  const [emotion, setEmotion] = useState("");
  const [minimaxModel, setMinimaxModel] = useState("speech-2.8-turbo");
  const [mimoModel, setMimoModel] = useState("mimo-v2.5-tts");
  const [mimoStyle, setMimoStyle] = useState("");
  const [customAudioFile, setCustomAudioFile] = useState<string | null>(null);
  const [previewingTts, setPreviewingTts] = useState(false);
  const [previewTtsText, setPreviewTtsText] = useState(DEFAULT_PREVIEW_TTS_TEXT);
  const [previewTtsAudioUrl, setPreviewTtsAudioUrl] = useState<string | null>(null);
  const previewTtsTextUserEditedRef = React.useRef(false);
  const autoPreviewTtsTextRef = React.useRef("");
  const [synthesizingCopy, setSynthesizingCopy] = useState(false);
  const [copyTtsAudioUrl, setCopyTtsAudioUrl] = useState<string | null>(null);
  const [copyTtsDuration, setCopyTtsDuration] = useState<number | null>(null);
  const [copyTtsSourceLabel, setCopyTtsSourceLabel] = useState("");

  // Image motion composition states
  const [enableMotion, setEnableMotion] = useState(true);
  const [enableSubtitles, setEnableSubtitles] = useState(true);
  const [subtitleStyle, setSubtitleStyle] = useState<SubtitleStyle>(DEFAULT_SUBTITLE_STYLE);
  const [keywordPreferences, setKeywordPreferences] = useState<KeywordPreferences>(DEFAULT_KEYWORD_PREFERENCES);
  const [aiKeywordSuggestions, setAiKeywordSuggestions] = useState<KeywordSuggestion[]>([]);
  const [keywordStatus, setKeywordStatus] = useState<KeywordStatus>("idle");
  const [keywordSourceSnapshot, setKeywordSourceSnapshot] = useState("");
  const [imageAspectRatio, setImageAspectRatio] = useState("2560x1440");
  const [imageWidth, setImageWidth] = useState(2560);
  const [imageHeight, setImageHeight] = useState(1440);

  // Render Workflow states
  const [workflowId, setWorkflowId] = useState("");
  const [workflowsCollapsed, setWorkflowsCollapsed] = useState(true);
  const [promptPrefix, setPromptPrefix] = useState("masterpiece, best quality, ultra-detailed, photorealistic, cinematic volumetric lighting, warm color palette, amber glow");
  const [testImagePrompt, setTestImagePrompt] = useState("a futuristic robot walking through a warm cinematic city street");
  const [testImageUrl, setTestImageUrl] = useState<string | null>(null);
  const [testImageError, setTestImageError] = useState<string | null>(null);
  const [testingImage, setTestingImage] = useState(false);
  const [savingPromptPrefix, setSavingPromptPrefix] = useState(false);
  const [presetNameDraft, setPresetNameDraft] = useState("");
  const [presetMenuOpen, setPresetMenuOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [reviewConfirmed, setReviewConfirmed] = useState(false);
  const [wizardStep, setWizardStep] = useState<WizardStepId>("content");
  const [expertMode, setExpertMode] = useState(false);
  const [showAdvancedProduction, setShowAdvancedProduction] = useState(false);
  const [showAdvancedKeywords, setShowAdvancedKeywords] = useState(false);
  const [draftSavedAt, setDraftSavedAt] = useState<string | null>(null);
  const [reuseSourceTaskId, setReuseSourceTaskId] = useState<string | null>(null);
  const [reuseAssetsEnabled, setReuseAssetsEnabled] = useState(false);
  const [showDraftBanner, setShowDraftBanner] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [deletePresetConfirmOpen, setDeletePresetConfirmOpen] = useState(false);
  const [showCreateTip, setShowCreateTip] = useState(() => !isCreateTipDismissed());
  const [lastBatchSummary, setLastBatchSummary] = useState<{
    total: number;
    success: number;
    failed: number;
    at: string;
  } | null>(null);
  const draftReadyRef = React.useRef(false);
  const draftRecoveredRef = React.useRef(false);
  const reviewReadyRef = React.useRef(false);
  const submissionLockRef = React.useRef(false);
  const suppressInitialReviewResetRef = React.useRef(false);
  const keywordRequestIdRef = React.useRef(0);
  const safeTtsDefaultAppliedRef = React.useRef(false);

  const bgmOptions = resources.bgm;
  const workflowOptions = resources.workflows;
  const fontOptions = resources.fonts || [];
  const selectedBgm = bgmOptions.find((item) => item.id === bgm);
  const effectiveReuseSourceTaskId =
    reuseAssetsEnabled ? (reuseSourceTaskId || latestCompletedTaskId || null) : null;
  const lastAppliedPresetId = React.useRef<string | null>(null);

  const normalizeSubtitleStyle = (value?: Partial<SubtitleStyle>): SubtitleStyle => ({
    ...DEFAULT_SUBTITLE_STYLE,
    ...(value || {}),
    fontSize: clampNumber(value?.fontSize, 80, 12, 120),
    outlineWidth: clampNumber(value?.outlineWidth, 0, 0, 12),
    shadow: clampNumber(value?.shadow, 0, 0, 12),
    marginV: clampNumber(value?.marginV, 200, 0, 600),
    alignment: clampNumber(value?.alignment, 2, 1, 9),
    maxCharsPerLine: clampNumber(value?.maxCharsPerLine, 20, 4, 40),
    maxLines: clampNumber(value?.maxLines, 1, 1, 4),
    highlightScale: clampNumber(value?.highlightScale, 125, 100, 180),
    backgroundOpacity: clampNumber(value?.backgroundOpacity, 72, 0, 100),
    fadeInMs: clampNumber(value?.fadeInMs, 120, 0, 1000),
    fadeOutMs: clampNumber(value?.fadeOutMs, 120, 0, 1000),
    segmentMode: value?.segmentMode && ["line", "sentence", "phrase"].includes(value.segmentMode)
      ? value.segmentMode
      : "sentence",
    keywordColors: value?.keywordColors && typeof value.keywordColors === "object"
      ? value.keywordColors
      : {},
  });

  React.useEffect(() => {
    try {
      const raw = localStorage.getItem(QUICK_CREATE_DRAFT_KEY);
      if (raw) {
        const draft = JSON.parse(raw);
        if (draft?.version === 1) {
          draftRecoveredRef.current = true;
          if (["ai", "manual", "batch"].includes(draft.mode)) setMode(draft.mode);
          if (typeof draft.title === "string") setTitle(draft.title);
          if (typeof draft.aiTopic === "string") setAiTopic(draft.aiTopic);
          if (typeof draft.copyDraft === "string") setCopyDraft(draft.copyDraft);
          if (typeof draft.batchInput === "string") {
            setBatchInput(draft.batchInput);
            setBatchCount(draft.batchInput.split("\n").filter((line: string) => line.trim()).length);
          }
          if (
            Array.isArray(draft.scenes) &&
            draft.scenes.every(
              (scene: unknown) =>
                Boolean(scene) &&
                typeof scene === "object" &&
                typeof (scene as { id?: unknown }).id === "number" &&
                typeof (scene as { ttsText?: unknown }).ttsText === "string" &&
                typeof (scene as { visualPrompt?: unknown }).visualPrompt === "string",
            )
          ) {
            setScenes(draft.scenes);
          }
          if (typeof draft.aiSceneCount === "number") {
            setAiSceneCount(clampSceneCount(draft.aiSceneCount));
            setAiSceneCountTouched(true);
          }
          if (typeof draft.aiSceneCountTouched === "boolean") setAiSceneCountTouched(draft.aiSceneCountTouched);
          if (typeof draft.suggestedSceneCount === "number") {
            setSuggestedSceneCount(clampSceneCount(draft.suggestedSceneCount));
          }
          if (["full", "segmented"].includes(draft.copyDraftMode)) setCopyDraftMode(draft.copyDraftMode);
          if (typeof draft.copyCharCount === "number") {
            setCopyCharCount(draft.copyCharCount);
            setCopyCharCountTouched(true);
          }
          if (["around", "within"].includes(draft.copyCharCountMode)) setCopyCharCountMode(draft.copyCharCountMode);
          if (["paragraph", "line", "sentence"].includes(draft.splitType)) setSplitType(draft.splitType);
          if (typeof draft.workflowId === "string") setWorkflowId(draft.workflowId);
          if (["edge", "comfyui", "minimax", "mimo"].includes(draft.ttsMode)) setTtsMode(draft.ttsMode);
          if (draft.ttsDelivery === "continuous" || draft.ttsDelivery === "per_scene") {
            setTtsDelivery(draft.ttsDelivery);
          }
          if (typeof draft.voice === "string") setVoice(draft.voice);
          if (typeof draft.speed === "number") setSpeed(draft.speed);
          if (typeof draft.minimaxModel === "string") setMinimaxModel(draft.minimaxModel);
          if (typeof draft.mimoModel === "string") setMimoModel(draft.mimoModel);
          if (typeof draft.mimoStyle === "string") setMimoStyle(draft.mimoStyle);
          if (typeof draft.emotion === "string") setEmotion(draft.emotion);
          if (typeof draft.bgm === "string") setBgm(draft.bgm);
          if (typeof draft.volume === "number") setVolume(draft.volume);
          if (typeof draft.promptPrefix === "string") setPromptPrefix(draft.promptPrefix);
          if (typeof draft.enableMotion === "boolean") setEnableMotion(draft.enableMotion);
          if (typeof draft.enableSubtitles === "boolean") setEnableSubtitles(draft.enableSubtitles);
          if (typeof draft.imageAspectRatio === "string") setImageAspectRatio(draft.imageAspectRatio);
          if (typeof draft.imageWidth === "number") setImageWidth(draft.imageWidth);
          if (typeof draft.imageHeight === "number") setImageHeight(draft.imageHeight);
          if (typeof draft.reuseSourceTaskId === "string") {
            setReuseSourceTaskId(draft.reuseSourceTaskId);
            setReuseAssetsEnabled(true);
          }
          if (typeof draft.reuseAssetsEnabled === "boolean") setReuseAssetsEnabled(draft.reuseAssetsEnabled);
          if (draft.subtitleStyle) setSubtitleStyle(normalizeSubtitleStyle(draft.subtitleStyle));
          setKeywordPreferences(normalizeKeywordPreferences(draft.keywordPreferences));
          setDraftSavedAt(typeof draft.savedAt === "string" ? draft.savedAt : null);
          setShowDraftBanner(true);
        }
      }
    } catch {
      localStorage.removeItem(QUICK_CREATE_DRAFT_KEY);
    } finally {
      draftReadyRef.current = true;
    }
  }, []);

  // Prefer MiniMax only when the service is ready and user has not restored a draft/preset yet.
  React.useEffect(() => {
    if (safeTtsDefaultAppliedRef.current || draftRecoveredRef.current) return;
    if (serviceReady?.minimax && ttsMode === "edge" && !activePreset) {
      safeTtsDefaultAppliedRef.current = true;
      setTtsMode("minimax");
      setVoice("male-qn-qingse");
    }
  }, [serviceReady?.minimax, ttsMode, activePreset]);

  React.useEffect(() => {
    if (!draftReadyRef.current) return;
    const timeoutId = window.setTimeout(() => {
      const savedAt = new Date().toISOString();
      localStorage.setItem(QUICK_CREATE_DRAFT_KEY, JSON.stringify({
        version: 1,
        savedAt,
        mode,
        title,
        aiTopic,
        aiSceneCount,
        aiSceneCountTouched,
        suggestedSceneCount,
        copyDraft,
        copyDraftMode,
        copyCharCount,
        copyCharCountMode,
        splitType,
        batchInput,
        scenes,
        workflowId,
        ttsMode,
        ttsDelivery,
        voice,
        speed,
        minimaxModel,
        emotion,
        mimoModel,
        mimoStyle,
        bgm,
        volume,
        promptPrefix,
        enableMotion,
        enableSubtitles,
        imageAspectRatio,
        imageWidth,
        imageHeight,
        reuseSourceTaskId,
        reuseAssetsEnabled,
        subtitleStyle: normalizeSubtitleStyle(subtitleStyle),
        keywordPreferences,
      }));
      setDraftSavedAt(savedAt);
    }, 500);
    return () => window.clearTimeout(timeoutId);
  }, [mode, title, aiTopic, aiSceneCount, aiSceneCountTouched, suggestedSceneCount, copyDraft, copyDraftMode, copyCharCount, copyCharCountMode, splitType, batchInput, scenes, workflowId, ttsMode, ttsDelivery, voice, speed, minimaxModel, emotion, mimoModel, mimoStyle, bgm, volume, promptPrefix, enableMotion, enableSubtitles, imageAspectRatio, imageWidth, imageHeight, subtitleStyle, reuseSourceTaskId, reuseAssetsEnabled, keywordPreferences]);

  // Invalidate the review whenever a submitted production setting changes.
  React.useEffect(() => {
    if (!reviewReadyRef.current) {
      reviewReadyRef.current = true;
      return;
    }
    if (suppressInitialReviewResetRef.current) {
      suppressInitialReviewResetRef.current = false;
      return;
    }
    setReviewConfirmed(false);
  }, [mode, title, copyDraft, copyDraftMode, aiSceneCount, splitType, batchInput, scenes, workflowId, ttsMode, ttsDelivery, voice, speed, minimaxModel, emotion, mimoModel, mimoStyle, bgm, volume, promptPrefix, enableMotion, enableSubtitles, imageWidth, imageHeight, subtitleStyle]);

  React.useEffect(() => {
    if (!copyCharCountTouched) {
      setCopyCharCount(suggestCopyCharCount(aiSceneCount));
    }
  }, [aiSceneCount, copyCharCountTouched]);

  React.useEffect(() => {
    if (workflowOptions.length === 0) return;
    if (!workflowId || !workflowOptions.some((workflow) => workflow.id === workflowId)) {
      setWorkflowId(workflowOptions[0].id);
    }
  }, [workflowOptions, workflowId]);

  React.useEffect(() => {
    if (bgm || bgmOptions.length === 0) return;
    setBgm(bgmOptions.find((item) => item.id !== "bgm-none")?.id || "bgm-none");
  }, [bgmOptions, bgm]);

  React.useEffect(() => {
    if (bgmPreviewRef.current) {
      bgmPreviewRef.current.volume = volume / 100;
    }
  }, [volume]);

  // BGM listen toggle
  const toggleBgmListen = async (selectedBgmId: string) => {
    const audio = bgmPreviewRef.current;
    if (!audio) {
      addToast("音频播放器尚未就绪。", "error");
      return;
    }

    if (playingBgm === selectedBgmId) {
      audio.pause();
      audio.currentTime = 0;
      setPlayingBgm(null);
      addToast("伴奏试听已暂停", "info");
      return;
    }

    const matchedBgm = bgmOptions.find((b) => b.id === selectedBgmId);
    if (!matchedBgm || !matchedBgm.src) {
      addToast("无法试听此类型的音频配置", "error");
      return;
    }

    audio.pause();
    audio.src = matchedBgm.src;
    audio.volume = volume / 100;
    audio.loop = true;
    audio.currentTime = 0;

    try {
      await audio.play();
      setPlayingBgm(selectedBgmId);
      addToast(`开始试听: ${matchedBgm.name}`, "success");
    } catch (err: any) {
      setPlayingBgm(null);
      addToast(err.message || "浏览器阻止了音频播放，请点击播放器播放。", "error");
    }
  };

  const handleBgmChange = (value: string) => {
    if (bgmPreviewRef.current) {
      bgmPreviewRef.current.pause();
      bgmPreviewRef.current.currentTime = 0;
    }
    setPlayingBgm(null);
    setBgm(value);
  };

  const updateSubtitleStyle = (patch: Partial<SubtitleStyle>) => {
    setSubtitleStyle((current) => ({ ...current, ...patch }));
  };

  const handleSubtitlePresetChange = (preset: SubtitleStyle["preset"]) => {
    updateSubtitleStyle({ preset, ...SUBTITLE_PRESET_STYLES[preset] });
  };

  const dynamicSubtitleEnabled = subtitleStyle.mode === "hyperframes";

  const handleSubtitleFontChange = (fontPath: string) => {
    const font = fontOptions.find((item) => item.path === fontPath);
    updateSubtitleStyle({
      fontPath,
      fontFamily: font?.name || "",
    });
  };

  const keywordSourceText = () => {
    if (mode === "batch") {
      return batchInput
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .slice(0, 8)
        .join("\n");
    }
    if (copyDraft.trim()) return copyDraft.trim();
    if (scenes.length) {
      return scenes.map((scene) => scene.ttsText || "").filter(Boolean).join("\n");
    }
    return aiTopic.trim() || title.trim();
  };

  const applyHighlightKeywords = (
    words: string[],
    colors?: Record<string, string>,
  ) => {
    const nextWords = Array.from(new Set(words.map((w) => w.trim()).filter(Boolean))).slice(0, 24);
    const nextColors: Record<string, string> = {};
    for (const word of nextWords) {
      nextColors[word] =
        colors?.[word] ||
        subtitleStyle.keywordColors?.[word] ||
        subtitleStyle.accentColor ||
        "#FFD43B";
    }
    updateSubtitleStyle({ highlightWords: nextWords, keywordColors: nextColors });
    const nextKeys = new Set(nextWords.map((word) => word.toLocaleLowerCase()));
    setAiKeywordSuggestions((current) => current.filter((item) => !nextKeys.has(item.word.toLocaleLowerCase())));
  };

  const updateKeywordPreferences = (patch: Partial<KeywordPreferences>) => {
    keywordRequestIdRef.current += 1;
    setKeywordPreferences((current) => ({ ...current, ...patch }));
    setKeywordStatus(aiKeywordSuggestions.length ? "stale" : "idle");
  };

  const applyKeywordSuggestions = (suggestions: KeywordSuggestion[]) => {
    const currentWords = subtitleStyle.highlightWords || [];
    const currentKeys = new Set(currentWords.map((word) => word.toLocaleLowerCase()));
    const additions = suggestions
      .filter((item) => !currentKeys.has(item.word.toLocaleLowerCase()))
      .slice(0, Math.max(0, 24 - currentWords.length));
    if (!additions.length) {
      addToast(currentWords.length >= 24 ? "最多支持 24 个高亮词。" : "这些关键词已经添加。", "info");
      return;
    }
    applyHighlightKeywords(
      [...currentWords, ...additions.map((item) => item.word)],
      Object.fromEntries(additions.map((item) => [item.word, item.color])),
    );
    const applied = new Set(additions.map((item) => item.word.toLocaleLowerCase()));
    setAiKeywordSuggestions((current) => current.filter((item) => !applied.has(item.word.toLocaleLowerCase())));
  };

  const requestKeywordSuggestions = async (text: string, replaceBatch = false) => {
    const source = text.trim();
    if (!source) {
      addToast("请先填写旁白或主题，再提取高亮词。", "error");
      return;
    }
    const requestId = ++keywordRequestIdRef.current;
    setKeywordStatus("loading");
    try {
      const selectedWords = subtitleStyle.highlightWords || [];
      const avoidWords = replaceBatch
        ? [...selectedWords, ...aiKeywordSuggestions.map((item) => item.word)]
        : selectedWords;
      const keywords = await extractHighlightKeywords(source, {
        maxKeywords: KEYWORD_DENSITY_LIMIT[keywordPreferences.density],
        style: keywordPreferences.style,
        density: keywordPreferences.density,
        avoidWords,
      });
      if (requestId !== keywordRequestIdRef.current) return;
      const selectedKeys = new Set(selectedWords.map((word) => word.toLocaleLowerCase()));
      setAiKeywordSuggestions(keywords.filter((item) => !selectedKeys.has(item.word.toLocaleLowerCase())));
      setKeywordSourceSnapshot(source);
      setKeywordStatus("ready");
      if (!keywords.length) addToast("没有找到更多可用高亮词。", "info");
    } catch (err: any) {
      if (requestId !== keywordRequestIdRef.current) return;
      setKeywordStatus("error");
      addToast(err.message || "高亮词提取失败。", "error");
    }
  };

  const handleExtractKeywords = () => requestKeywordSuggestions(keywordSourceText());

  const handleSwapKeywordSuggestions = () => requestKeywordSuggestions(keywordSourceText(), true);

  const handleCopyDraftChange = (value: string) => {
    keywordRequestIdRef.current += 1;
    setCopyDraft(value);
    if (!value.trim()) {
      setAiKeywordSuggestions([]);
      setKeywordStatus("idle");
    } else if (
      keywordStatus === "loading" ||
      (keywordSourceSnapshot && value.trim() !== keywordSourceSnapshot)
    ) {
      setKeywordStatus("stale");
    }
  };

  const renderSelectedKeywordEditor = () => (
    <div className="space-y-1.5">
      <label className="block">
        <span className="block text-[10px] text-zinc-500 mb-1">已选高亮词（逗号分隔）</span>
        <textarea
          value={(subtitleStyle.highlightWords || []).join("，")}
          onChange={(e) => applyHighlightKeywords(parseHighlightWords(e.target.value))}
          rows={2}
          placeholder="例如：表达力，重点"
          className="w-full resize-y min-h-16 max-h-32 bg-[#101114] border border-zinc-900 rounded px-2.5 py-2 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
        />
      </label>
      {(subtitleStyle.highlightWords || []).length > 0 && (
        <div className="space-y-1.5">
          {(subtitleStyle.highlightWords || []).map((word) => (
            <div key={word} className="flex items-center gap-2 rounded border border-zinc-800 bg-[#0c0d10] px-2 py-1.5">
              <span
                className="min-w-0 flex-1 truncate text-xs font-semibold"
                style={{ color: subtitleStyle.keywordColors?.[word] || subtitleStyle.accentColor }}
              >
                {word}
              </span>
              <input
                type="color"
                value={subtitleStyle.keywordColors?.[word] || subtitleStyle.accentColor || "#FFD43B"}
                onChange={(e) => updateSubtitleStyle({ keywordColors: { ...(subtitleStyle.keywordColors || {}), [word]: e.target.value } })}
                className="h-7 w-10 cursor-pointer rounded border border-zinc-800 bg-transparent p-0.5"
                title={`${word} 颜色`}
              />
              <button
                type="button"
                onClick={() => {
                  const nextWords = (subtitleStyle.highlightWords || []).filter((item) => item !== word);
                  const nextColors = { ...(subtitleStyle.keywordColors || {}) };
                  delete nextColors[word];
                  updateSubtitleStyle({ highlightWords: nextWords, keywordColors: nextColors });
                }}
                className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
                title="移除"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const openCustomBgmFolder = async () => {
    try {
      const response = await fetch("/api/resources/bgm/select-folder", { method: "POST" });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(
          formatApiErrorValue(data.detail) ||
          formatApiErrorValue(data.error) ||
          "无法选择自定义音乐文件夹。",
        );
      }
      await onRefreshResources();
      addToast("已保存自定义音乐文件夹，音乐列表已刷新。", "success");
    } catch (err: any) {
      addToast(err.message || "无法选择自定义音乐文件夹。", "error");
    }
  };

  const openCustomFontFolder = async () => {
    try {
      const response = await fetch("/api/resources/fonts/select-folder", { method: "POST" });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(
          formatApiErrorValue(data.detail) ||
          formatApiErrorValue(data.error) ||
          "无法选择自定义字体文件夹。",
        );
      }
      await onRefreshResources();
      addToast("已保存自定义字体文件夹，字体列表已刷新。", "success");
    } catch (err: any) {
      addToast(err.message || "无法选择自定义字体文件夹。", "error");
    }
  };

  const refreshFonts = async () => {
    try {
      await onRefreshResources();
      addToast("字体列表已刷新", "success");
    } catch (err: any) {
      addToast(err?.message || "刷新字体失败", "error");
    }
  };

  const audioPathToUrl = (audioPath: string) => {
    if (/^https?:\/\//.test(audioPath)) return audioPath;
    return `/api/files/${audioPath}`;
  };

  const mediaPathToUrl = (mediaPath: string) => {
    if (/^(https?:|data:|blob:)/.test(mediaPath)) return mediaPath;
    const normalizedPath = mediaPath.replace(/\\/g, "/");
    return `/api/files/${normalizedPath}`;
  };

  const applyImageSizePreset = (presetId: string) => {
    setImageAspectRatio(presetId);
    const preset = IMAGE_SIZE_PRESETS.find((item) => item.id === presetId);
    if (preset && preset.id !== "custom") {
      setImageWidth(preset.width);
      setImageHeight(preset.height);
    }
  };

  const handleTestImageGenerate = async () => {
    if (!testImagePrompt.trim()) {
      addToast("请先填写测试出图提示词。", "error");
      return;
    }

    const mergedPrompt = [promptPrefix.trim(), testImagePrompt.trim()]
      .filter(Boolean)
      .join(", ");

    setTestingImage(true);
    setTestImageError(null);
    setTestImageUrl(null);
    addToast("正在根据当前画风参数测试出图...", "info");

    try {
      const response = await fetch("/api/image/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: mergedPrompt,
          width: imageWidth,
          height: imageHeight,
          workflow: workflowId || undefined,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(formatApiErrorValue(data.detail) || formatApiErrorValue(data.error) || "测试出图失败，请检查图像生成服务配置。");
      }
      setTestImageUrl(mediaPathToUrl(data.image_path));
      addToast("测试图已生成。", "success");
    } catch (err: any) {
      const message = err.message || "测试出图失败，请检查 ComfyUI / RunningHub / 图像 API 配置。";
      setTestImageError(message);
      addToast(message, "error");
    } finally {
      setTestingImage(false);
    }
  };

  const handleSavePromptPrefix = async () => {
    setSavingPromptPrefix(true);
    try {
      const savedPromptPrefix = await onSavePromptPrefix(promptPrefix);
      if (typeof savedPromptPrefix === "string") {
        setPromptPrefix(savedPromptPrefix);
      }
    } catch (err: any) {
      addToast(err.message || "提示词保存失败，请检查后端配置服务。", "error");
    } finally {
      setSavingPromptPrefix(false);
    }
  };

  // TTS Speak Preview
  const handlePreviewTts = async () => {
    if (!previewTtsText.trim()) {
      addToast("请先填写试听文案。", "error");
      return;
    }

    setPreviewingTts(true);
    setPreviewTtsAudioUrl(null);
    const previewInferenceMode = ttsMode === "edge" ? "local" : ttsMode;
    const previewServiceName = ttsMode === "minimax" ? "MiniMax" : ttsMode === "mimo" ? "MiMo" : ttsMode === "comfyui" ? "ComfyUI" : "Edge";
    addToast(`正在生成 ${previewServiceName} TTS 试听音频...`, "info");

    try {
      const response = await fetch("/api/tts/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: previewTtsText,
          inference_mode: previewInferenceMode,
          voice_id: voice,
          speed,
          minimax_model: ttsMode === "minimax" ? minimaxModel : undefined,
          minimax_emotion: ttsMode === "minimax" ? emotion || undefined : undefined,
          mimo_model: ttsMode === "mimo" ? mimoModel : undefined,
          mimo_style: ttsMode === "mimo" ? mimoStyle || undefined : undefined,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(formatApiErrorValue(data.detail) || formatApiErrorValue(data.error) || `${previewServiceName} TTS 试听生成失败。`);
      }
      const audioUrl = audioPathToUrl(data.audio_path);
      setPreviewTtsAudioUrl(audioUrl);
      addToast(`${previewServiceName} TTS 试听音频已生成。`, "success");

      const audio = new Audio(audioUrl);
      audio.play().catch(() => {
        addToast("试听音频已生成，请点击播放器播放。", "info");
      });
    } catch (err: any) {
      addToast(err.message || "TTS 试听生成失败。", "error");
    } finally {
      setPreviewingTts(false);
    }
  };

  const getCurrentCopyForTts = () => {
    const sceneTexts = scenes.map((scene) => scene.ttsText).map((text) => text.trim()).filter(Boolean);
    const draftText = copyDraft.trim();

    if (mode === "manual" && sceneTexts.length > 0) {
      return {
        text: sceneTexts.join("\n"),
        label: `${sceneTexts.length} 段分镜旁白`,
      };
    }

    if (mode === "ai" && draftText) {
      return {
        text: draftText,
        label: copyDraftMode === "segmented" ? "分镜旁白草稿" : "完整口播稿",
      };
    }

    return {
      text: "",
      label: "暂无可合成文案",
    };
  };

  const formatCopyTtsDuration = (duration: number | null) => {
    if (!duration || !Number.isFinite(duration)) return "--:--";
    const minutes = Math.floor(duration / 60);
    const seconds = Math.round(duration % 60);
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  };

  const handleSynthesizeCurrentCopy = async () => {
    const currentCopy = getCurrentCopyForTts();

    if (!currentCopy.text.trim()) {
      addToast("请先生成或填写当前文案，再合成音频。", "error");
      return;
    }

    setSynthesizingCopy(true);
    setCopyTtsAudioUrl(null);
    setCopyTtsDuration(null);
    setCopyTtsSourceLabel(currentCopy.label);

    const copyInferenceMode = ttsMode === "edge" ? "local" : ttsMode;
    const copyServiceName = ttsMode === "minimax" ? "MiniMax" : ttsMode === "mimo" ? "MiMo" : ttsMode === "comfyui" ? "ComfyUI" : "Edge";
    addToast(`正在合成 ${copyServiceName} 当前文案音频...`, "info");

    try {
      const response = await fetch("/api/tts/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: currentCopy.text,
          inference_mode: copyInferenceMode,
          voice_id: voice,
          speed,
          minimax_model: ttsMode === "minimax" ? minimaxModel : undefined,
          minimax_emotion: ttsMode === "minimax" ? emotion || undefined : undefined,
          mimo_model: ttsMode === "mimo" ? mimoModel : undefined,
          mimo_style: ttsMode === "mimo" ? mimoStyle || undefined : undefined,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(formatApiErrorValue(data.detail) || formatApiErrorValue(data.error) || `${copyServiceName} 当前文案合成失败。`);
      }

      setCopyTtsAudioUrl(audioPathToUrl(data.audio_path));
      setCopyTtsDuration(typeof data.duration === "number" ? data.duration : null);
      addToast(`${copyServiceName} 当前文案音频已生成。`, "success");
    } catch (err: any) {
      addToast(err.message || "当前文案音频合成失败。", "error");
    } finally {
      setSynthesizingCopy(false);
    }
  };

  // Apply Preset
  React.useEffect(() => {
    if (activePreset) {
      if (draftRecoveredRef.current && lastAppliedPresetId.current === null) {
        lastAppliedPresetId.current = activePreset.id;
        setPresetNameDraft(activePreset.name);
        return;
      }
      if (lastAppliedPresetId.current === activePreset.id) {
        setPromptPrefix(activePreset.promptPrefix);
        setPresetNameDraft(activePreset.name);
        setSubtitleStyle(normalizeSubtitleStyle(activePreset.subtitleStyle));
        return;
      }

      lastAppliedPresetId.current = activePreset.id;
      if (!draftRecoveredRef.current) suppressInitialReviewResetRef.current = true;
      setPresetNameDraft(activePreset.name);
      setTtsMode(activePreset.ttsMode);
      setVoice(activePreset.voice);
      setSpeed(activePreset.speed);
      setWorkflowId(activePreset.workflow);
      setBgm(activePreset.bgm);
      setVolume(activePreset.bgmVolume);
      setPromptPrefix(activePreset.promptPrefix);
      setSplitType(activePreset.splitType);
      if (activePreset.enableMotion !== undefined) setEnableMotion(activePreset.enableMotion);
      if (activePreset.enableSubtitles !== undefined) setEnableSubtitles(activePreset.enableSubtitles);
      setSubtitleStyle(normalizeSubtitleStyle(activePreset.subtitleStyle));
      setMinimaxModel(activePreset.minimaxModel || "speech-2.8-turbo");
      setEmotion(activePreset.emotion || "");
      setMimoModel(activePreset.mimoModel || "mimo-v2.5-tts");
      setMimoStyle(activePreset.mimoStyle || "");
      if (activePreset.sceneCount) {
        setAiSceneCount(clampSceneCount(activePreset.sceneCount));
        setAiSceneCountTouched(true);
      }
      if (activePreset.copyCharCount) {
        setCopyCharCount(activePreset.copyCharCount);
        setCopyCharCountTouched(true);
      }
      if (activePreset.copyCharCountMode) setCopyCharCountMode(activePreset.copyCharCountMode);
      if (activePreset.copyDraftMode) setCopyDraftMode(activePreset.copyDraftMode);
      if (activePreset.mediaWidth) setImageWidth(activePreset.mediaWidth);
      if (activePreset.mediaHeight) setImageHeight(activePreset.mediaHeight);
      if (activePreset.imageAspectRatio) setImageAspectRatio(activePreset.imageAspectRatio);
      addToast(`已成功应用预设: ${activePreset.name}`, "success");
    }
  }, [activePreset]);

  const maybeSyncCopyDraftToPreviewTts = (draftText: string) => {
    const previewSentence = extractPreviewSentenceFromCopyDraft(draftText);
    if (!previewSentence) return;

    setPreviewTtsText((currentText) => {
      const canAutoFill =
        !previewTtsTextUserEditedRef.current ||
        !currentText.trim() ||
        currentText === DEFAULT_PREVIEW_TTS_TEXT ||
        currentText === autoPreviewTtsTextRef.current;

      if (!canAutoFill) return currentText;

      autoPreviewTtsTextRef.current = previewSentence;
      previewTtsTextUserEditedRef.current = false;
      return previewSentence;
    });
  };

  /**
   * Step 2 after pure copy: rule-based semantic + rhythm recommendation.
   * Does not call LLM; optional auto-adopt when the user has not locked scene count.
   */
  const reanalyzeStoryboardFromCopy = (
    draftText: string,
    options?: { adoptIfUnlocked?: boolean; toastOnResult?: boolean; draftJustGenerated?: boolean },
  ) => {
    const text = String(draftText || "").trim();
    if (!text) {
      setSuggestedSceneCount(null);
      setRhythmSceneCount(null);
      return null;
    }
    const continuousTts = String(ttsDelivery || "").toLowerCase() === "continuous";
    const rule: DraftSplitType = copyDraftMode === "segmented" ? "line" : splitType;
    // continuous: no soft comma-expand (avoids mid-sentence holds)
    const softExpand = copyDraftMode === "full" && !continuousTts;
    const analysis = analyzeStoryboardRecommendation(text, rule, { softExpand });
    setSuggestedSceneCount(analysis.semantic);
    setRhythmSceneCount(analysis.rhythm);

    const adopt = options?.adoptIfUnlocked !== false && !aiSceneCountTouched;
    if (adopt) {
      setAiSceneCount(analysis.preferred);
    }

    if (options?.toastOnResult) {
      const prefix = options?.draftJustGenerated ? "AI 文案草稿已生成。" : "分镜分析完成。";
      if (adopt) {
        addToast(
          `${prefix}语义建议 ${analysis.semantic} 镜（已填入）· 节奏约 ${analysis.rhythm} 镜（${analysis.charCount} 字）`,
          "success",
        );
      } else {
        addToast(
          `${prefix}语义建议 ${analysis.semantic} 镜 · 节奏约 ${analysis.rhythm} 镜（你已锁定分镜数 ${aiSceneCount}）`,
          "success",
        );
      }
    }
    return analysis;
  };

  const handleGenerateCopyDraft = async () => {
    if (!aiTopic.trim()) {
      addToast("请输入创作主题，以便 AI 生成文案草稿", "error");
      return;
    }

    keywordRequestIdRef.current += 1;
    setCopyDraftLoading(true);
    addToast(
      copyDraftMode === "full" ? "AI 正在生成口播稿草稿..." : "AI 正在生成分镜旁白草稿...",
      "info"
    );

    try {
      const response = await fetch("/api/generate-copy-draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: aiTopic,
          sceneCount: aiSceneCount,
          draftMode: copyDraftMode,
          targetCharCount: copyCharCount,
          charCountMode: copyCharCountMode,
          splitType,
        }),
      });
      const resData = await response.json();
      if (response.ok && resData.success) {
        const draftText = resData.draftText || "";
        setCopyDraft(draftText);
        setAiKeywordSuggestions([]);
        setKeywordSourceSnapshot("");
        setKeywordStatus("idle");
        // Step 2: rule-based semantic + rhythm recommendation (no second LLM rewrite).
        const analysis = reanalyzeStoryboardFromCopy(draftText, {
          adoptIfUnlocked: true,
          toastOnResult: true,
          draftJustGenerated: true,
        });
        if (!analysis) {
          addToast("AI 文案草稿已生成。", "success");
        }
        maybeSyncCopyDraftToPreviewTts(draftText);
        if (keywordPreferences.autoExtract) void requestKeywordSuggestions(draftText);
      } else {
        addToast(formatApiErrorValue(resData.detail) || formatApiErrorValue(resData.error) || "文案草稿生成异常，请检查 LLM 设置。", "error");
      }
    } catch (err: any) {
      const detail = err?.message || String(err || "");
      addToast(
        detail.includes("Failed to fetch") || detail.includes("NetworkError") || detail.includes("fetch")
          ? "无法连接后端服务，请确认 http://127.0.0.1:8000 已启动后重试。"
          : `生成文案失败：${detail || "网络或服务器异常"}`,
        "error",
      );
    } finally {
      setCopyDraftLoading(false);
    }
  };

  // AI Generation fetch via Gemini API route
  const handleAIGenerateScript = async () => {
    if (!aiTopic.trim()) {
      addToast("请输入创作主题，以便 AI 生成分镜脚本", "error");
      return;
    }
    if (!copyDraft.trim()) {
      addToast("请先生成或填写确认文案，再生成 AI 分镜脚本。", "error");
      return;
    }
    setAiLoading(true);
    addToast("大模型正在基于确认文案生成分镜脚本，请稍候...", "info");

    try {
      const response = await fetch("/api/generate-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: aiTopic,
          confirmedText: copyDraft.trim(),
          draftMode: copyDraftMode,
          sceneCount: aiSceneCount,
          splitType,
          ttsDelivery,
        }),
      });
      const resData = await response.json();
      if (response.ok && resData.success) {
        // Transform incoming data into scenes list
        const generated = resData.data.map((item: any) => ({
          id: item.id,
          ttsText: item.ttsText,
          visualPrompt: item.visualPrompt,
        }));
        setScenes(generated);
        setMode("manual"); // switch to manual scene editor so user can review and edit
        const actualCount = generated.length;
        setSuggestedSceneCount(actualCount);
        if (!aiSceneCountTouched) {
          setAiSceneCount(clampSceneCount(actualCount));
        }
        addToast(
          `AI 分镜脚本生成就绪！已按语义切成 ${actualCount} 个分镜，您可直接在下方编辑或点击渲染。`,
          "success",
        );
      } else {
        addToast(formatApiErrorValue(resData.detail) || formatApiErrorValue(resData.error) || "脚本构思异常，请检查 LLM 设置。", "error");
      }
    } catch (err: any) {
      const detail = err?.message || String(err || "");
      addToast(
        detail.includes("Failed to fetch") || detail.includes("NetworkError") || detail.includes("fetch")
          ? "无法连接后端服务，请确认 http://127.0.0.1:8000 已启动后重试。"
          : `生成分镜脚本失败：${detail || "网络或服务器异常"}`,
        "error",
      );
    } finally {
      setAiLoading(false);
    }
  };

  // Scene CRUD
  const addScene = () => {
    const newId = scenes.length > 0 ? Math.max(...scenes.map((s) => s.id)) + 1 : 1;
    setScenes([...scenes, { id: newId, ttsText: "", visualPrompt: "" }]);
  };

  const removeScene = (id: number) => {
    setScenes(scenes.filter((s) => s.id !== id));
  };

  const updateScene = (id: number, key: "ttsText" | "visualPrompt", value: string) => {
    setScenes(scenes.map((s) => (s.id === id ? { ...s, [key]: value } : s)));
  };

  const buildScenesForRender = () => {
    if (mode === "manual") {
      return scenes.map((scene) => ({
        id: scene.id,
        ttsText: scene.ttsText.trim(),
        visualPrompt: scene.visualPrompt,
      }));
    }

    if (mode === "ai") {
      const draftText = copyDraft.trim();
      if (!draftText) return [];

      // segmented drafts are already one narration per line; full drafts use splitType.
      // packSemanticUnits merges when too many, keeps intact when fewer than target (no char-slice).
      // continuous TTS: disable soft comma-expand — clause-level clips + hold = mid-sentence pause.
      const rule: DraftSplitType = copyDraftMode === "segmented" ? "line" : splitType;
      const continuousTts = String(ttsDelivery || "").toLowerCase() === "continuous";
      const draftSegments = buildStoryboardNarrations(draftText, rule, aiSceneCount, {
        softExpand: copyDraftMode === "full" && !continuousTts,
      });

      return draftSegments.map((ttsText, index) => ({
        id: index + 1,
        ttsText,
        visualPrompt: "",
      }));
    }

    return batchInput
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .map((ttsText, index) => ({
        id: index + 1,
        ttsText,
        visualPrompt: "",
      }));
  };

  const buildBatchTaskInputs = (
    baseTaskInput: any,
    renderScenes: ReturnType<typeof buildScenesForRender>,
    requestGroupKey: string,
  ) =>
    renderScenes.map((scene, index) => {
      const topicLabel = scene.ttsText.replace(/^主题\s*[一二三四五六七八九十\d]+\s*[:：]\s*/u, "").trim();
      return {
        ...baseTaskInput,
        title: `${title.trim()} · ${topicLabel.slice(0, 28) || `主题 ${index + 1}`}`,
        scenes: [{ ...scene, id: 1 }],
        batchIndex: index + 1,
        batchSize: renderScenes.length,
        clientRequestKey: `${requestGroupKey}-${index + 1}`,
      };
    });

  const scrollToField = (anchorId: string) => {
    window.requestAnimationFrame(() => {
      document.getElementById(anchorId)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };

  const validateBeforeSubmit = (renderScenes: ReturnType<typeof buildScenesForRender>): FieldErrors => {
    const errors: FieldErrors = {};
    if (!title.trim()) {
      errors.title = "请填写项目标题";
    }
    if (mode === "ai" && renderScenes.length === 0) {
      errors.content = "请先生成或填写文案，再开始生成";
    } else if (mode === "manual" && renderScenes.some((s) => !s.ttsText.trim())) {
      errors.content = "请完善每一个分镜的旁白文本";
    } else if (renderScenes.length === 0) {
      errors.content = "没有可用于生成的文案内容";
    }
    if (ttsMode === "minimax" && serviceReady && !serviceReady.minimax) {
      errors.tts = "MiniMax 未配置，请前往设置填写 Key，或改用 Edge 配音";
    }
    if (ttsMode === "mimo" && serviceReady && !serviceReady.mimo) {
      errors.tts = "MiMo 未配置，请前往设置填写 Key，或改用 Edge 配音";
    }
    if (
      ttsMode === "mimo" &&
      String(mimoModel || "").includes("voicedesign") &&
      !String(mimoStyle || "").trim()
    ) {
      errors.tts = "Voice Design 模式请填写音色设计描述（全片共用）";
    }
    if (!reviewConfirmed) {
      errors.review = "请勾选下方确认项后再提交";
    }
    return errors;
  };

  const clearLocalDraft = () => {
    localStorage.removeItem(QUICK_CREATE_DRAFT_KEY);
    setShowDraftBanner(false);
    setDraftSavedAt(null);
    setTitle("新品发布创意科技短视频");
    setAiTopic("探索未来世界的智能机器人生活碎片");
    setCopyDraft("");
    setAiSceneCount(5);
    setAiSceneCountTouched(false);
    setSuggestedSceneCount(null);
    setRhythmSceneCount(null);
    setScenes([
      { id: 1, ttsText: "这是一个科技感爆棚的高能概念画卷。", visualPrompt: "Cinematic digital art of high-tech lab, warm amber lighting, futuristic, 4k" },
      { id: 2, ttsText: "每一个齿轮的咬合，都是精工美学的体现。", visualPrompt: "Macro close-up of amber golden machine gears interlocking in motion, cinematic depth of field" },
    ]);
    setBatchInput("主题一: 智能机器人在雨夜撑伞\n主题二: 机械宠物狗在客厅嬉戏\n主题三: 未来城市空中飞车速递");
    setReviewConfirmed(false);
    setReuseAssetsEnabled(false);
    setReuseSourceTaskId(null);
    setFieldErrors({});
    addToast("已清空本地草稿，可重新开始。", "info");
  };

  // Trigger main generator callback
  const handleTriggerRender = async (directGenerate = false) => {
    if (submissionLockRef.current) return;
    submissionLockRef.current = true;
    try {
      const renderScenes = buildScenesForRender();
      const errors = validateBeforeSubmit(renderScenes);
      setFieldErrors(errors);
      if (Object.keys(errors).length > 0) {
        if (errors.title) scrollToField("stage-content");
        else if (errors.content) scrollToField("stage-storyboard");
        else if (errors.tts) scrollToField("stage-voice");
        else if (errors.review) scrollToField("stage-review");
        addToast(Object.values(errors)[0] || "请先完善必填项", "error");
        return;
      }

      // Soft guidance when multi-scene Voice Design still uses per-scene delivery.
      if (
        ttsMode === "mimo" &&
        String(mimoModel || "").includes("voicedesign") &&
        renderScenes.length > 1 &&
        ttsDelivery === "per_scene"
      ) {
        addToast(
          `当前 ${renderScenes.length} 个分镜将逐段合成 Voice Design 配音，音色可能有轻微漂移。建议改用「整篇连续合成」或预设音色。`,
          "info",
        );
      }

      const taskInput = {
        title,
        tabType: "quick-create",
        workflowId,
        ttsMode,
        ttsDelivery,
        voice,
        speed,
        minimaxModel,
        emotion: emotion || undefined,
        mimoModel,
        mimoStyle: mimoStyle || undefined,
        mediaWidth: imageWidth,
        mediaHeight: imageHeight,
        bgm,
        bgmVolume: volume,
        promptPrefix,
        enableMotion,
        enableSubtitles,
        subtitleStyle,
        splitType,
        reuseTaskId: mode === "batch" ? undefined : effectiveReuseSourceTaskId,
        scenes: renderScenes,
      };

      if (mode !== "batch" && onCreateProject && !directGenerate) {
        setIsSubmitting(true);
        try {
          await onCreateProject({
            ...taskInput,
            scenes: renderScenes.map((scene) => ({
              ...scene,
              visualPrompt: scene.visualPrompt.trim() || scene.ttsText,
            })),
          });
          setReviewConfirmed(false);
          setFieldErrors({});
        } finally {
          setIsSubmitting(false);
        }
        return;
      }

      const requestGroupKey = crypto.randomUUID();
      setIsSubmitting(true);
      onOpenConsole?.();
      try {
        if (mode === "batch") {
          const taskInputs = buildBatchTaskInputs(taskInput, renderScenes, requestGroupKey);
          let successfulSubmissions = 0;
          await runWithConcurrency(taskInputs, 3, async (item) => {
            if (await onGenerateTask(item)) successfulSubmissions += 1;
          });
          const failedSubmissions = taskInputs.length - successfulSubmissions;
          setLastBatchSummary({
            total: taskInputs.length,
            success: successfulSubmissions,
            failed: failedSubmissions,
            at: new Date().toISOString(),
          });
          if (failedSubmissions > 0) {
            addToast(
              `批量提交完成：成功 ${successfulSubmissions} 个，失败 ${failedSubmissions} 个。请在右侧任务面板查看失败原因。`,
              "error",
            );
          } else {
            addToast(`已提交 ${successfulSubmissions} 个独立视频任务，可在右侧任务面板查看进度。`, "success");
          }
          if (successfulSubmissions === 0) return;
        } else {
          const submittedTaskId = await onGenerateTask({ ...taskInput, clientRequestKey: requestGroupKey });
          if (!submittedTaskId) return;
          setReuseSourceTaskId(submittedTaskId);
          addToast("任务已提交，请在右侧任务面板查看进度与结果。", "info");
        }
        setReviewConfirmed(false);
        setFieldErrors({});
      } finally {
        setIsSubmitting(false);
      }
    } finally {
      submissionLockRef.current = false;
    }
  };

  const buildWorkbenchPreset = (name: string): Omit<Preset, "id"> => ({
      name,
      ttsMode,
      ttsDelivery,
      voice,
      speed,
      workflow: workflowId,
      bgm,
      bgmVolume: volume,
      promptPrefix,
      splitType,
      enableMotion,
      enableSubtitles,
      subtitleStyle,
      minimaxModel,
      emotion: emotion || undefined,
      mimoModel,
      mimoStyle: mimoStyle || undefined,
      sceneCount: aiSceneCount,
      copyCharCount,
      copyCharCountMode,
      copyDraftMode,
      mediaWidth: imageWidth,
      mediaHeight: imageHeight,
      imageAspectRatio
  });

  const getPresetName = () => {
    const fallbackName = `预设-${title.trim().slice(0, 8) || "工作台"}`;
    return presetNameDraft.trim() || activePreset?.name || fallbackName;
  };

  const handleCreatePreset = async () => {
    await onCreatePreset(buildWorkbenchPreset(getPresetName()));
    setPresetMenuOpen(false);
  };

  const handleUpdatePreset = async () => {
    if (!activePreset) {
      await handleCreatePreset();
      return;
    }
    await onUpdatePreset(activePreset.id, {
      ...activePreset,
      ...buildWorkbenchPreset(getPresetName()),
      id: activePreset.id,
    });
    setPresetMenuOpen(false);
  };

  const handleDeletePreset = async () => {
    if (!activePreset) return;
    setDeletePresetConfirmOpen(true);
    setPresetMenuOpen(false);
  };

  const confirmDeletePreset = async () => {
    if (!activePreset) return;
    await onDeletePreset(activePreset.id);
    setDeletePresetConfirmOpen(false);
  };

  const handleSetDefaultPreset = async () => {
    if (!activePreset) return;
    await onSetDefaultPreset(activePreset.id);
    setPresetMenuOpen(false);
  };

  const currentWorkflow = workflowOptions.find((w) => w.id === workflowId);
  const reviewScenes = buildScenesForRender();
  const reviewVideoCount = mode === "batch" ? reviewScenes.length : reviewScenes.length > 0 ? 1 : 0;
  const reviewSceneCount = mode === "batch" ? reviewScenes.length : reviewScenes.length;
  const reviewNarrationSeconds = estimateNarrationSeconds(
    reviewScenes.reduce((total, scene) => total + scene.ttsText.length, 0),
  );
  const averageCopyCharsPerStoryboard = Math.max(1, Math.round(copyCharCount / Math.max(aiSceneCount, 1)));
  const estimatedCopySeconds = estimateNarrationSeconds(copyCharCount);
  const currentCopyForTts = getCurrentCopyForTts();
  const copyTtsDownloadName = `${title.trim() || "pixelle"}-current-copy-tts.mp3`.replace(/[\\/:*?"<>|]+/g, "-");

  const readinessItems = [
    { key: "llm", label: "语言模型", ok: serviceReady?.llm !== false, action: "去配置" },
    { key: "image", label: "图像生成", ok: serviceReady?.image !== false, action: "去配置" },
    {
      key: "tts",
      label: ttsMode === "edge" ? "配音 (Edge)" : ttsMode === "minimax" ? "配音 (MiniMax)" : ttsMode === "mimo" ? "配音 (MiMo)" : "配音",
      ok:
        ttsMode === "edge" || ttsMode === "comfyui"
          ? true
          : ttsMode === "minimax"
          ? Boolean(serviceReady?.minimax)
          : Boolean(serviceReady?.mimo),
      action: ttsMode === "edge" ? "" : "去配置或改用 Edge",
    },
  ];
  const readinessIssues = readinessItems.filter((item) => !item.ok);
  const liveStoryboardPreview = mode === "ai" ? buildScenesForRender() : [];
  const sceneCountMismatch =
    mode === "ai" &&
    Boolean(copyDraft.trim()) &&
    liveStoryboardPreview.length > 0 &&
    liveStoryboardPreview.length !== aiSceneCount;
  const reuseLabel =
    latestCompletedTaskTitle ||
    (latestCompletedTaskId ? `最近完成任务 ${latestCompletedTaskId.slice(0, 8)}…` : null);
  const showContentStep = expertMode || wizardStep === "content";
  const showStyleStep = expertMode || wizardStep === "style";
  const showVoiceStep = expertMode || wizardStep === "voice";
  const showReviewStep = expertMode || wizardStep === "review";
  const contentReady = Boolean(title.trim()) && buildScenesForRender().length > 0;
  const styleReady = Boolean(workflowId);
  const voiceReady = Boolean(voice);
  const goWizard = (step: WizardStepId) => {
    setWizardStep(step);
    window.requestAnimationFrame(() => {
      const anchor = WIZARD_STAGE_ID[step];
      document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };
  const handleWizardNext = () => {
    if (wizardStep === "content") {
      if (!contentReady) {
        const errors = validateBeforeSubmit(buildScenesForRender());
        // Only surface content-related errors for step gate (ignore review confirm).
        const stepErrors: FieldErrors = {};
        if (errors.title) stepErrors.title = errors.title;
        if (errors.content) stepErrors.content = errors.content;
        if (!title.trim()) stepErrors.title = "请填写项目标题";
        if (buildScenesForRender().length === 0) stepErrors.content = "请先生成或填写文案";
        setFieldErrors(stepErrors);
        if (stepErrors.title) scrollToField("stage-content");
        else scrollToField("stage-storyboard");
        addToast(Object.values(stepErrors)[0] || "请先完成内容步骤", "error");
        return;
      }
      setFieldErrors({});
      goWizard("style");
      return;
    }
    if (wizardStep === "style") {
      if (!styleReady) {
        addToast("请选择画面工作流后再继续", "error");
        scrollToField("stage-style");
        return;
      }
      goWizard("voice");
      return;
    }
    if (wizardStep === "voice") {
      if (!voiceReady) {
        addToast("请选择配音音色后再继续", "error");
        scrollToField("stage-voice");
        return;
      }
      if (fieldErrors.tts) {
        scrollToField("stage-voice");
        addToast(fieldErrors.tts, "error");
        return;
      }
      goWizard("review");
    }
  };
  const handleWizardBack = () => {
    if (wizardStep === "style") goWizard("content");
    else if (wizardStep === "voice") goWizard("style");
    else if (wizardStep === "review") goWizard("voice");
  };

  return (
    <div className="mx-auto w-full max-w-[1240px] animate-fade-in space-y-5 pb-28">
      <ConfirmModal
        open={deletePresetConfirmOpen}
        danger
        title="删除工作台预设？"
        description={activePreset ? `将删除预设「${activePreset.name}」，此操作不可撤销。` : undefined}
        confirmLabel="确认删除"
        onCancel={() => setDeletePresetConfirmOpen(false)}
        onConfirm={confirmDeletePreset}
      />

      {showDraftBanner && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2.5">
          <div className="text-sm text-amber-100">
            已恢复本地草稿
            {draftSavedAt ? ` · ${new Date(draftSavedAt).toLocaleString()}` : ""}
            <span className="block text-xs text-amber-200/70 mt-0.5">可继续编辑，或清空后重新开始。</span>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setShowDraftBanner(false)}
              className="rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:border-zinc-500"
            >
              继续编辑
            </button>
            <button
              type="button"
              onClick={clearLocalDraft}
              className="rounded border border-rose-900/50 px-3 py-1.5 text-xs text-rose-300 hover:bg-rose-950/30"
            >
              清空重来
            </button>
          </div>
        </div>
      )}

      {showCreateTip && (
        <div className="flex flex-col gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between animate-fade-in-up">
          <p className="text-sm text-amber-50/95">
            <span className="font-medium text-amber-200">快速上手：</span>
            先写主题 → 生成文案 → 风格 / 声音 → 确认后生成初稿。
          </p>
          <button
            type="button"
            onClick={() => {
              dismissCreateTip();
              setShowCreateTip(false);
            }}
            className="shrink-0 rounded-md border border-zinc-700 px-2.5 py-1 text-xs text-zinc-400 hover:text-zinc-200"
          >
            知道了
          </button>
        </div>
      )}

      {serviceReady && (
        <div className={`rounded-xl border px-3 py-2.5 ${readinessIssues.length ? "border-amber-500/30 bg-amber-500/5" : "border-emerald-500/20 bg-emerald-500/5"}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-zinc-200">
              {readinessIssues.length
                ? `创作前检查：${readinessIssues.length} 项服务待处理`
                : "创作前检查：关键服务已就绪"}
            </p>
            {readinessIssues.length > 0 && onOpenSettings && (
              <button
                type="button"
                onClick={onOpenSettings}
                className="text-xs font-medium text-amber-300 hover:text-amber-200"
              >
                打开系统设置
              </button>
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {readinessItems.map((item) => (
              <span
                key={item.key}
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
                  item.ok
                    ? "border-emerald-500/20 text-emerald-300"
                    : "border-amber-500/30 text-amber-200"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${item.ok ? "bg-emerald-400" : "bg-amber-400"}`} />
                {item.label}
                {!item.ok && item.action ? ` · ${item.action}` : ""}
              </span>
            ))}
          </div>
        </div>
      )}

      <CreateStepper
        wizardStep={wizardStep}
        expertMode={expertMode}
        contentReady={contentReady}
        styleReady={styleReady}
        voiceReady={voiceReady}
        reviewConfirmed={reviewConfirmed}
        draftSavedAt={draftSavedAt}
        onGoStep={goWizard}
        onRequestNext={handleWizardNext}
        onToggleExpert={() => setExpertMode((value) => !value)}
      />

      {/* Step 1: Content */}
      <div className={showContentStep ? "space-y-5 animate-soft-scale-in" : "hidden"}>
      {/* Task Header Title */}
      <div id="stage-content" className="ui-card space-y-3 scroll-mt-24">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex-1">
          <label htmlFor="quick-create-title" className="block text-label mb-0.5">
            项目标题
          </label>
          <input
            id="quick-create-title"
            type="text"
            value={title}
            onChange={(e) => {
              setTitle(e.target.value);
              if (fieldErrors.title) setFieldErrors((prev) => ({ ...prev, title: undefined }));
            }}
            className={`bg-transparent border-b text-zinc-100 font-medium text-base w-full py-0.5 focus:outline-none font-display transition-colors ${
              fieldErrors.title ? "border-rose-500" : "border-zinc-800 focus:border-amber-500"
            }`}
          />
          {fieldErrors.title && <p className="mt-1 text-xs text-rose-400">{fieldErrors.title}</p>}
        </div>
        <div className="text-caption">
          {activePreset ? `当前预设: ${activePreset.name}` : "尚未选择预设"}
          {activePreset?.id === defaultPresetId && " · 默认"}
        </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(180px,260px)_minmax(180px,1fr)_auto] gap-2 items-end">
          <div>
            <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
              工作台预设 / Workspace Preset
            </label>
            <Select
              value={activePreset?.id || ""}
              onChange={(e) => {
                const preset = presets.find((item) => item.id === e.target.value);
                if (preset) onSelectPreset(preset);
              }}
              className="w-full bg-[#17181c] border border-zinc-800 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
            >
              <option value="">选择工作台预设</option>
              {presets.map((preset) => (
                <option key={preset.id} value={preset.id}>
                  {preset.name}{preset.id === defaultPresetId ? " · 默认" : ""}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
              预设名称
            </label>
            <input
              type="text"
              value={presetNameDraft}
              onChange={(e) => setPresetNameDraft(e.target.value)}
              placeholder="例如：小红书竖屏口播"
              className="w-full bg-[#17181c] border border-zinc-800 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
            />
          </div>

          <div className="flex flex-wrap gap-1.5 justify-start xl:justify-end relative">
            <button
              type="button"
              onClick={handleUpdatePreset}
              disabled={!activePreset}
              className="px-3 py-1.5 text-xs bg-zinc-800 text-zinc-300 hover:text-white disabled:text-zinc-600 disabled:bg-zinc-900 rounded border border-zinc-750 hover:border-amber-500/40 font-medium flex items-center gap-1.5 transition-colors"
            >
              <Save className="w-3.5 h-3.5 text-amber-500" />
              覆盖当前预设
            </button>
            <button
              type="button"
              onClick={handleCreatePreset}
              className="px-3 py-1.5 text-xs text-black bg-amber-500 hover:bg-amber-400 rounded border border-amber-400/40 font-semibold flex items-center gap-1.5 transition-colors"
            >
              <Plus className="w-3.5 h-3.5 text-black" />
              另存为
            </button>
            <button
              type="button"
              onClick={() => setPresetMenuOpen((open) => !open)}
              className="px-2.5 py-1.5 text-xs text-zinc-400 bg-[#17181c] hover:text-zinc-100 rounded border border-zinc-800 hover:border-zinc-700 flex items-center gap-1 transition-colors"
            >
              <ChevronDown className="w-3.5 h-3.5" />
              更多
            </button>

            {presetMenuOpen && (
              <div className="absolute right-0 top-full mt-1.5 z-20 w-36 bg-[#101114] border border-zinc-800 rounded shadow-xl overflow-hidden">
                <button
                  type="button"
                  onClick={handleSetDefaultPreset}
                  disabled={!activePreset || activePreset.id === defaultPresetId}
                  className="w-full px-3 py-2 text-left text-xs text-zinc-300 hover:bg-zinc-900 disabled:text-zinc-600"
                >
                  设为默认
                </button>
                <button
                  type="button"
                  onClick={handleDeletePreset}
                  disabled={!activePreset}
                  className="w-full px-3 py-2 text-left text-xs text-rose-300 hover:bg-rose-950/20 disabled:text-zinc-600"
                >
                  删除预设
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 1. Creative Mode Tab Switches */}
      <div className="space-y-2">
        <label className="block text-xs font-semibold text-zinc-400">创作方式</label>
        <div className="grid max-w-2xl grid-cols-1 gap-2 p-1 sm:grid-cols-3 rounded-xl border border-zinc-800 bg-[var(--color-surface-2)]">
          <button
            type="button"
            onClick={() => setMode("ai")}
            className={`flex flex-col items-start gap-0.5 rounded-lg px-3 py-2.5 text-left text-xs transition-all ${
              mode === "ai"
                ? "bg-amber-500/10 text-amber-300 border border-amber-500/25 font-semibold"
                : "text-zinc-400 hover:text-zinc-200 border border-transparent"
            }`}
          >
            <span className="inline-flex items-center gap-1.5"><Sparkles className="w-3.5 h-3.5" /> AI 一键文案</span>
            <span className="text-caption font-normal text-zinc-500">主题生成口播，推荐新手</span>
          </button>
          <button
            type="button"
            onClick={() => setMode("manual")}
            className={`flex flex-col items-start gap-0.5 rounded-lg px-3 py-2.5 text-left text-xs transition-all ${
              mode === "manual"
                ? "bg-amber-500/10 text-amber-300 border border-amber-500/25 font-semibold"
                : "text-zinc-400 hover:text-zinc-200 border border-transparent"
            }`}
          >
            <span className="inline-flex items-center gap-1.5"><Edit3 className="w-3.5 h-3.5" /> 手动分镜</span>
            <span className="text-caption font-normal text-zinc-500">逐镜写旁白与画面提示词</span>
          </button>
          <button
            type="button"
            onClick={() => setMode("batch")}
            className={`flex flex-col items-start gap-0.5 rounded-lg px-3 py-2.5 text-left text-xs transition-all ${
              mode === "batch"
                ? "bg-amber-500/10 text-amber-300 border border-amber-500/25 font-semibold"
                : "text-zinc-400 hover:text-zinc-200 border border-transparent"
            }`}
          >
            <span className="inline-flex items-center gap-1.5"><Layers className="w-3.5 h-3.5" /> 批量多主题</span>
            <span className="text-caption font-normal text-zinc-500">一行一主题，各生成一条视频</span>
          </button>
        </div>
      </div>

      {/* 2. Content Input panel */}
      <div id="stage-storyboard" className="ui-card space-y-4 scroll-mt-24">
        {mode === "ai" && (
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">输入创作主题 / Prompt Idea</label>
              <textarea
                placeholder="例如: 智能机器人在雨夜的霓虹小巷穿梭，极具颗粒感写实，带有温暖孤独色彩的科幻故事。"
                value={aiTopic}
                onChange={(e) => setAiTopic(e.target.value)}
                className="w-full h-24 bg-[#17181c] border border-zinc-800 rounded p-2.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 placeholder-zinc-650"
              />
            </div>

            <div className="bg-[#17181c] border border-zinc-850 rounded-md p-3 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <label className="block text-xs font-medium text-zinc-400">文案生成方式</label>
                <div className="flex gap-1.5 bg-[#101114] border border-zinc-900 p-0.5 rounded">
                  <button
                    type="button"
                    onClick={() => setCopyDraftMode("full")}
                    className={`px-2.5 py-1 text-[10px] rounded transition-all ${
                      copyDraftMode === "full" ? "bg-amber-500/10 text-amber-400 font-medium" : "text-zinc-500 hover:text-zinc-300"
                    }`}
                  >
                    整篇口播稿
                  </button>
                  <button
                    type="button"
                    onClick={() => setCopyDraftMode("segmented")}
                    className={`px-2.5 py-1 text-[10px] rounded transition-all ${
                      copyDraftMode === "segmented" ? "bg-amber-500/10 text-amber-400 font-medium" : "text-zinc-500 hover:text-zinc-300"
                    }`}
                  >
                    分镜旁白列表
                  </button>
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between gap-3 mb-1.5">
                  <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
                    AI 生成文案草稿 / Editable Copy Draft
                  </label>
                  <span className="text-[10px] text-zinc-600">
                    {copyDraftMode === "full"
                      ? "两步：① 纯净口播稿 ② 语义/节奏推荐分镜（不绑死镜数）"
                      : "按当前分镜数直接生成多段旁白"}
                  </span>
                </div>
                <textarea
                  value={copyDraft}
                  onChange={(e) => handleCopyDraftChange(e.target.value)}
                  placeholder={
                    copyDraftMode === "full"
                      ? "点击生成后，先得到纯净口播（不按固定镜数切割）；随后自动做语义+节奏分镜建议。也可粘贴成稿后点「重新分析」。"
                      : "点击“生成分镜旁白草稿”后，AI 会在这里按段落生成旁白列表。你可以逐段修改，每段会进入一个分镜。"
                  }
                  className="w-full min-h-36 max-h-80 bg-[#101114] border border-zinc-900 rounded px-2.5 py-2 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 placeholder-zinc-650 resize-y leading-relaxed"
                />
              </div>
              <div id="keyword-extraction" className="mt-3 border-t border-zinc-800 pt-3 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div>
                    <div className="text-xs font-medium text-zinc-300">字幕高亮词（可选）</div>
                    <div className="text-[10px] text-zinc-500 mt-0.5">
                      {keywordStatus === "loading" && "正在分析当前文案..."}
                      {keywordStatus === "stale" && "文案已修改，建议重新抽词"}
                      {keywordStatus === "error" && "抽词失败，可重新尝试"}
                      {keywordStatus === "ready" && (aiKeywordSuggestions.length ? `已生成 ${aiKeywordSuggestions.length} 个候选` : "候选已处理")}
                      {keywordStatus === "idle" && "可折叠，不影响主路径出片"}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => setShowAdvancedKeywords((open) => !open)}
                      className="inline-flex items-center gap-1 text-[11px] text-zinc-400 hover:text-zinc-200"
                    >
                      {showAdvancedKeywords ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                      {showAdvancedKeywords ? "收起" : "展开"}
                    </button>
                    <label className="inline-flex items-center gap-2 text-[11px] text-zinc-400 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={keywordPreferences.autoExtract}
                        onChange={(e) => updateKeywordPreferences({ autoExtract: e.target.checked })}
                        className="h-3.5 w-3.5 accent-amber-500"
                      />
                      生成文案后自动抽词
                    </label>
                    <button
                      type="button"
                      onClick={handleExtractKeywords}
                      disabled={keywordStatus === "loading" || !keywordSourceText()}
                      className="inline-flex items-center justify-center gap-1.5 rounded border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-[11px] text-amber-200 hover:bg-amber-500/20 disabled:opacity-50"
                    >
                      {keywordStatus === "loading" ? <Loader className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
                      {keywordStatus === "stale" || keywordStatus === "error" || keywordStatus === "ready" ? "重新抽取" : "AI 抽词"}
                    </button>
                  </div>
                </div>
                <div className={showAdvancedKeywords || keywordPreferences.autoExtract && aiKeywordSuggestions.length > 0 ? "space-y-3" : "hidden"}>

                <div className="grid grid-cols-2 gap-2">
                  <label className="block">
                    <span className="block text-[10px] text-zinc-500 mb-1">抽取风格</span>
                    <Select
                      value={keywordPreferences.style}
                      onChange={(e) => {
                        updateKeywordPreferences({ style: e.target.value as KeywordExtractionStyle });
                      }}
                      className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                    >
                      <option value="balanced">综合</option>
                      <option value="concept">核心概念</option>
                      <option value="selling_point">产品卖点</option>
                      <option value="emotion">情绪表达</option>
                      <option value="numeric">数字信息</option>
                      <option value="action">行动号召</option>
                    </Select>
                  </label>
                  <label className="block">
                    <span className="block text-[10px] text-zinc-500 mb-1">抽取密度</span>
                    <Select
                      value={keywordPreferences.density}
                      onChange={(e) => {
                        updateKeywordPreferences({ density: e.target.value as KeywordExtractionDensity });
                      }}
                      className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                    >
                      <option value="low">少</option>
                      <option value="standard">标准</option>
                      <option value="high">多</option>
                    </Select>
                  </label>
                </div>

                {aiKeywordSuggestions.length > 0 && (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] text-zinc-500">AI 推荐</span>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => applyKeywordSuggestions(aiKeywordSuggestions)}
                          disabled={keywordStatus === "loading"}
                          className="text-[10px] text-amber-300 hover:text-amber-200 disabled:opacity-50"
                        >
                          全部应用
                        </button>
                        <button
                          type="button"
                          onClick={handleSwapKeywordSuggestions}
                          disabled={keywordStatus === "loading" || !keywordSourceText()}
                          className="inline-flex items-center gap-1 rounded border border-zinc-800 px-2 py-1 text-[10px] text-zinc-400 hover:border-amber-500/40 hover:text-zinc-200 disabled:opacity-50"
                        >
                          {keywordStatus === "loading" ? <Loader className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                          换一批
                        </button>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {aiKeywordSuggestions.map((item) => (
                        <button
                          key={item.word}
                          type="button"
                          onClick={() => applyKeywordSuggestions([item])}
                          title={`应用“${item.word}”`}
                          className="inline-flex items-center gap-1 rounded border border-zinc-800 bg-[#0c0d10] px-2 py-1 text-xs hover:border-amber-500/50"
                          style={{ color: item.color }}
                        >
                          {item.word}
                          <Plus className="h-3 w-3" />
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {renderSelectedKeywordEditor()}
                </div>
              </div>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">文案总字数</label>
                <div className="grid grid-cols-[minmax(0,1fr)_88px] gap-1.5">
                  <input
                    type="number"
                    min="50"
                    max="3000"
                    step="10"
                    value={copyCharCount}
                    onChange={(e) => {
                      setCopyCharCountTouched(true);
                      setCopyCharCount(parseInt(e.target.value || "120"));
                    }}
                    className="w-full bg-[#17181c] border border-zinc-800 rounded px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                  />
                  <Select
                    value={copyCharCountMode}
                    onChange={(e: any) => setCopyCharCountMode(e.target.value)}
                    className="w-full bg-[#17181c] border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                  >
                    <option value="around">字左右</option>
                    <option value="within">字以内</option>
                  </Select>
                </div>
                <p className="mt-1 text-[10px] text-zinc-500 leading-relaxed">
                  步骤 1：按字数生成纯净口播（不绑死分镜数）· 预计 {estimatedCopySeconds} 秒
                </p>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">分镜数量</label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={STORYBOARD_SCENE_MIN}
                    max={STORYBOARD_SCENE_MAX}
                    step={1}
                    value={aiSceneCount}
                    onChange={(e) => {
                      const next = clampSceneCount(parseInt(e.target.value || String(STORYBOARD_SCENE_MIN), 10));
                      setAiSceneCount(next);
                      setAiSceneCountTouched(true);
                    }}
                    className="ui-input"
                  />
                  <span className="shrink-0 text-caption">个</span>
                </div>
                <p className="mt-1 text-caption leading-relaxed">
                  {suggestedSceneCount != null ? (
                    <>
                      <span className="text-zinc-400">步骤 2 · </span>
                      语义 <span className="text-zinc-200 font-medium">{suggestedSceneCount}</span>
                      {rhythmSceneCount != null && (
                        <>
                          {" "}· 节奏 <span className="text-zinc-200 font-medium">{rhythmSceneCount}</span>
                          <span className="text-zinc-600">（约 40 字/镜）</span>
                        </>
                      )}
                      {!aiSceneCountTouched && suggestedSceneCount === aiSceneCount ? (
                        <span className="text-zinc-500"> · 已用语义填入</span>
                      ) : null}
                      <span className="ml-1.5 inline-flex flex-wrap gap-x-2 gap-y-0.5">
                        {suggestedSceneCount !== aiSceneCount && (
                          <button
                            type="button"
                            onClick={() => {
                              setAiSceneCount(suggestedSceneCount);
                              setAiSceneCountTouched(false);
                            }}
                            className="text-amber-400 hover:text-amber-300 underline-offset-2 hover:underline"
                          >
                            采用语义
                          </button>
                        )}
                        {rhythmSceneCount != null && rhythmSceneCount !== aiSceneCount && (
                          <button
                            type="button"
                            onClick={() => {
                              setAiSceneCount(rhythmSceneCount);
                              setAiSceneCountTouched(true);
                            }}
                            className="text-amber-400/90 hover:text-amber-300 underline-offset-2 hover:underline"
                          >
                            采用节奏
                          </button>
                        )}
                        {copyDraft.trim() && (
                          <button
                            type="button"
                            onClick={() => {
                              const result = reanalyzeStoryboardFromCopy(copyDraft, {
                                adoptIfUnlocked: false,
                                toastOnResult: true,
                              });
                              if (!result) addToast("请先填写或生成文案", "info");
                            }}
                            className="text-zinc-400 hover:text-zinc-200 underline-offset-2 hover:underline"
                          >
                            重新分析
                          </button>
                        )}
                      </span>
                    </>
                  ) : (
                    <>步骤 2：生成纯净文案后，按语义 + 节奏推荐分镜 · 可改 {STORYBOARD_SCENE_MIN}–{STORYBOARD_SCENE_MAX}</>
                  )}
                </p>
                <p className="mt-0.5 text-[10px] text-zinc-600 leading-relaxed">
                  分镜数不由总字数直接决定；语义看句/意群，节奏按字数粗估。当前目标每镜约 {averageCopyCharsPerStoryboard} 字。
                </p>
                {sceneCountMismatch && (
                  <p className="mt-1 text-[10px] text-amber-400/90 leading-relaxed">
                    目标 {aiSceneCount} 镜 · 当前可安全切分 {liveStoryboardPreview.length} 镜（语义优先，未强制字切）
                  </p>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">切分规则方式</label>
                <Select
                  value={splitType}
                  onChange={(e: any) => setSplitType(e.target.value)}
                  className="w-full bg-[#17181c] border border-zinc-800 rounded px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                >
                  <option value="paragraph">按段落智能切分</option>
                  <option value="line">按每一行/换行切分</option>
                  <option value="sentence">按句子标点切分</option>
                </Select>
              </div>
            </div>

            {fieldErrors.content && (
              <p className="text-xs text-rose-400" role="alert">{fieldErrors.content}</p>
            )}

            {liveStoryboardPreview.length > 0 && (
              <div className="rounded-md border border-zinc-800 bg-[#0c0d10] p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium text-zinc-200">
                    将生成 {liveStoryboardPreview.length} 个分镜（根据当前文案实时预览）
                  </p>
                  <span className="text-caption">提交时按此切分</span>
                </div>
                <ol className="max-h-40 space-y-1.5 overflow-y-auto">
                  {liveStoryboardPreview.slice(0, 12).map((scene) => (
                    <li key={scene.id} className="flex gap-2 text-xs text-zinc-400">
                      <span className="font-mono text-amber-500/80 shrink-0">#{scene.id}</span>
                      <span className="line-clamp-2 text-zinc-300">{scene.ttsText || "（空旁白）"}</span>
                    </li>
                  ))}
                  {liveStoryboardPreview.length > 12 && (
                    <li className="text-caption">…还有 {liveStoryboardPreview.length - 12} 个分镜</li>
                  )}
                </ol>
              </div>
            )}

            <div className="flex flex-col sm:flex-row justify-end gap-2 pt-2 border-t border-zinc-900">
              <button
                type="button"
                onClick={handleGenerateCopyDraft}
                disabled={copyDraftLoading || aiLoading || serviceReady?.llm === false}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-400 disabled:bg-zinc-800 text-black disabled:text-zinc-500 font-semibold text-sm rounded shadow-md flex items-center justify-center gap-1.5 transition-colors"
              >
                {copyDraftLoading ? (
                  <>
                    <Loader className="w-3.5 h-3.5 animate-spin" />
                    AI 正在生成文案...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5 text-black" />
                    {copyDraftMode === "full" ? "生成口播稿" : "生成分镜旁白"}
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={handleAIGenerateScript}
                disabled={aiLoading || copyDraftLoading || !copyDraft.trim()}
                className="px-3 py-2 bg-zinc-800 text-zinc-300 hover:text-white disabled:bg-zinc-900 disabled:text-zinc-600 border border-zinc-700 hover:border-amber-500/40 text-xs font-medium rounded flex items-center justify-center gap-1.5 transition-colors"
                title="进阶：为每镜生成画面提示词并切换到手动分镜编辑"
              >
                {aiLoading ? (
                  <>
                    <Loader className="w-3.5 h-3.5 animate-spin text-amber-500" />
                    生成画面提示词中...
                  </>
                ) : (
                  <>
                    <Edit3 className="w-3.5 h-3.5 text-amber-500" />
                    进阶：生成画面提示词并手动编辑
                  </>
                )}
              </button>
            </div>
            {serviceReady?.llm === false && (
              <p className="text-xs text-amber-300 text-right">
                语言模型未就绪，
                <button type="button" className="underline ml-1" onClick={onOpenSettings}>
                  前往配置
                </button>
              </p>
            )}
          </div>
        )}

        {mode === "manual" && (
          <div className="space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-zinc-900">
              <span className="text-xs font-medium text-zinc-300 flex items-center gap-1">
                分镜列表编辑器 (精细化定制旁白与画面提示词)
              </span>
              <button
                onClick={addScene}
                className="px-2 py-1 bg-[#17181c] hover:bg-zinc-800 text-zinc-300 border border-zinc-800 rounded text-[11px] font-medium flex items-center gap-1 transition-colors"
              >
                <Plus className="w-3 h-3 text-amber-500" />
                新增分镜
              </button>
            </div>

            <div className="space-y-3 max-h-[360px] overflow-y-auto pr-1">
              {scenes.map((scene, idx) => (
                <div
                  key={scene.id}
                  className="bg-[#17181c] border border-zinc-850 p-3 rounded flex items-start gap-3 relative hover:border-zinc-800 group"
                >
                  <div className="w-6 h-6 rounded bg-zinc-800/80 text-zinc-400 text-xs font-bold flex items-center justify-center font-mono mt-1">
                    {idx + 1}
                  </div>

                  <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label htmlFor={`scene-narration-${scene.id}`} className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                        分镜配音旁白 (TTS Text)
                      </label>
                      <textarea
                        id={`scene-narration-${scene.id}`}
                        placeholder="请输入本分镜念出来的配音旁白文案..."
                        value={scene.ttsText}
                        onChange={(e) => updateScene(scene.id, "ttsText", e.target.value)}
                        rows={3}
                        className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-2 text-xs text-zinc-300 leading-relaxed resize-y max-h-48 overflow-y-auto focus:outline-none focus:border-amber-500"
                      />
                    </div>
                    <div>
                      <label htmlFor={`scene-visual-${scene.id}`} className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                        画面视觉绘图 Prompt (英文最佳)
                      </label>
                      <textarea
                        id={`scene-visual-${scene.id}`}
                        placeholder="请输入本分镜的画面提示词，留空将沿用主题..."
                        value={scene.visualPrompt}
                        onChange={(e) => updateScene(scene.id, "visualPrompt", e.target.value)}
                        rows={3}
                        className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-2 text-xs text-zinc-300 leading-relaxed resize-y max-h-48 overflow-y-auto focus:outline-none focus:border-amber-500"
                      />
                    </div>
                  </div>

                  <button
                    onClick={() => removeScene(scene.id)}
                    className="p-1.5 hover:bg-rose-950/20 text-zinc-500 hover:text-rose-400 rounded transition-colors"
                    title="删除此分镜"
                    aria-label={`删除分镜 ${idx + 1}`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {mode === "batch" && (
          <div className="space-y-4 animate-soft-scale-in">
            <div className="rounded-xl border border-zinc-800 bg-[var(--color-surface-3)] p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <label className="text-sm font-medium text-zinc-200">批量主题列表</label>
                <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-caption text-amber-200">
                  最多并行 3 路 · 共 {batchCount} 条
                </span>
              </div>
              <p className="mb-2 text-xs text-zinc-500">
                一行一个主题。提交后每个主题会生成<strong className="text-zinc-300">独立视频任务</strong>，进度在右侧任务面板与历史记录中分别查看。
              </p>
              <textarea
                value={batchInput}
                onChange={(e) => {
                  setBatchInput(e.target.value);
                  const count = e.target.value.split("\n").filter((l) => l.trim() !== "").length;
                  setBatchCount(count);
                }}
                placeholder={"主题一: 智能机器人在雨夜撑伞\n主题二: 机械宠物狗在客厅嬉戏\n主题三: 未来城市空中飞车速递"}
                className="w-full h-36 rounded-lg border border-zinc-800 bg-[var(--color-surface-1)] p-2.5 text-sm text-zinc-300 focus:outline-none focus:border-amber-500 font-mono placeholder-zinc-600"
              />
              {batchCount > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {batchInput
                    .split(/\r?\n/)
                    .map((line) => line.trim())
                    .filter(Boolean)
                    .slice(0, 12)
                    .map((line, index) => (
                      <span
                        key={`${index}-${line.slice(0, 12)}`}
                        className="max-w-full truncate rounded-md border border-zinc-800 bg-[var(--color-surface-1)] px-2 py-1 text-caption text-zinc-400"
                        title={line}
                      >
                        #{index + 1} {line.replace(/^主题\s*[一二三四五六七八九十\d]+\s*[:：]\s*/u, "").slice(0, 28)}
                      </span>
                    ))}
                  {batchCount > 12 && (
                    <span className="text-caption text-zinc-500">…还有 {batchCount - 12} 条</span>
                  )}
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-amber-500/15 bg-amber-500/5 p-3 text-xs text-zinc-400">
              <span className="flex items-start gap-1.5">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
                <span>
                  将创建 <strong className="text-zinc-200">{batchCount}</strong> 个独立任务；配音 / 工作流 / 画幅共用当前成片设定。
                  批量模式不进入项目工作台。
                </span>
              </span>
            </div>

            {lastBatchSummary && (
              <div className="rounded-xl border border-zinc-800 bg-[var(--color-surface-2)] p-3 text-xs">
                <div className="mb-1 font-medium text-zinc-200">最近一次批量提交</div>
                <p className="text-zinc-400">
                  {new Date(lastBatchSummary.at).toLocaleString()} · 共 {lastBatchSummary.total} 条 ·
                  成功 <span className="text-emerald-400">{lastBatchSummary.success}</span> ·
                  失败 <span className={lastBatchSummary.failed ? "text-rose-400" : "text-zinc-500"}>{lastBatchSummary.failed}</span>
                </p>
                <button
                  type="button"
                  onClick={() => onOpenConsole?.()}
                  className="mt-2 text-amber-300 hover:text-amber-200"
                >
                  打开任务面板查看进度 →
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      </div>
      {/* End step 1 content */}

      {/* Step 2: Style (画幅 / 字幕 / 工作流) — filled after voice block restructure */}
      {/* Step 3: Voice */}
      <div className={showVoiceStep ? "space-y-5 animate-soft-scale-in" : "hidden"}>
      {/* TTS Voice Synthesis & BGM Mixing */}
      <div id="stage-voice" className="grid grid-cols-1 gap-4 scroll-mt-24 md:grid-cols-2">
        {/* TTS Panel */}
        <div className="ui-card space-y-4 !p-4">
          <h3 className="flex items-center gap-1.5 text-xs font-semibold text-zinc-400">
            <Mic2 className="h-4 w-4 text-amber-500" />
            配音合成 TTS 引擎
          </h3>
          <p className="text-[10px] text-amber-400/80">试听与“合成当前文案”仅供预览，不会复用到最终成片。</p>

          <div className="grid grid-cols-4 gap-1 p-0.5 bg-[#17181c] border border-zinc-850 rounded">
            {(["edge", "comfyui", "minimax", "mimo"] as const).map((opt) => (
              <button
                key={opt}
                onClick={() => {
                  setTtsMode(opt);
                  setVoice(VOICE_OPTIONS[opt][0].id);
                }}
                className={`py-1 text-[10px] rounded uppercase font-semibold text-center transition-all ${
                  ttsMode === opt ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {opt === "edge" && "Edge 极速"}
                {opt === "comfyui" && "Comfy 克隆"}
                {opt === "minimax" && "MiniMax 精致"}
                {opt === "mimo" && "MiMo 自然"}
              </button>
            ))}
          </div>

          <div className="space-y-1.5">
            <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
              多镜配音交付 / Delivery
            </label>
            <div className="grid grid-cols-2 gap-1 p-0.5 bg-[#17181c] border border-zinc-850 rounded">
              {(
                [
                  { id: "continuous" as const, label: "整篇连续（推荐）" },
                  { id: "per_scene" as const, label: "逐镜合成" },
                ] as const
              ).map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setTtsDelivery(opt.id)}
                  className={`py-1.5 text-[10px] rounded font-medium text-center transition-all ${
                    ttsDelivery === opt.id
                      ? "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                      : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <p className="text-[10px] text-zinc-500 leading-relaxed">
              {ttsDelivery === "continuous"
                ? "多镜默认整篇一次合成，再按对齐时间切成各镜，音色更连贯；改某一镜旁白会整轨重合成。"
                : "每镜单独合成，速度快、局部重做省成本，但多镜可能出现音色/语势漂移。"}
            </p>
          </div>

          <div className="space-y-3 pt-1">
            {/* Voices list */}
            <div>
              <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                选择合成音色及风格 / Voice Model
              </label>
              <Select
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                className="w-full bg-[#17181c] border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
              >
                {VOICE_OPTIONS[ttsMode].map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </Select>
            </div>

            {/* Sub options if MiniMax */}
            {ttsMode === "minimax" && (
              <div className="grid grid-cols-2 gap-2 bg-[#17181c] p-2 rounded border border-zinc-850">
                <div>
                  <label className="block text-[9px] text-zinc-500 mb-0.5">声音情感 / Emotion</label>
                  <Select
                    value={emotion}
                    onChange={(e) => setEmotion(e.target.value)}
                    className="w-full bg-[#101114] border border-zinc-900 rounded px-1.5 py-1 text-[11px] text-zinc-300 focus:outline-none focus:border-amber-500"
                  >
                    <option value="">自动匹配 (Auto)</option>
                    <option value="happy">欢快愉悦 (Happy)</option>
                    <option value="sad">悲伤低落 (Sad)</option>
                    <option value="angry">严厉愤怒 (Angry)</option>
                    <option value="fearful">紧张害怕 (Fearful)</option>
                    <option value="disgusted">厌恶嫌弃 (Disgusted)</option>
                    <option value="surprised">惊讶意外 (Surprised)</option>
                    <option value="calm">平静克制 (Calm)</option>
                    <option value="fluent">流畅自然 (Fluent)</option>
                    <option value="whisper">低声耳语 (Whisper)</option>
                  </Select>
                </div>
                <div>
                  <label className="block text-[9px] text-zinc-500 mb-0.5">MiniMax 基座模型</label>
                  <Select
                    value={minimaxModel}
                    onChange={(e) => setMinimaxModel(e.target.value)}
                    className="w-full bg-[#101114] border border-zinc-900 rounded px-1.5 py-1 text-[11px] text-zinc-300 focus:outline-none focus:border-amber-500"
                  >
                    <option value="speech-2.8-turbo">speech-2.8-turbo</option>
                    <option value="speech-2.8-hd">speech-2.8-hd</option>
                    <option value="speech-2.6-turbo">speech-2.6-turbo</option>
                    <option value="speech-2.6-hd">speech-2.6-hd</option>
                    <option value="speech-02-turbo">speech-02-turbo</option>
                    <option value="speech-02-hd">speech-02-hd</option>
                  </Select>
                </div>
              </div>
            )}

            {/* Sub options if MiMo */}
            {ttsMode === "mimo" && (
              <div className="grid grid-cols-2 gap-2 bg-[#17181c] p-2 rounded border border-zinc-850">
                <div>
                  <label className="block text-[9px] text-zinc-500 mb-0.5">MiMo 基座模型</label>
                  <Select
                    value={mimoModel}
                    onChange={(e) => setMimoModel(e.target.value)}
                    className="w-full bg-[#101114] border border-zinc-900 rounded px-1.5 py-1 text-[11px] text-zinc-300 focus:outline-none focus:border-amber-500"
                  >
                    <option value="mimo-v2.5-tts">mimo-v2.5-tts（预设音色 · 多镜更稳）</option>
                    <option value="mimo-v2.5-tts-voicedesign">mimo-v2.5-tts-voicedesign（文案设计音色 · 多镜易漂移）</option>
                    <option value="mimo-v2.5-tts-voiceclone">mimo-v2.5-tts-voiceclone（参考音频克隆）</option>
                  </Select>
                </div>
                <div className="col-span-2">
                  <label className="block text-[9px] text-zinc-500 mb-0.5">
                    {mimoModel.includes("voicedesign")
                      ? "音色设计描述（必填，全片共用同一描述）"
                      : "自然语言风格指令（可选，多镜建议填写并固定）"}
                  </label>
                  <textarea
                    value={mimoStyle}
                    onChange={(e) => setMimoStyle(e.target.value)}
                    rows={2}
                    placeholder={
                      mimoModel.includes("voicedesign")
                        ? "例：25 岁年轻女声，清亮温柔，略带笑意，语速适中，适合短视频口播。同一讲述者全程口播。"
                        : "例：平稳专业的讲解语气，语速适中，情绪克制，适合知识口播。"
                    }
                    className="w-full bg-[#101114] border border-zinc-900 rounded px-1.5 py-1 text-[11px] text-zinc-300 resize-none focus:outline-none focus:border-amber-500"
                  />
                  {mimoModel.includes("voicedesign") ? (
                    <p className="mt-1 text-[10px] text-amber-400/90 leading-relaxed">
                      {ttsDelivery === "continuous"
                        ? "已启用「整篇连续合成」：Voice Design 多镜将一次合成再切分，音色更稳。请保持全片同一设计描述。"
                        : "当前为逐分镜合成：Voice Design 每镜都会重采样，多镜口播容易不像同一人。建议改用「整篇连续」或「预设音色」。"}
                    </p>
                  ) : (
                    <p className="mt-1 text-[10px] text-zinc-500 leading-relaxed">
                      多镜口播请固定音色与风格指令；连续合成 + 响度归一可进一步减轻镜间突兀感。
                    </p>
                  )}
                  {mimoModel.includes("voicedesign") && buildScenesForRender().length > 1 && (
                    <button
                      type="button"
                      onClick={() => {
                        setMimoModel("mimo-v2.5-tts");
                        addToast("已切换为预设音色模型，多镜口播更稳定。请再选一个固定音色。", "info");
                      }}
                      className="mt-1.5 text-[10px] text-amber-300 underline-offset-2 hover:underline"
                    >
                      一键改用预设音色（推荐）
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Audio Upload if ComfyUI clone */}
            {ttsMode === "comfyui" && (
              <div className="bg-[#17181c] p-2.5 rounded border border-zinc-850 space-y-2">
                <span className="text-[10px] text-zinc-400 font-medium block">
                  上传您要克隆的目标参考音频 (10MB以内的 MP3/WAV, 最好 5s-30s):
                </span>
                <div className="border border-dashed border-zinc-800 rounded flex flex-col items-center justify-center p-3 hover:border-amber-500/40 cursor-pointer">
                  <Upload className="w-5 h-5 text-zinc-600 mb-1.5" />
                  <span className="text-[10px] text-zinc-500">点击上传或将文件拖拽于此</span>
                </div>
              </div>
            )}

            <div className="bg-[#17181c] p-2.5 rounded border border-zinc-850 space-y-2">
              <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
                试听文案 / Preview Script
              </label>
              <textarea
                value={previewTtsText}
                onChange={(e) => {
                  previewTtsTextUserEditedRef.current = true;
                  setPreviewTtsText(e.target.value);
                }}
                rows={3}
                className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-2 text-xs text-zinc-300 leading-relaxed resize-none focus:outline-none focus:border-amber-500"
                placeholder="输入一段用于试听配音效果的文案"
              />
              {previewTtsAudioUrl && (
                <audio
                  src={previewTtsAudioUrl}
                  controls
                  className="w-full h-8"
                />
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center pt-2">
              <div>
                <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                  <span>语速调节: {speed}x</span>
                  <span>建议 0.9 - 1.2</span>
                </div>
                <input
                  type="range"
                  min="0.8"
                  max="1.5"
                  step="0.05"
                  value={speed}
                  onChange={(e) => setSpeed(parseFloat(e.target.value))}
                  className="w-full accent-amber-500 h-1 cursor-pointer bg-zinc-850 rounded"
                />
              </div>

              <div className="flex justify-end">
                <button
                  onClick={handlePreviewTts}
                  disabled={previewingTts}
                  className="px-2.5 py-1 bg-zinc-800 text-zinc-300 hover:text-white rounded border border-zinc-750 hover:border-zinc-650 text-xs font-medium flex items-center gap-1 transition-colors"
                >
                  {previewingTts ? <Loader className="w-3 h-3 animate-spin text-amber-500" /> : <Play className="w-3 h-3 text-amber-500" />}
                  试听 TTS 语音
                </button>
              </div>
            </div>

            <div className="bg-[#17181c] p-2.5 rounded border border-zinc-850 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <span className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
                    当前文案音频 / Current Copy
                  </span>
                  <span className="text-[10px] text-zinc-500">
                    {currentCopyForTts.label}
                    {currentCopyForTts.text && ` · ${currentCopyForTts.text.length} 字`}
                  </span>
                </div>
                <button
                  onClick={handleSynthesizeCurrentCopy}
                  disabled={synthesizingCopy || !currentCopyForTts.text}
                  className="px-2.5 py-1 bg-amber-500 text-black hover:bg-amber-400 disabled:bg-zinc-800 disabled:text-zinc-500 rounded border border-amber-400/40 disabled:border-zinc-750 text-xs font-semibold flex items-center gap-1 transition-colors"
                >
                  {synthesizingCopy ? <Loader className="w-3 h-3 animate-spin text-black" /> : <Volume2 className="w-3 h-3 text-black" />}
                  合成当前文案
                </button>
              </div>

              {copyTtsAudioUrl && (
                <div className="space-y-2 pt-2 border-t border-zinc-850">
                  <audio
                    src={copyTtsAudioUrl}
                    controls
                    className="w-full h-8"
                  />
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[10px] text-zinc-500 font-mono">
                      时长 {formatCopyTtsDuration(copyTtsDuration)} · {copyTtsSourceLabel}
                    </span>
                    <div className="flex items-center gap-1.5">
                      <a
                        href={copyTtsAudioUrl}
                        download={copyTtsDownloadName}
                        className="px-2 py-1 text-[10px] bg-zinc-800 text-zinc-300 hover:text-white rounded border border-zinc-750 hover:border-zinc-650 flex items-center gap-1 transition-colors"
                      >
                        <Download className="w-3 h-3 text-amber-500" />
                        下载音频
                      </a>
                      <button
                        onClick={() => {
                          setCopyTtsAudioUrl(null);
                          setCopyTtsDuration(null);
                          setCopyTtsSourceLabel("");
                        }}
                        className="px-2 py-1 text-[10px] bg-zinc-900 text-zinc-400 hover:text-rose-300 rounded border border-zinc-800 hover:border-rose-900/70 flex items-center gap-1 transition-colors"
                      >
                        <XCircle className="w-3 h-3 text-rose-400" />
                        清除音频
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* BGM Panel */}
        <div className="ui-card space-y-4 !p-4">
          <h3 className="flex items-center gap-1.5 text-xs font-semibold text-zinc-400">
            <Music className="h-4 w-4 text-amber-500" />
            背景伴奏 BGM 混音配乐
          </h3>

          <div className="space-y-3">
            <div>
              <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                选择背景配乐 / Background Audio
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-[minmax(0,1fr)_auto_auto] gap-2">
                <Select
                  value={bgm}
                  onChange={(e) => handleBgmChange(e.target.value)}
                  className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                >
                  {bgmOptions.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}{b.author ? ` · ${b.author}` : ""}
                    </option>
                  ))}
                </Select>
                <button
                  type="button"
                  onClick={() => selectedBgm?.src && toggleBgmListen(selectedBgm.id)}
                  disabled={!selectedBgm?.src}
                  className={`px-2.5 py-1.5 rounded border text-xs font-medium flex items-center justify-center gap-1 transition-colors disabled:opacity-50 ${
                    playingBgm === selectedBgm?.id
                      ? "bg-amber-500/10 border-amber-500/20 text-amber-400"
                      : "bg-[#17181c] border-zinc-800 text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  <Volume2 className="w-3.5 h-3.5" />
                  {playingBgm === selectedBgm?.id ? "暂停" : "试听"}
                </button>
                <button
                  type="button"
                  onClick={openCustomBgmFolder}
                  className="px-2.5 py-1.5 rounded border border-zinc-800 bg-[#17181c] text-xs font-medium text-zinc-400 hover:text-zinc-100 hover:border-amber-500/40 flex items-center justify-center gap-1 transition-colors"
                  title="打开自定义音乐文件夹"
                >
                  <FolderOpen className="w-3.5 h-3.5 text-amber-500" />
                  自定义音乐文件夹
                </button>
              </div>
              {selectedBgm?.src && (
                <audio
                  ref={bgmPreviewRef}
                  src={selectedBgm.src}
                  controls
                  preload="metadata"
                  className="w-full h-8 mt-2"
                  onPause={() => setPlayingBgm(null)}
                  onPlay={() => setPlayingBgm(selectedBgm.id)}
                />
              )}
            </div>

            <div className="pt-2">
              <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                <span>配乐音量: {volume}%</span>
                <span>主旁白自动避让降噪</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                value={volume}
                onChange={(e) => setVolume(parseInt(e.target.value))}
                className="w-full accent-amber-500 h-1 cursor-pointer bg-zinc-850 rounded"
              />
            </div>
          </div>
        </div>
      </div>
      </div>
      {/* End step voice */}

      {/* Step style: aspect / subtitles / workflows */}
      <div className={showStyleStep ? "space-y-5 animate-soft-scale-in" : "hidden"}>
      <div id="stage-style" className="space-y-4 scroll-mt-24">
      {/* Image style and motion composition */}
      <div className="ui-card space-y-4 !p-4">
        <div className="flex items-center justify-between gap-3 border-b border-[var(--color-border-subtle)] pb-2">
          <h3 className="flex items-center gap-1.5 text-xs font-semibold text-zinc-400">
            <FileVideo className="h-4 w-4 text-amber-500" />
            画幅 · 字幕 · 画风
          </h3>
          <button
            type="button"
            onClick={() => setShowAdvancedProduction((open) => !open)}
            className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200"
          >
            {showAdvancedProduction ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            {showAdvancedProduction ? "收起高级" : "更多设定"}
          </button>
        </div>

        {/* Always-visible essentials: aspect + motion/subtitle toggles appear below; advanced block holds prefix/test/subtitle detail */}
        <div className={showAdvancedProduction ? "space-y-3" : "hidden"}>
          <div>
            <div className="flex items-center justify-between gap-3 mb-1">
              <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
                画风提示词前缀
              </label>
              <button
                type="button"
                onClick={handleSavePromptPrefix}
                disabled={savingPromptPrefix}
                className="px-2.5 py-1 bg-[#17181c] text-zinc-300 hover:text-white rounded border border-zinc-800 hover:border-amber-500/40 text-[10px] font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
                title="保存当前提示词前缀"
              >
                {savingPromptPrefix ? <Loader className="w-3 h-3 animate-spin text-amber-500" /> : <Save className="w-3 h-3 text-amber-500" />}
                保存提示词
              </button>
            </div>
            <textarea
              value={promptPrefix}
              onChange={(e) => setPromptPrefix(e.target.value)}
              rows={3}
              className="w-full bg-[#17181c] border border-zinc-800 rounded px-2.5 py-2 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 font-mono resize-none leading-relaxed"
              placeholder="输入会固定拼接在每个分镜画面提示词前面的底模风格参数"
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_260px] gap-3">
            <div className="bg-[#17181c] border border-zinc-850 rounded-md p-3 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <label className="text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
                  测试出图提示词 / Test Prompt
                </label>
                <span className="text-[9px] text-zinc-600 font-mono truncate">
                  使用图片运动生成比例 · {currentWorkflow?.name || "Default workflow"} · {imageWidth}x{imageHeight}
                </span>
              </div>
              <p className="text-[10px] text-amber-400/80">测试图仅供预览，不会复用到最终成片。</p>
              <textarea
                value={testImagePrompt}
                onChange={(e) => setTestImagePrompt(e.target.value)}
                rows={3}
                className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-2 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 resize-none leading-relaxed"
                placeholder="输入一条用于测试当前前缀画风的画面提示词"
              />
              <div className="flex justify-end">
                <button
                  onClick={handleTestImageGenerate}
                  disabled={testingImage}
                  className="px-3 py-1.5 bg-zinc-800 text-zinc-300 hover:text-white rounded border border-zinc-750 hover:border-amber-500/40 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
                >
                  {testingImage ? <Loader className="w-3.5 h-3.5 animate-spin text-amber-500" /> : <Sparkles className="w-3.5 h-3.5 text-amber-500" />}
                  生成测试图
                </button>
              </div>
            </div>

            <div className="bg-[#17181c] border border-dashed border-zinc-800 rounded-md min-h-44 overflow-hidden flex items-center justify-center">
              {testingImage ? (
                <div className="text-center text-xs text-zinc-500 space-y-2 px-4">
                  <Loader className="w-5 h-5 animate-spin text-amber-500 mx-auto" />
                  <p>正在测试出图...</p>
                </div>
              ) : testImageUrl ? (
                <img
                  src={testImageUrl}
                  alt="测试出图预览"
                  className="w-full h-full min-h-44 object-cover"
                />
              ) : testImageError ? (
                <div className="text-center text-[11px] text-rose-400 leading-relaxed px-4">
                  {testImageError}
                </div>
              ) : (
                <div className="text-center text-xs text-zinc-500 space-y-2 px-4">
                  <Eye className="w-5 h-5 text-zinc-650 mx-auto" />
                  <p>测试出图区域</p>
                  <p className="text-[10px] text-zinc-600">生成后将在这里预览当前前缀画风效果</p>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="p-3 bg-[#17181c] border border-zinc-850 rounded-md space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                  图片/视频画布比例 / Output Size
                </label>
                <Select
                  value={imageAspectRatio}
                  onChange={(e) => applyImageSizePreset(e.target.value)}
                  className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                >
                  {IMAGE_SIZE_PRESETS.map((preset) => (
                    <option key={preset.id} value={preset.id}>
                      {preset.label} · {preset.id === "custom" ? "手动输入" : `${preset.width}x${preset.height}`}
                    </option>
                  ))}
                </Select>
                <p className="mt-1 text-[10px] text-zinc-600 leading-relaxed">
                  此尺寸会同时用于生成图片素材和最终视频画布
                </p>
              </div>
              <div>
                <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                  宽度 / Width
                </label>
                <input
                  type="number"
                  min="512"
                  max="3840"
                  step="16"
                  value={imageWidth}
                  onChange={(e) => {
                    setImageAspectRatio("custom");
                    setImageWidth(parseInt(e.target.value || "1024"));
                  }}
                  className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                />
              </div>
              <div>
                <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                  高度 / Height
                </label>
                <input
                  type="number"
                  min="512"
                  max="3840"
                  step="16"
                  value={imageHeight}
                  onChange={(e) => {
                    setImageAspectRatio("custom");
                    setImageHeight(parseInt(e.target.value || "1536"));
                  }}
                  className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="flex items-center gap-3 cursor-pointer p-1">
              <input
                type="checkbox"
                checked={enableMotion}
                onChange={(e) => setEnableMotion(e.target.checked)}
                className="accent-amber-500 w-4 h-4 rounded"
              />
              <div>
                <span className="text-xs font-semibold text-zinc-300 block">开启镜头 3D 微动效果</span>
                <span className="text-[10px] text-zinc-500 block">通过深度估算添加摄像机推拉摇移</span>
              </div>
            </label>

            <label className="flex items-center gap-3 cursor-pointer p-1">
              <input
                type="checkbox"
                checked={enableSubtitles}
                onChange={(e) => setEnableSubtitles(e.target.checked)}
                className="accent-amber-500 w-4 h-4 rounded"
              />
              <div>
                <span className="text-xs font-semibold text-zinc-300 block">添加高清晰中文字幕</span>
                <span className="text-[10px] text-zinc-500 block">自动对其 TTS 脚本音频进行叠字渲染</span>
              </div>
            </label>

            {enableSubtitles && (
              <div className="sm:col-span-2 bg-[#17181c] border border-zinc-900 rounded p-3 space-y-3">
                <SubtitleStylePreview style={subtitleStyle} />

                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-zinc-300">字幕渲染</span>
                  <Select
                    value={subtitleStyle.mode === "hyperframes" ? "hyperframes" : "ass"}
                    onChange={(e) => updateSubtitleStyle({ mode: e.target.value as SubtitleStyle["mode"] })}
                    className="bg-[#101114] border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                  >
                    <option value="ass">标准字幕</option>
                    <option value="hyperframes">动态字幕</option>
                  </Select>
                </div>

                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-zinc-300">字幕样式</span>
                  <Select
                    value={subtitleStyle.preset}
                    onChange={(e) => handleSubtitlePresetChange(e.target.value as SubtitleStyle["preset"])}
                    className="bg-[#101114] border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                  >
                    <option value="short-video-bold">短视频粗体</option>
                    <option value="clean-white">清爽白字</option>
                    <option value="cinema-soft">电影柔光</option>
                    <option value="caption-box">字幕黑底框</option>
                  </Select>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-2 items-start">
                  <div>
                    <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                      字体 / Font
                    </label>
                    <FontSelect
                      value={subtitleStyle.fontPath || ""}
                      fonts={fontOptions}
                      onChange={handleSubtitleFontChange}
                      className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                      previewText="让每一帧，都更有表达力 Aa 123"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={openCustomFontFolder}
                    className="self-end inline-flex items-center justify-center gap-1.5 bg-[#101114] border border-zinc-800 hover:border-amber-500/60 text-zinc-300 rounded px-3 py-1.5 text-xs transition-colors"
                  >
                    <FolderOpen className="w-3.5 h-3.5" />
                    自定义字体文件夹
                  </button>
                  <button
                    type="button"
                    onClick={refreshFonts}
                    title="刷新字体列表"
                    aria-label="刷新字体列表"
                    className="self-end inline-flex items-center justify-center gap-1.5 bg-[#101114] border border-zinc-800 hover:border-amber-500/60 text-zinc-300 rounded px-3 py-1.5 text-xs transition-colors"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    刷新字体
                  </button>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-5 gap-2">
                  <div>
                    <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                      字号
                    </label>
                    <input
                      type="number"
                      min="12"
                      max="120"
                      value={subtitleStyle.fontSize}
                      onChange={(e) => updateSubtitleStyle({ fontSize: parseInt(e.target.value || "52", 10) })}
                      className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                      描边
                    </label>
                    <input
                      type="number"
                      min="0"
                      max="12"
                      value={subtitleStyle.outlineWidth}
                      onChange={(e) => updateSubtitleStyle({ outlineWidth: parseInt(e.target.value || "3", 10) })}
                      className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                      底部距离
                    </label>
                    <input
                      type="number"
                      min="0"
                      max="600"
                      value={subtitleStyle.marginV}
                      onChange={(e) => updateSubtitleStyle({ marginV: parseInt(e.target.value || "120", 10) })}
                      className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                      每行字数
                    </label>
                    <input
                      type="number"
                      min="4"
                      max="40"
                      value={subtitleStyle.maxCharsPerLine}
                      onChange={(e) => updateSubtitleStyle({ maxCharsPerLine: parseInt(e.target.value || "14", 10) })}
                      className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                      阴影
                    </label>
                    <input
                      type="number"
                      min="0"
                      max="12"
                      value={subtitleStyle.shadow}
                      onChange={(e) => updateSubtitleStyle({ shadow: parseInt(e.target.value || "0", 10) })}
                      className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
                  {[
                    ["文字", "primaryColor"],
                    ["强调", "accentColor"],
                    ["描边色", "outlineColor"],
                    ["底色", "backColor"],
                  ].map(([label, key]) => (
                    <label key={key} className="block">
                      <span className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                        {label}
                      </span>
                      <input
                        type="color"
                        value={subtitleStyle[key as keyof SubtitleStyle] as string}
                        onChange={(e) => updateSubtitleStyle({ [key]: e.target.value } as Partial<SubtitleStyle>)}
                        className="w-full h-8 bg-[#101114] border border-zinc-900 rounded px-1 py-1"
                      />
                    </label>
                  ))}
                </div>

                <div className="border-t border-zinc-800 pt-3 space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <span className="text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
                      高亮显示
                    </span>
                    {mode === "ai" ? (
                      <button
                        type="button"
                        onClick={() => document.getElementById("keyword-extraction")?.scrollIntoView({ behavior: "smooth", block: "center" })}
                        className="inline-flex items-center justify-center gap-1.5 rounded border border-zinc-800 px-2.5 py-1 text-[11px] text-zinc-400 hover:border-amber-500/40 hover:text-zinc-200"
                      >
                        <Sparkles className="w-3 h-3" />
                        已选 {(subtitleStyle.highlightWords || []).length} 个词 · 编辑
                      </button>
                    ) : (
                      <span className="text-[11px] text-zinc-500">已选 {(subtitleStyle.highlightWords || []).length} 个词</span>
                    )}
                  </div>
                  {mode !== "ai" && renderSelectedKeywordEditor()}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    {dynamicSubtitleEnabled && (
                      <>
                        <div>
                          <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">高亮样式</label>
                          <Select
                            value={subtitleStyle.highlightStyle || "accent"}
                            onChange={(e) => updateSubtitleStyle({ highlightStyle: e.target.value as NonNullable<SubtitleStyle["highlightStyle"]> })}
                            className="w-full bg-[#0c0d10] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                          >
                            <option value="accent">强调色</option>
                            <option value="pop">加粗强调</option>
                            <option value="badge">色块徽标</option>
                          </Select>
                        </div>
                        <div>
                          <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">高亮缩放</label>
                          <input
                            type="number"
                            min="100"
                            max="180"
                            value={subtitleStyle.highlightScale || 125}
                            onChange={(e) => updateSubtitleStyle({ highlightScale: parseInt(e.target.value || "125", 10) })}
                            className="w-full bg-[#0c0d10] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                          />
                        </div>
                      </>
                    )}
                    {(dynamicSubtitleEnabled || subtitleStyle.preset === "caption-box") && (
                      <div>
                        <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">底色透明度</label>
                        <input
                          type="number"
                          min="0"
                          max="100"
                          value={subtitleStyle.backgroundOpacity ?? 72}
                          onChange={(e) => updateSubtitleStyle({ backgroundOpacity: parseInt(e.target.value || "72", 10) })}
                          className="w-full bg-[#0c0d10] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                        />
                      </div>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">缓入 ms</label>
                      <input
                        type="number"
                        min="0"
                        max="1000"
                        value={subtitleStyle.fadeInMs ?? 120}
                        onChange={(e) => updateSubtitleStyle({ fadeInMs: parseInt(e.target.value || "120", 10) })}
                        className="w-full bg-[#0c0d10] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">缓出 ms</label>
                      <input
                        type="number"
                        min="0"
                        max="1000"
                        value={subtitleStyle.fadeOutMs ?? 120}
                        onChange={(e) => updateSubtitleStyle({ fadeOutMs: parseInt(e.target.value || "120", 10) })}
                        className="w-full bg-[#0c0d10] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                      />
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
                  <div>
                    <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                      分段方式
                    </label>
                    <Select
                      value={subtitleStyle.segmentMode}
                      onChange={(e) => updateSubtitleStyle({ segmentMode: e.target.value as SubtitleStyle["segmentMode"] })}
                      className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                    >
                      <option value="sentence">按标点切分（一行一句、去标点）</option>
                      <option value="phrase">按字数切分</option>
                      <option value="line">按换行切分</option>
                    </Select>
                  </div>
                  <div>
                    <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                      行数
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="4"
                      value={subtitleStyle.maxLines}
                      onChange={(e) => updateSubtitleStyle({ maxLines: parseInt(e.target.value || "2", 10) })}
                      className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                      动画
                    </label>
                    <Select
                      value={dynamicSubtitleEnabled || subtitleStyle.animation !== "word-pop" ? subtitleStyle.animation : "fade"}
                      onChange={(e) => updateSubtitleStyle({ animation: e.target.value as SubtitleStyle["animation"] })}
                      className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                    >
                      <option value="fade">淡入淡出</option>
                      <option value="pop">整段弹跳</option>
                      {dynamicSubtitleEnabled && <option value="word-pop">重点逐词弹入</option>}
                      <option value="none">无动画</option>
                    </Select>
                  </div>
                  <div>
                    <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                      对齐
                    </label>
                    <Select
                      value={String(subtitleStyle.alignment)}
                      onChange={(e) => updateSubtitleStyle({ alignment: parseInt(e.target.value, 10) })}
                      className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                    >
                      <option value="1">左下</option>
                      <option value="2">居中</option>
                      <option value="3">右下</option>
                    </Select>
                  </div>
                </div>
              </div>
            )}
            </div>
          </div>

      </div>

      {/* ComfyUI Media Workflows selections */}
      <div className="ui-card space-y-4 !p-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="flex items-center gap-1.5 text-xs font-semibold text-zinc-400">
            <Workflow className="h-4 w-4 text-amber-500" />
            画面工作流
          </h3>
          <button
            type="button"
            onClick={() => setWorkflowsCollapsed((current) => !current)}
            className="w-7 h-7 inline-flex items-center justify-center rounded border border-zinc-800 bg-[#17181c] text-zinc-400 hover:text-zinc-100 hover:border-amber-500/40 transition-colors"
            title={workflowsCollapsed ? "展开 Workflows" : "折叠 Workflows"}
            aria-label={workflowsCollapsed ? "展开 Workflows" : "折叠 Workflows"}
          >
            {workflowsCollapsed ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronUp className="w-3.5 h-3.5" />}
          </button>
        </div>

        {!workflowsCollapsed && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-h-[360px] overflow-y-auto pr-1">
            {workflowOptions.length === 0 && (
              <div className="sm:col-span-3 border border-dashed border-zinc-800 rounded p-6 text-center text-xs text-zinc-500">
                正在等待后端工作流资源...
              </div>
            )}
            {workflowOptions.map((wf) => (
              <div
                key={wf.id}
                onClick={() => setWorkflowId(wf.id)}
                className={`p-3 rounded border text-left cursor-pointer transition-colors ${
                  workflowId === wf.id
                    ? "bg-[#17181c] border-amber-500/30 text-amber-400"
                    : "bg-[#121316] border-zinc-900 text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <div className="flex justify-between items-start mb-1">
                  <span className="text-[11px] font-semibold text-zinc-200 block truncate">{wf.name}</span>
                  <span className="text-[8px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-1 py-0.5 rounded font-mono">
                    {wf.source}
                  </span>
                </div>
                <span className="text-[9px] font-mono text-zinc-500 block">类型: {wf.type} | {wf.resolution}</span>
                <p className="text-[10px] text-zinc-400 leading-relaxed mt-2 line-clamp-2">
                  {wf.desc}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
      </div>
      </div>
      {/* End step style */}

      {/* Step 4: Review */}
      <div className={showReviewStep ? "space-y-5 animate-soft-scale-in" : "hidden"}>
      <section id="stage-review" className="ui-card space-y-3 scroll-mt-24 ring-1 ring-amber-500/20" aria-labelledby="generation-review-title">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 id="generation-review-title" className="text-sm font-semibold text-zinc-200">生成前核对</h3>
            <p className="text-xs text-zinc-400 mt-1">确认数量与关键参数。提交后仍可在任务面板取消。</p>
          </div>
          <span className="text-caption text-amber-400 border border-amber-500/20 rounded px-2 py-1">
            {mode === "batch" ? "批量视频" : "单视频"}
          </span>
        </div>
        <dl className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          {[
            ["视频数量", `${reviewVideoCount}`],
            ["分镜总数", `${reviewSceneCount}`],
            ["配音", `${ttsMode} · ${voice}`],
            ["工作流", currentWorkflow?.name || workflowId || "未选择"],
            ["画布", `${imageWidth} × ${imageHeight}`],
            ["字幕", enableSubtitles ? `${subtitleStyle.fontSize}px · ${subtitleStyle.fontFamily || "自动中文字体"}` : "关闭"],
            ["背景音乐", selectedBgm?.name || "无背景音乐"],
            ["生成策略", effectiveReuseSourceTaskId ? `复用素材${reuseLabel ? ` · ${reuseLabel}` : ""}` : "完整生成"],
            ["预计旁白", `约 ${Math.ceil(reviewNarrationSeconds / 60)} 分钟`],
          ].map(([label, value]) => (
            <div key={label} className="bg-[#17181c] border border-zinc-900 rounded p-2 min-w-0">
              <dt className="text-zinc-500 mb-1">{label}</dt>
              <dd className="text-zinc-200 truncate" title={value}>{value}</dd>
            </div>
          ))}
        </dl>

        {mode !== "batch" && (latestCompletedTaskId || reuseSourceTaskId) && (
          <label className="flex items-start gap-2 rounded-md border border-zinc-800 bg-[#0c0d10] p-3 text-sm text-zinc-300 cursor-pointer">
            <input
              type="checkbox"
              checked={reuseAssetsEnabled}
              onChange={(event) => {
                setReuseAssetsEnabled(event.target.checked);
                if (event.target.checked && !reuseSourceTaskId && latestCompletedTaskId) {
                  setReuseSourceTaskId(latestCompletedTaskId);
                }
              }}
              className="mt-0.5 accent-amber-500"
            />
            <span>
              沿用历史素材（配音/图片优先复用）
              {reuseLabel && (
                <span className="block text-xs text-zinc-500 mt-0.5">来源：{reuseLabel}</span>
              )}
              {!reuseLabel && (
                <span className="block text-xs text-zinc-500 mt-0.5">将使用最近完成的快捷创作任务</span>
              )}
            </span>
          </label>
        )}

        <label className={`flex items-start gap-2 text-sm text-zinc-300 cursor-pointer ${fieldErrors.review ? "text-rose-300" : ""}`}>
          <input
            type="checkbox"
            checked={reviewConfirmed}
            onChange={(event) => {
              setReviewConfirmed(event.target.checked);
              if (event.target.checked) setFieldErrors((prev) => ({ ...prev, review: undefined }));
            }}
            className="mt-0.5 accent-amber-500"
          />
          <span>
            我已核对以上配置，确认
            {mode === "batch" ? `创建 ${reviewVideoCount} 个视频任务` : "提交生成"}。
          </span>
        </label>
        {fieldErrors.review && <p className="text-xs text-rose-400">{fieldErrors.review}</p>}
        {fieldErrors.tts && <p className="text-xs text-rose-400">{fieldErrors.tts}</p>}
      </section>
      </div>
      {/* End step review */}

      <CreateStickyFooter
        expertMode={expertMode}
        wizardStep={wizardStep}
        mode={mode}
        isSubmitting={isSubmitting}
        contentReady={contentReady}
        styleReady={styleReady}
        voiceReady={voiceReady}
        reviewConfirmed={reviewConfirmed}
        reviewVideoCount={reviewVideoCount}
        canCreateProject={Boolean(onCreateProject)}
        onBack={handleWizardBack}
        onNext={handleWizardNext}
        onSubmitWorkbench={() => void handleTriggerRender(false)}
        onSubmitDirect={() => void handleTriggerRender(true)}
      />
    </div>
  );
};
