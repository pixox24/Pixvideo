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
import { extractHighlightKeywords, formatApiErrorValue } from "../lib/api";

interface QuickCreateProps {
  onGenerateTask: (taskInput: any) => Promise<string | null>;
  onCreateProject?: (input: QuickCreateInput) => Promise<void>;
  latestCompletedTaskId?: string | null;
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
}

const DEFAULT_PREVIEW_TTS_TEXT = "这是一段 TTS 试听文案，用来检查音色、语速和发音效果。";
const QUICK_CREATE_DRAFT_KEY = "pixvideo.quick-create.draft.v1";

const QUICK_CREATE_STAGES = [
  { id: "content", label: "内容", anchor: "stage-content" },
  { id: "storyboard", label: "分镜", anchor: "stage-storyboard" },
  { id: "production", label: "声音与画面", anchor: "stage-production" },
  { id: "review", label: "核对并生成", anchor: "stage-review" },
  { id: "progress", label: "进度与结果", anchor: "" },
] as const;

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
  mode: "ass",
  preset: "short-video-bold",
  fontFamily: "",
  fontPath: "",
  fontSize: 52,
  primaryColor: "#FFFFFF",
  accentColor: "#FFD43B",
  outlineColor: "#000000",
  backColor: "#000000",
  outlineWidth: 3,
  shadow: 0,
  marginV: 120,
  alignment: 2,
  maxCharsPerLine: 14,
  maxLines: 2,
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
}) => {
  // Main states
  const [mode, setMode] = useState<"ai" | "manual" | "batch">("ai");
  const [title, setTitle] = useState("新品发布创意科技短视频");
  
  // AI Creation states
  const [aiTopic, setAiTopic] = useState("探索未来世界的智能机器人生活碎片");
  const [aiSceneCount, setAiSceneCount] = useState(5);
  const [aiLoading, setAiLoading] = useState(false);
  const [copyDraftMode, setCopyDraftMode] = useState<"full" | "segmented">("full");
  const [copyDraft, setCopyDraft] = useState("");
  const [copyDraftLoading, setCopyDraftLoading] = useState(false);
  const [copyCharCount, setCopyCharCount] = useState(() => suggestCopyCharCount(5));
  const [copyCharCountTouched, setCopyCharCountTouched] = useState(false);
  const [copyCharCountMode, setCopyCharCountMode] = useState<"around" | "within">("around");

  // Manual Creation states (Scenes list)
  const [scenes, setScenes] = useState<Array<{ id: number; ttsText: string; visualPrompt: string }>>([
    { id: 1, ttsText: "这是一个科技感爆棚的高能概念画卷。", visualPrompt: "Cinematic digital art of high-tech lab, warm amber lighting, futuristic, 4k" },
    { id: 2, ttsText: "每一个齿轮的咬合，都是精工美学的体现。", visualPrompt: "Macro close-up of amber golden machine gears interlocking in motion, cinematic depth of field" }
  ]);

  // Batch Creation states
  const [batchInput, setBatchInput] = useState("主题一: 智能机器人在雨夜撑伞\n主题二: 机械宠物狗在客厅嬉戏\n主题三: 未来城市空中飞车速递");
  const [batchCount, setBatchCount] = useState(3);
  const [splitType, setSplitType] = useState<"paragraph" | "line" | "sentence">("line");

  // BGM states
  const [bgm, setBgm] = useState("bgm-none");
  const [volume, setVolume] = useState(30);
  const [playingBgm, setPlayingBgm] = useState<string | null>(null);
  const bgmPreviewRef = React.useRef<HTMLAudioElement | null>(null);

  // TTS States
  const [ttsMode, setTtsMode] = useState<"edge" | "comfyui" | "minimax">("minimax");
  const [voice, setVoice] = useState("male-qn-qingse");
  const [speed, setSpeed] = useState(1.0);
  const [emotion, setEmotion] = useState("");
  const [minimaxModel, setMinimaxModel] = useState("speech-2.8-turbo");
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
  const [keywordLoading, setKeywordLoading] = useState(false);
  const [imageAspectRatio, setImageAspectRatio] = useState("1024x1536");
  const [imageWidth, setImageWidth] = useState(1024);
  const [imageHeight, setImageHeight] = useState(1536);

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
  const [activeStage, setActiveStage] = useState<(typeof QUICK_CREATE_STAGES)[number]["id"]>("content");
  const [draftSavedAt, setDraftSavedAt] = useState<string | null>(null);
  const [reuseSourceTaskId, setReuseSourceTaskId] = useState<string | null>(null);
  const draftReadyRef = React.useRef(false);
  const draftRecoveredRef = React.useRef(false);
  const reviewReadyRef = React.useRef(false);
  const submissionLockRef = React.useRef(false);

  const bgmOptions = resources.bgm;
  const workflowOptions = resources.workflows;
  const fontOptions = resources.fonts || [];
  const selectedBgm = bgmOptions.find((item) => item.id === bgm);
  const effectiveReuseSourceTaskId = reuseSourceTaskId || latestCompletedTaskId || null;
  const lastAppliedPresetId = React.useRef<string | null>(null);

  const normalizeSubtitleStyle = (value?: Partial<SubtitleStyle>): SubtitleStyle => ({
    ...DEFAULT_SUBTITLE_STYLE,
    ...(value || {}),
    fontSize: clampNumber(value?.fontSize, 52, 12, 120),
    outlineWidth: clampNumber(value?.outlineWidth, 3, 0, 12),
    shadow: clampNumber(value?.shadow, 0, 0, 12),
    marginV: clampNumber(value?.marginV, 120, 0, 600),
    alignment: clampNumber(value?.alignment, 2, 1, 9),
    maxCharsPerLine: clampNumber(value?.maxCharsPerLine, 14, 4, 40),
    maxLines: clampNumber(value?.maxLines, 2, 1, 4),
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
          if (typeof draft.aiSceneCount === "number") setAiSceneCount(draft.aiSceneCount);
          if (["full", "segmented"].includes(draft.copyDraftMode)) setCopyDraftMode(draft.copyDraftMode);
          if (typeof draft.copyCharCount === "number") {
            setCopyCharCount(draft.copyCharCount);
            setCopyCharCountTouched(true);
          }
          if (["around", "within"].includes(draft.copyCharCountMode)) setCopyCharCountMode(draft.copyCharCountMode);
          if (["paragraph", "line", "sentence"].includes(draft.splitType)) setSplitType(draft.splitType);
          if (typeof draft.workflowId === "string") setWorkflowId(draft.workflowId);
          if (["edge", "comfyui", "minimax"].includes(draft.ttsMode)) setTtsMode(draft.ttsMode);
          if (typeof draft.voice === "string") setVoice(draft.voice);
          if (typeof draft.speed === "number") setSpeed(draft.speed);
          if (typeof draft.minimaxModel === "string") setMinimaxModel(draft.minimaxModel);
          if (typeof draft.emotion === "string") setEmotion(draft.emotion);
          if (typeof draft.bgm === "string") setBgm(draft.bgm);
          if (typeof draft.volume === "number") setVolume(draft.volume);
          if (typeof draft.promptPrefix === "string") setPromptPrefix(draft.promptPrefix);
          if (typeof draft.enableMotion === "boolean") setEnableMotion(draft.enableMotion);
          if (typeof draft.enableSubtitles === "boolean") setEnableSubtitles(draft.enableSubtitles);
          if (typeof draft.imageAspectRatio === "string") setImageAspectRatio(draft.imageAspectRatio);
          if (typeof draft.imageWidth === "number") setImageWidth(draft.imageWidth);
          if (typeof draft.imageHeight === "number") setImageHeight(draft.imageHeight);
          if (typeof draft.reuseSourceTaskId === "string") setReuseSourceTaskId(draft.reuseSourceTaskId);
          if (draft.subtitleStyle) setSubtitleStyle(normalizeSubtitleStyle(draft.subtitleStyle));
          setDraftSavedAt(typeof draft.savedAt === "string" ? draft.savedAt : null);
        }
      }
    } catch {
      localStorage.removeItem(QUICK_CREATE_DRAFT_KEY);
    } finally {
      draftReadyRef.current = true;
    }
  }, []);

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
        copyDraft,
        copyDraftMode,
        copyCharCount,
        copyCharCountMode,
        splitType,
        batchInput,
        scenes,
        workflowId,
        ttsMode,
        voice,
        speed,
        minimaxModel,
        emotion,
        bgm,
        volume,
        promptPrefix,
        enableMotion,
        enableSubtitles,
        imageAspectRatio,
        imageWidth,
        imageHeight,
        reuseSourceTaskId,
        subtitleStyle: normalizeSubtitleStyle(subtitleStyle),
      }));
      setDraftSavedAt(savedAt);
    }, 500);
    return () => window.clearTimeout(timeoutId);
  }, [mode, title, aiTopic, aiSceneCount, copyDraft, copyDraftMode, copyCharCount, copyCharCountMode, splitType, batchInput, scenes, workflowId, ttsMode, voice, speed, minimaxModel, emotion, bgm, volume, promptPrefix, enableMotion, enableSubtitles, imageAspectRatio, imageWidth, imageHeight, subtitleStyle, reuseSourceTaskId]);

  // Invalidate the review whenever a submitted production setting changes.
  React.useEffect(() => {
    if (!reviewReadyRef.current) {
      reviewReadyRef.current = true;
      return;
    }
    setReviewConfirmed(false);
  }, [mode, title, copyDraft, copyDraftMode, aiSceneCount, splitType, batchInput, scenes, workflowId, ttsMode, voice, speed, minimaxModel, emotion, bgm, volume, promptPrefix, enableMotion, enableSubtitles, imageWidth, imageHeight, subtitleStyle]);

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
    if (bgmOptions.length === 0) return;
    if (!bgmOptions.some((item) => item.id === bgm)) {
      setBgm("bgm-none");
    }
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
  };

  const handleExtractKeywords = async () => {
    const text = keywordSourceText();
    if (!text) {
      addToast("请先填写旁白或主题，再提取高亮词。", "error");
      return;
    }
    setKeywordLoading(true);
    try {
      const keywords = await extractHighlightKeywords(text, 8);
      if (!keywords.length) {
        addToast("未提取到可用高亮词，请手动填写。", "info");
        return;
      }
      const colors: Record<string, string> = {};
      for (const item of keywords) colors[item.word] = item.color;
      applyHighlightKeywords(
        keywords.map((item) => item.word),
        colors,
      );
      addToast(`已提取 ${keywords.length} 个高亮词`, "success");
    } catch (err: any) {
      addToast(err.message || "高亮词提取失败。", "error");
    } finally {
      setKeywordLoading(false);
    }
  };

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
    const previewServiceName = ttsMode === "minimax" ? "MiniMax" : ttsMode === "comfyui" ? "ComfyUI" : "Edge";
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
    const copyServiceName = ttsMode === "minimax" ? "MiniMax" : ttsMode === "comfyui" ? "ComfyUI" : "Edge";
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
      if (activePreset.sceneCount) setAiSceneCount(activePreset.sceneCount);
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

  const handleGenerateCopyDraft = async () => {
    if (!aiTopic.trim()) {
      addToast("请输入创作主题，以便 AI 生成文案草稿", "error");
      return;
    }

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
        maybeSyncCopyDraftToPreviewTts(draftText);
        addToast("AI 文案草稿已生成，你可以先预览或编辑。", "success");
      } else {
        addToast(formatApiErrorValue(resData.detail) || formatApiErrorValue(resData.error) || "文案草稿生成异常，请检查 LLM 设置。", "error");
      }
    } catch (err: any) {
      addToast("连接服务器超时，请确保 dev 服务器就绪。", "error");
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
          splitType
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
        addToast(`AI 分镜脚本生成就绪！已帮您切分成 ${generated.length} 个分镜，您可直接在下方编辑或点击渲染。`, "success");
      } else {
        addToast(formatApiErrorValue(resData.detail) || formatApiErrorValue(resData.error) || "脚本构思异常，请检查 LLM 设置。", "error");
      }
    } catch (err: any) {
      addToast("连接服务器超时，请确保 dev 服务器就绪。", "error");
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

  const splitDraftByCurrentRule = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return [];

    if (splitType === "paragraph") {
      return trimmed.split(/\n\s*\n/).map((segment) => segment.trim()).filter(Boolean);
    }

    if (splitType === "sentence") {
      return trimmed.match(/[^。！？.!?\n]+[。！？.!?]?/g)?.map((segment) => segment.trim()).filter(Boolean) || [];
    }

    return trimmed.split(/\r?\n/).map((segment) => segment.trim()).filter(Boolean);
  };

  const rebalanceDraftSegments = (segments: string[], targetCount: number) => {
    const cleanSegments = segments.map((segment) => segment.trim()).filter(Boolean);
    const safeTargetCount = Math.max(1, targetCount);

    if (cleanSegments.length === safeTargetCount) return cleanSegments;

    if (cleanSegments.length > safeTargetCount) {
      return Array.from({ length: safeTargetCount }, (_, index) => {
        const start = Math.floor((index * cleanSegments.length) / safeTargetCount);
        const end = Math.floor(((index + 1) * cleanSegments.length) / safeTargetCount);
        return cleanSegments.slice(start, Math.max(end, start + 1)).join("").trim();
      }).filter(Boolean);
    }

    const mergedText = cleanSegments.join("");
    if (!mergedText) return [];

    const chars = Array.from(mergedText);
    const chunkSize = Math.ceil(chars.length / safeTargetCount);
    return Array.from({ length: safeTargetCount }, (_, index) =>
      chars.slice(index * chunkSize, (index + 1) * chunkSize).join("").trim()
    ).filter(Boolean);
  };

  const splitFullCopyDraftForRender = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return [];

    const units = splitDraftByCurrentRule(text);
    return rebalanceDraftSegments(units, aiSceneCount);
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

      const draftSegments =
        copyDraftMode === "full"
          ? splitFullCopyDraftForRender(draftText)
          : splitDraftByCurrentRule(draftText);

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

  const buildVisualPromptFallback = async (scenes: Array<{ ttsText: string; visualPrompt: string }>): Promise<Array<{ ttsText: string; visualPrompt: string }>> => {
    const missing = scenes.filter((scene) => !String(scene.visualPrompt || "").trim());
    if (missing.length === 0) return scenes;
    addToast(`正在为 ${missing.length} 个分镜自动生成画面提示词…`, "info");
    const response = await fetch("/api/generate-script", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: (aiTopic || title).trim(),
        sceneCount: missing.length,
        draftMode: "segmented",
        splitType: "paragraph",
        confirmedText: missing.map((scene) => scene.ttsText).join("\n\n"),
      }),
    });
    const resData = await response.json();
    if (!response.ok || !resData.success) {
      addToast(formatApiErrorValue(resData.detail) || formatApiErrorValue(resData.error) || "画面提示词自动生成失败，分镜将沿用旁白作为画面描述。", "info");
      return scenes;
    }
    const prompts: string[] = (resData.data || []).map((item: any) => String(item.visualPrompt || "").trim()).filter(Boolean);
    if (prompts.length === 0) {
      addToast("画面提示词自动生成失败，分镜将沿用旁白作为画面描述。", "info");
      return scenes;
    }
    let promptIndex = 0;
    return scenes.map((scene) => {
      if (String(scene.visualPrompt || "").trim()) return scene;
      if (promptIndex >= prompts.length) return scene;
      return { ...scene, visualPrompt: prompts[promptIndex++] };
    });
  };

  // Trigger main generator callback
  const handleTriggerRender = async (directGenerate = false) => {
    if (submissionLockRef.current) return;
    submissionLockRef.current = true;
    try {
    if (!title.trim()) {
      addToast("请先指定视频生产任务标题！", "error");
      return;
    }

    const renderScenes = buildScenesForRender();

    if (mode === "ai" && renderScenes.length === 0) {
      addToast("请先生成或填写确认文案，再开始生成视频。", "error");
      return;
    }

    if (mode === "manual" && renderScenes.some((s) => !s.ttsText.trim())) {
      addToast("检测到未填写的旁白文本，请完善每一个分镜！", "error");
      return;
    }

    if (renderScenes.length === 0) {
      addToast("没有可用于生成视频的文案内容。", "error");
      return;
    }

    if (!reviewConfirmed) {
      addToast("请先核对生成摘要并确认配置。", "error");
      return;
    }

      const taskInput = {
      title,
      tabType: "quick-create",
      workflowId,
      ttsMode,
      voice,
      speed,
      minimaxModel,
      emotion: emotion || undefined,
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
        scenes: renderScenes
      };

      if (mode !== "batch" && onCreateProject && !directGenerate) {
        const enrichedScenes = await buildVisualPromptFallback(renderScenes);
        await onCreateProject({ ...taskInput, scenes: enrichedScenes });
        setReviewConfirmed(false);
        return;
      }

      const requestGroupKey = crypto.randomUUID();
    setIsSubmitting(true);
    try {
      if (mode === "batch") {
        const taskInputs = buildBatchTaskInputs(taskInput, renderScenes, requestGroupKey);
        let successfulSubmissions = 0;
        await runWithConcurrency(taskInputs, 3, async (item) => {
          if (await onGenerateTask(item)) successfulSubmissions += 1;
        });
        const failedSubmissions = taskInputs.length - successfulSubmissions;
        if (failedSubmissions > 0) {
          addToast(
            `批量提交完成：成功 ${successfulSubmissions} 个，失败 ${failedSubmissions} 个。请查看任务面板中的失败原因。`,
            "error",
          );
        } else {
          addToast(`已提交 ${successfulSubmissions} 个独立视频任务。`, "success");
        }
        if (successfulSubmissions === 0) return;
      } else {
        const submittedTaskId = await onGenerateTask({ ...taskInput, clientRequestKey: requestGroupKey });
        if (!submittedTaskId) return;
        setReuseSourceTaskId(submittedTaskId);
      }
      setReviewConfirmed(false);
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
    await onDeletePreset(activePreset.id);
    setPresetMenuOpen(false);
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

  return (
    <div className="space-y-6 animate-fade-in w-full max-w-[1240px] mx-auto pb-10">
      <nav className="sticky top-0 z-20 -mx-1 p-1 bg-[#07080a]/95 backdrop-blur border border-zinc-900 rounded-lg" aria-label="快捷创作阶段">
        <ol className="grid grid-cols-5 gap-1">
          {QUICK_CREATE_STAGES.map((stage, index) => {
            const completed =
              stage.id === "content" ? Boolean(title.trim()) :
              stage.id === "storyboard" ? buildScenesForRender().length > 0 :
              stage.id === "production" ? Boolean(workflowId && voice) :
              stage.id === "review" ? reviewConfirmed : false;
            return (
              <li key={stage.id}>
                <button
                  type="button"
                  aria-current={activeStage === stage.id ? "step" : undefined}
                  onClick={() => {
                    setActiveStage(stage.id);
                    if (stage.anchor) {
                      document.getElementById(stage.anchor)?.scrollIntoView({ behavior: "smooth", block: "start" });
                    } else {
                      addToast("任务提交后可在任务面板或历史记录查看进度与结果。", "info");
                    }
                  }}
                  className={`w-full min-h-11 px-1.5 py-1.5 rounded text-[10px] sm:text-xs flex items-center justify-center gap-1 border transition-colors ${
                    activeStage === stage.id
                      ? "bg-amber-500/10 text-amber-400 border-amber-500/30"
                      : "bg-[#101114] text-zinc-400 border-zinc-900 hover:text-zinc-200"
                  }`}
                >
                  <span className="font-mono">{completed ? "✓" : index + 1}</span>
                  <span>{stage.label}</span>
                </button>
              </li>
            );
          })}
        </ol>
        <p className="px-2 pt-1 text-[10px] text-zinc-500" aria-live="polite">
          {draftSavedAt ? `草稿已自动保存 · ${new Date(draftSavedAt).toLocaleTimeString()}` : "草稿将在编辑后自动保存"}
        </p>
      </nav>

      {/* Task Header Title */}
      <div id="stage-content" className="bg-[#101114] border border-zinc-900 rounded-md p-3.5 space-y-3 scroll-mt-24">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex-1">
          <label htmlFor="quick-create-title" className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-0.5">
            当前生产项目名称 / Project Title
          </label>
          <input
            id="quick-create-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="bg-transparent border-b border-zinc-800 text-zinc-100 font-medium text-sm w-full py-0.5 focus:outline-none focus:border-amber-500 font-display transition-colors"
          />
        </div>
        <div className="text-[10px] text-zinc-600 font-mono">
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
      <div className="space-y-3">
        <label className="block text-xs font-semibold text-zinc-400">选择内容源创作模式</label>
        <div className="grid grid-cols-3 gap-2 p-1 bg-[#101114] border border-zinc-900 rounded-md max-w-lg">
          <button
            onClick={() => setMode("ai")}
            className={`flex items-center justify-center gap-1.5 py-1.5 text-xs rounded transition-all ${
              mode === "ai"
                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20 font-semibold"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            AI 创作 (一键脚本)
          </button>
          <button
            onClick={() => setMode("manual")}
            className={`flex items-center justify-center gap-1.5 py-1.5 text-xs rounded transition-all ${
              mode === "manual"
                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20 font-semibold"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Edit3 className="w-3.5 h-3.5" />
            自行创作 (分镜编辑)
          </button>
          <button
            onClick={() => setMode("batch")}
            className={`flex items-center justify-center gap-1.5 py-1.5 text-xs rounded transition-all ${
              mode === "batch"
                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20 font-semibold"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            批量生成 (多主题)
          </button>
        </div>
      </div>

      {/* 2. Content Input panel */}
      <div id="stage-storyboard" className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4 scroll-mt-24">
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
                    {copyDraftMode === "full" ? "先确认完整口播，再智能拆分" : "一段对应一个分镜旁白"}
                  </span>
                </div>
                <textarea
                  value={copyDraft}
                  onChange={(e) => setCopyDraft(e.target.value)}
                  placeholder={
                    copyDraftMode === "full"
                      ? "点击“生成口播稿草稿”后，AI 会在这里生成一整篇可编辑口播稿。你也可以直接粘贴自己的成稿。"
                      : "点击“生成分镜旁白草稿”后，AI 会在这里按段落生成旁白列表。你可以逐段修改，每段会进入一个分镜。"
                  }
                  className="w-full min-h-36 max-h-80 bg-[#101114] border border-zinc-900 rounded px-2.5 py-2 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 placeholder-zinc-650 resize-y leading-relaxed"
                />
              </div>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="font-medium text-zinc-400">分镜切片数量: {aiSceneCount} 个分镜</span>
                  <span className="text-[10px] text-zinc-500 font-mono">建议 5-10 个分镜</span>
                </div>
                <input
                  type="range"
                  min="3"
                  max="100"
                  step="1"
                  value={aiSceneCount}
                  onChange={(e) => setAiSceneCount(parseInt(e.target.value))}
                  className="w-full accent-amber-500 cursor-pointer h-1.5 bg-zinc-800 rounded"
                />
              </div>

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
                  预计口播 {estimatedCopySeconds} 秒 · 每分镜约 {averageCopyCharsPerStoryboard} 字
                </p>
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

            <div className="flex flex-col sm:flex-row justify-end gap-2 pt-2 border-t border-zinc-900">
              <button
                type="button"
                onClick={handleGenerateCopyDraft}
                disabled={copyDraftLoading || aiLoading}
                className="px-4 py-1.5 bg-zinc-800 text-zinc-300 hover:text-white disabled:bg-zinc-900 disabled:text-zinc-600 border border-zinc-750 hover:border-amber-500/40 text-xs font-semibold rounded shadow-md flex items-center justify-center gap-1.5 transition-colors"
              >
                {copyDraftLoading ? (
                  <>
                    <Loader className="w-3.5 h-3.5 animate-spin text-amber-500" />
                    AI 正在生成文案...
                  </>
                ) : (
                  <>
                    <Edit3 className="w-3.5 h-3.5 text-amber-500" />
                    {copyDraftMode === "full" ? "生成口播稿草稿" : "生成分镜旁白草稿"}
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={handleAIGenerateScript}
                disabled={aiLoading || copyDraftLoading}
                className="px-4 py-1.5 bg-amber-500 hover:bg-amber-400 disabled:bg-zinc-800 text-black disabled:text-zinc-500 font-semibold text-xs rounded shadow-md flex items-center justify-center gap-1.5 transition-colors"
              >
                {aiLoading ? (
                  <>
                    <Loader className="w-3.5 h-3.5 animate-spin" />
                    AI 正在构建智能分镜脚本...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5 text-black" />
                    基于确认文案生成 AI 分镜脚本
                  </>
                )}
              </button>
            </div>
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
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                输入多个主题 (每个主题将独立渲染一个短视频)
              </label>
              <textarea
                value={batchInput}
                onChange={(e) => {
                  setBatchInput(e.target.value);
                  const count = e.target.value.split("\n").filter((l) => l.trim() !== "").length;
                  setBatchCount(count);
                }}
                placeholder="一行一个主题进行配置..."
                className="w-full h-32 bg-[#17181c] border border-zinc-800 rounded p-2.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 font-mono placeholder-zinc-700"
              />
            </div>
            
            <div className="bg-amber-550/5 border border-amber-500/10 p-3 rounded text-xs text-zinc-400 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                系统检测到 <strong>{batchCount}</strong> 个合法主题，将创建 <strong>{batchCount}</strong> 个独立视频。
              </span>
              <span className="text-[10px] font-mono uppercase tracking-wider bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded">
                批量生成并发
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 3. TTS Voice Synthesis & BGM Mixing */}
      <div id="stage-production" className="grid grid-cols-1 md:grid-cols-2 gap-4 scroll-mt-24">
        {/* TTS Panel */}
        <div className="bg-[#101114] border border-zinc-900 p-4 rounded-lg space-y-4">
          <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
            <Mic2 className="w-4 h-4 text-amber-500" />
            配音合成 TTS 引擎
          </h3>
          <p className="text-[10px] text-amber-400/80">试听与“合成当前文案”仅供预览，不会复用到最终成片。</p>

          <div className="grid grid-cols-3 gap-1 p-0.5 bg-[#17181c] border border-zinc-850 rounded">
            {(["edge", "comfyui", "minimax"] as const).map((opt) => (
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
              </button>
            ))}
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
        <div className="bg-[#101114] border border-zinc-900 p-4 rounded-lg space-y-4">
          <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
            <Music className="w-4 h-4 text-amber-500" />
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

      {/* 4. Image style and motion composition */}
      <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <div className="flex items-center pb-2 border-b border-zinc-900">
          <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
            <FileVideo className="w-4 h-4 text-amber-500" />
            分镜画风及画面渲染模式
          </h3>
        </div>

        <div className="space-y-3">
          <div>
            <div className="flex items-center justify-between gap-3 mb-1">
              <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
                底模提示词前缀固定参数 / Prompt Prefix
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
                      高亮词（可单独配色）
                    </span>
                    <button
                      type="button"
                      onClick={handleExtractKeywords}
                      disabled={keywordLoading}
                      className="inline-flex items-center justify-center gap-1.5 rounded border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-[11px] text-amber-200 hover:bg-amber-500/20 disabled:opacity-50"
                    >
                      {keywordLoading ? <Loader className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
                      AI 自动抽词
                    </button>
                  </div>
                  <label className="block">
                    <span className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                      批量编辑（逗号分隔）
                    </span>
                    <textarea
                      value={(subtitleStyle.highlightWords || []).join("，")}
                      onChange={(e) => {
                        const words = parseHighlightWords(e.target.value);
                        applyHighlightKeywords(words);
                      }}
                      rows={2}
                      placeholder="例如：表达力，重点"
                      className="w-full resize-y min-h-16 max-h-32 bg-[#0c0d10] border border-zinc-900 rounded px-2.5 py-2 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                    />
                  </label>
                  {(subtitleStyle.highlightWords || []).length > 0 && (
                    <div className="space-y-1.5">
                      {(subtitleStyle.highlightWords || []).map((word) => (
                        <div
                          key={word}
                          className="flex items-center gap-2 rounded border border-zinc-800 bg-[#0c0d10] px-2 py-1.5"
                        >
                          <span
                            className="min-w-0 flex-1 truncate text-xs font-semibold"
                            style={{ color: subtitleStyle.keywordColors?.[word] || subtitleStyle.accentColor }}
                          >
                            {word}
                          </span>
                          <input
                            type="color"
                            value={subtitleStyle.keywordColors?.[word] || subtitleStyle.accentColor || "#FFD43B"}
                            onChange={(e) =>
                              updateSubtitleStyle({
                                keywordColors: {
                                  ...(subtitleStyle.keywordColors || {}),
                                  [word]: e.target.value,
                                },
                              })
                            }
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

      {/* 5. ComfyUI Media Workflows selections */}
      <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
            <Workflow className="w-4 h-4 text-amber-500" />
            后台渲染 Workflows 源工作流配置
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

      <section id="stage-review" className="bg-[#101114] border border-amber-500/20 rounded-lg p-4 space-y-3 scroll-mt-24" aria-labelledby="generation-review-title">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 id="generation-review-title" className="text-sm font-semibold text-zinc-200">生成前核对</h3>
            <p className="text-xs text-zinc-400 mt-1">确认任务数量和关键生产参数，提交后仍可在任务面板取消。</p>
          </div>
          <span className="text-[10px] font-mono text-amber-400 border border-amber-500/20 rounded px-2 py-1">
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
            ["生成策略", effectiveReuseSourceTaskId ? "优先复用配音与图片" : "完整生成"],
            ["预计旁白", `约 ${Math.ceil(reviewNarrationSeconds / 60)} 分钟`],
          ].map(([label, value]) => (
            <div key={label} className="bg-[#17181c] border border-zinc-900 rounded p-2 min-w-0">
              <dt className="text-zinc-500 mb-1">{label}</dt>
              <dd className="text-zinc-200 truncate" title={value}>{value}</dd>
            </div>
          ))}
        </dl>
        <label className="flex items-start gap-2 text-xs text-zinc-300 cursor-pointer">
          <input
            type="checkbox"
            checked={reviewConfirmed}
            onChange={(event) => setReviewConfirmed(event.target.checked)}
            className="mt-0.5 accent-amber-500"
          />
          <span>
            我已核对以上配置，确认
            {mode === "batch" ? `创建 ${reviewVideoCount} 个视频任务` : "进入剪辑工作台或直接生成成片"}。
          </span>
        </label>
      </section>

      {/* Primary Action Button */}
      <div className="flex flex-wrap justify-end gap-2 pt-2">
        {mode !== "batch" && onCreateProject && (
          <button
            type="button"
            onClick={() => void handleTriggerRender(true)}
            disabled={isSubmitting || !reviewConfirmed}
            className="px-4 py-2.5 border border-zinc-700 text-zinc-200 font-semibold text-xs rounded hover:border-zinc-500 hover:bg-zinc-900 disabled:border-zinc-800 disabled:text-zinc-600 disabled:cursor-not-allowed flex items-center gap-2 transition-colors"
          >
            <FileVideo className="w-4 h-4" />
            仅生成成片
          </button>
        )}
        <button
          type="button"
          onClick={() => void handleTriggerRender(false)}
          disabled={isSubmitting || !reviewConfirmed}
          className="px-6 py-2.5 bg-amber-500 text-black font-semibold text-xs rounded hover:bg-amber-400 disabled:bg-zinc-800 disabled:text-zinc-500 disabled:cursor-not-allowed shadow-xl shadow-amber-500/10 flex items-center gap-2 transition-transform active:scale-[0.99]"
        >
          {isSubmitting ? <Loader className="w-4 h-4 animate-spin" /> : mode === "batch" ? <Sparkles className="w-4 h-4 text-black" /> : <FolderOpen className="w-4 h-4 text-black" />}
          {isSubmitting ? "正在提交任务…" : mode === "batch" ? `提交 ${reviewVideoCount} 个视频任务` : "生成初稿并打开工作台"}
        </button>
      </div>
    </div>
  );
};
