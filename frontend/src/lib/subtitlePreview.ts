import { SubtitleStyle } from "../types";

export type PreviewAspect = "landscape" | "portrait";
export interface PreviewHighlightFragment {
  text: string;
  highlighted: boolean;
}

export const PREVIEW_SAMPLE_TEXT = "让每一帧，都更有表达力。";

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(Math.max(value, minimum), maximum);

export const wrapPreviewText = (text: string, maxCharsPerLine: number, maxLines: number) => {
  const characters = Array.from(text.replace(/\s+/g, " ").trim());
  const lineLength = clamp(maxCharsPerLine || 14, 4, 40);
  const lineCount = clamp(maxLines || 2, 1, 4);
  const maximumCharacters = lineLength * lineCount;
  const truncated = characters.length > maximumCharacters;
  const visible = characters.slice(0, maximumCharacters);
  const lines = Array.from({ length: Math.ceil(visible.length / lineLength) }, (_, index) =>
    visible.slice(index * lineLength, (index + 1) * lineLength).join("")
  );

  if (truncated && lines.length > 0) {
    const lastLine = lines.length - 1;
    lines[lastLine] = `${lines[lastLine].slice(0, Math.max(0, lineLength - 1))}…`;
  }

  return lines;
};

export const segmentPreviewText = (text: string, mode: SubtitleStyle["segmentMode"], style: SubtitleStyle) => {
  if (mode === "line") {
    return wrapPreviewText(text, style.maxCharsPerLine, style.maxLines);
  }

  if (mode === "sentence") {
    return text.match(/[^。！？.!?]+[。！？.!?]?/gu)?.map((segment) => segment.trim()).filter(Boolean) || [text];
  }

  return Array.from(text.matchAll(/.{1,6}/gu), (match) => match[0]);
};

export const splitPreviewHighlights = (
  text: string,
  highlightWords: string[] = [],
): PreviewHighlightFragment[] => {
  const words = Array.from(new Set(
    highlightWords
      .map((word) => word.trim())
      .filter(Boolean)
      .sort((left, right) => right.length - left.length),
  ));
  if (!words.length) return text ? [{ text, highlighted: false }] : [];

  const escapePattern = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matcher = new RegExp(`(${words.map(escapePattern).join("|")})`, "giu");
  const highlightKeys = new Set(words.map((word) => word.toLocaleLowerCase()));

  return text
    .split(matcher)
    .filter(Boolean)
    .map((fragment) => ({
      text: fragment,
      highlighted: highlightKeys.has(fragment.toLocaleLowerCase()),
    }));
};

export const scaleStyleForPreview = (style: SubtitleStyle, aspect: PreviewAspect) => {
  const canvasWidth = aspect === "landscape" ? 480 : 260;
  const canvasHeight = aspect === "landscape" ? 270 : 462;
  const sourceWidth = aspect === "landscape" ? 1920 : 1080;
  const sourceHeight = aspect === "landscape" ? 1080 : 1920;
  const scale = canvasWidth / sourceWidth;

  return {
    fontSize: Math.max(12, clamp(style.fontSize || 52, 12, 120) * scale),
    outlineWidth: style.outlineWidth > 0 ? Math.max(0.75, clamp(style.outlineWidth, 0, 12) * scale) : 0,
    shadow: clamp(style.shadow || 0, 0, 12) * scale,
    marginBottom: clamp(style.marginV || 120, 0, 600) * (canvasHeight / sourceHeight),
  };
};

export const previewTextAlignment = (alignment: number) => {
  if ([1, 4, 7].includes(alignment)) return "left";
  if ([3, 6, 9].includes(alignment)) return "right";
  return "center";
};
