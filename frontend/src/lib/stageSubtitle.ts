/**
 * Stage (workbench center) subtitle preview model.
 *
 * Product decisions (BAAA):
 * 1B Hold: keep the last cue visible after narration ends.
 * 2A No audio duration: do not time-sync (hide timed preview).
 * 3A Style comes from project config only (no workbench style editor in P0).
 * 4A enableSubtitles off → no preview.
 */

import { SubtitleStyle } from "../types";
import {
  previewTextAlignment,
  segmentPreviewText,
  splitPreviewHighlights,
  wrapPreviewText,
  type PreviewHighlightFragment,
} from "./subtitlePreview";

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(Math.max(value, minimum), maximum);

export const STAGE_SUBTITLE_STYLE_DEFAULTS: SubtitleStyle = {
  mode: "ass",
  preset: "caption-box",
  fontFamily: "",
  fontPath: "",
  fontSize: 80,
  primaryColor: "#FFFFFF",
  accentColor: "#FFD43B",
  outlineColor: "#000000",
  backColor: "#000000",
  outlineWidth: 10,
  shadow: 0,
  marginV: 200,
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
  boxEnabled: true,
  boxColor: "#000000",
  boxOpacity: 72,
  boxPadding: 10,
  boxRadius: 12,
  strokeWidth: 0,
  strokeColor: "#000000",
};

export interface StageSubtitleCue {
  text: string;
  start: number;
  end: number;
}

export interface StageSubtitleLayout {
  fontSize: number;
  outlineWidth: number;
  shadow: number;
  marginBottom: number;
  textAlign: "left" | "center" | "right";
  /** Display-space box padding (export boxPadding scaled by canvas width ratio). */
  boxPadX: number;
  boxPadY: number;
  boxRadius: number;
  /** contentWidth / mediaWidth — used to keep preview proportions = export. */
  scale: number;
}

export interface StageSubtitleModel {
  visible: boolean;
  /** Why hidden / mode tag for UI. */
  reason:
    | "ok"
    | "disabled"
    | "empty"
    | "no_audio_duration"
    | "no_cues";
  activeText: string;
  lines: string[];
  fragmentsByLine: PreviewHighlightFragment[][];
  layout: StageSubtitleLayout;
  style: SubtitleStyle;
  cues: StageSubtitleCue[];
  activeCueIndex: number;
  audioDurationSeconds: number;
  /** True when localTime is past narration (hold region) but last cue kept (1B). */
  inHold: boolean;
}

export function normalizeStageSubtitleStyle(value?: Partial<SubtitleStyle> | null): SubtitleStyle {
  const base = { ...STAGE_SUBTITLE_STYLE_DEFAULTS, ...(value || {}) };
  return {
    ...base,
    fontSize: clamp(Number(base.fontSize) || STAGE_SUBTITLE_STYLE_DEFAULTS.fontSize, 12, 120),
    outlineWidth: clamp(Number(base.outlineWidth) || 0, 0, 24),
    shadow: clamp(Number(base.shadow) || 0, 0, 12),
    marginV: clamp(Number(base.marginV) || 120, 0, 800),
    alignment: clamp(Number(base.alignment) || 2, 1, 9),
    maxCharsPerLine: clamp(Number(base.maxCharsPerLine) || 14, 4, 40),
    maxLines: clamp(Number(base.maxLines) || 2, 1, 4),
    highlightWords: Array.isArray(base.highlightWords) ? base.highlightWords : [],
    keywordColors: base.keywordColors && typeof base.keywordColors === "object" ? base.keywordColors : {},
    highlightScale: clamp(Number(base.highlightScale) || 125, 100, 180),
    backgroundOpacity: clamp(Number(base.backgroundOpacity ?? base.boxOpacity ?? 72), 0, 100),
    boxOpacity: clamp(Number(base.boxOpacity ?? base.backgroundOpacity ?? 72), 0, 100),
    boxPadding: clamp(Number(base.boxPadding ?? base.outlineWidth ?? 10), 0, 48),
    boxRadius: clamp(Number(base.boxRadius ?? 12), 0, 48),
  };
}

export function resolveExportCanvasSize(config?: Record<string, unknown> | null): {
  width: number;
  height: number;
} {
  const cfg = config || {};
  const width = Number(
    cfg.mediaWidth
    ?? cfg.media_width
    ?? cfg.imageWidth
    ?? cfg.image_width
    ?? (cfg.image as { width?: number } | undefined)?.width
    ?? 1080,
  );
  const height = Number(
    cfg.mediaHeight
    ?? cfg.media_height
    ?? cfg.imageHeight
    ?? cfg.image_height
    ?? (cfg.image as { height?: number } | undefined)?.height
    ?? 1920,
  );
  return {
    width: width > 0 ? width : 1080,
    height: height > 0 ? height : 1920,
  };
}

/**
 * Scale export-canvas style metrics into the on-screen content box.
 */
export function scaleStyleForStage(
  style: SubtitleStyle,
  contentWidth: number,
  contentHeight: number,
  mediaWidth: number,
  mediaHeight: number,
): StageSubtitleLayout {
  const mw = mediaWidth > 0 ? mediaWidth : 1080;
  const mh = mediaHeight > 0 ? mediaHeight : 1920;
  const cw = contentWidth > 0 ? contentWidth : mw;
  const ch = contentHeight > 0 ? contentHeight : mh;
  const scale = cw / mw;
  const boxEnabled = style.boxEnabled === true || style.preset === "caption-box";
  const outlineSource = boxEnabled
    ? 0
    : (style.strokeWidth ?? style.outlineWidth ?? 0);

  // Mirror pillow_caption_renderer / StageSubtitleOverlay product formula, then
  // scale into display pixels so pad/font ratio matches full-res export.
  const padRaw = Math.max(
    boxEnabled ? 1 : 0,
    Number(style.boxPadding ?? (boxEnabled ? style.outlineWidth || 10 : 0)) || 0,
  );
  const padXExport = boxEnabled ? Math.max(6, Math.round(padRaw * 0.9)) : 0;
  const padYExport = boxEnabled ? Math.max(4, Math.round(padRaw * 0.55)) : 0;
  const radiusExport = boxEnabled ? Math.max(0, Number(style.boxRadius ?? 12) || 0) : 0;

  return {
    fontSize: Math.max(10, clamp(style.fontSize || 52, 12, 120) * scale),
    outlineWidth: outlineSource > 0 ? Math.max(0.5, clamp(outlineSource, 0, 12) * scale) : 0,
    shadow: clamp(style.shadow || 0, 0, 12) * scale * 1.2,
    marginBottom: clamp(style.marginV || 120, 0, 800) * (ch / mh),
    textAlign: previewTextAlignment(style.alignment),
    boxPadX: padXExport * scale,
    boxPadY: padYExport * scale,
    boxRadius: radiusExport * scale,
    scale,
  };
}

/** Weight by character count so longer cues get more time. */
export function buildWeightedCues(segments: string[], audioDurationSeconds: number): StageSubtitleCue[] {
  const clean = segments.map((text) => String(text || "").trim()).filter(Boolean);
  if (clean.length === 0 || audioDurationSeconds <= 0) return [];

  const weights = clean.map((text) => Math.max(1, Array.from(text.replace(/\s+/g, "")).length));
  const totalWeight = weights.reduce((sum, w) => sum + w, 0) || clean.length;
  let cursor = 0;
  return clean.map((text, index) => {
    const start = cursor;
    const share = audioDurationSeconds * (weights[index]! / totalWeight);
    const end = index === clean.length - 1 ? audioDurationSeconds : cursor + share;
    cursor = end;
    return { text, start, end };
  });
}

export function pickActiveCueIndex(
  cues: StageSubtitleCue[],
  localTime: number,
  audioDurationSeconds: number,
  options?: { keepLastDuringHold?: boolean },
): number {
  if (cues.length === 0) return -1;
  const keepHold = options?.keepLastDuringHold !== false;
  const t = Number.isFinite(localTime) ? localTime : 0;

  // 1B: after narration (hold), keep last cue.
  if (keepHold && t >= audioDurationSeconds - 1e-6) {
    return cues.length - 1;
  }

  for (let i = 0; i < cues.length; i += 1) {
    const cue = cues[i]!;
    if (t >= cue.start && t < cue.end) return i;
  }
  // Boundary: exactly at last cue end while still in audio region.
  if (t >= 0 && t < audioDurationSeconds) {
    return cues.length - 1;
  }
  return -1;
}

export interface BuildStageSubtitleModelInput {
  enableSubtitles: boolean;
  narration: string;
  localTime: number;
  /** Narration-only duration (durationSeconds - hold). Decision 2A: <=0 → hide. */
  audioDurationSeconds: number;
  style?: Partial<SubtitleStyle> | null;
  contentWidth: number;
  contentHeight: number;
  mediaWidth: number;
  mediaHeight: number;
}

export function buildStageSubtitleModel(input: BuildStageSubtitleModelInput): StageSubtitleModel {
  const style = normalizeStageSubtitleStyle(input.style);
  const layout = scaleStyleForStage(
    style,
    input.contentWidth,
    input.contentHeight,
    input.mediaWidth,
    input.mediaHeight,
  );

  const empty = (reason: StageSubtitleModel["reason"]): StageSubtitleModel => ({
    visible: false,
    reason,
    activeText: "",
    lines: [],
    fragmentsByLine: [],
    layout,
    style,
    cues: [],
    activeCueIndex: -1,
    audioDurationSeconds: Math.max(0, input.audioDurationSeconds || 0),
    inHold: false,
  });

  if (!input.enableSubtitles) return empty("disabled");

  const narration = String(input.narration || "").trim();
  if (!narration) return empty("empty");

  const audioDurationSeconds = Number(input.audioDurationSeconds);
  // 2A: unknown / zero narration duration → no timed preview.
  if (!Number.isFinite(audioDurationSeconds) || audioDurationSeconds <= 0) {
    return empty("no_audio_duration");
  }

  const segments = segmentPreviewText(narration, style.segmentMode, style);
  const cues = buildWeightedCues(segments, audioDurationSeconds);
  if (cues.length === 0) return empty("no_cues");

  const activeCueIndex = pickActiveCueIndex(cues, input.localTime, audioDurationSeconds, {
    keepLastDuringHold: true,
  });
  if (activeCueIndex < 0) return empty("no_cues");

  const activeText = cues[activeCueIndex]!.text;
  const lines = activeText.includes("\n")
    ? activeText.split("\n").map((line) => line.trim()).filter(Boolean)
    : wrapPreviewText(activeText, style.maxCharsPerLine, style.maxLines);

  const fragmentsByLine = lines.map((line) =>
    splitPreviewHighlights(
      line,
      style.highlightWords,
      style.keywordColors,
      style.accentColor,
    ),
  );

  const inHold = input.localTime >= audioDurationSeconds - 1e-6;

  return {
    visible: true,
    reason: "ok",
    activeText,
    lines,
    fragmentsByLine,
    layout,
    style,
    cues,
    activeCueIndex,
    audioDurationSeconds,
    inHold,
  };
}
