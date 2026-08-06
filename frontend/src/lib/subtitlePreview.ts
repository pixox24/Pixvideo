import { SubtitleStyle } from "../types";

export type PreviewAspect = "landscape" | "portrait";
export interface PreviewHighlightFragment {
  text: string;
  highlighted: boolean;
  color?: string;
}

export const PREVIEW_SAMPLE_TEXT = "有人说，AI会取代人类。取代不了深夜那碗面的温度。";

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(Math.max(value, minimum), maximum);

/** Punctuation used as split points (not shown on screen). */
const SPLIT_PUNCT = /[。！？!?\.…，,、；;：:]/u;

/** Strip punctuation used as sentence split points (not shown on screen). */
export const stripDisplayPunctuation = (text: string) =>
  text
    .replace(/^[,，、；;：:\s。！？!?\.…]+/u, "")
    .replace(/[。！？!?\.…,，、；;：:\s]+$/u, "")
    .trim();

export const wrapPreviewText = (text: string, maxCharsPerLine: number, maxLines: number) => {
  const characters = Array.from(text.replace(/\s+/g, " ").trim());
  const lineLength = clamp(maxCharsPerLine || 14, 4, 40);
  const lineCount = clamp(maxLines || 2, 1, 4);
  const maximumCharacters = lineLength * lineCount;
  const truncated = characters.length > maximumCharacters;
  const visible = characters.slice(0, maximumCharacters);
  const lines = Array.from({ length: Math.ceil(visible.length / lineLength) || 0 }, (_, index) =>
    visible.slice(index * lineLength, (index + 1) * lineLength).join("")
  );

  if (truncated && lines.length > 0) {
    const lastLine = lines.length - 1;
    lines[lastLine] = `${lines[lastLine].slice(0, Math.max(0, lineLength - 1))}…`;
  }

  return lines;
};

/**
 * Segment preview text using the same rules as backend SubtitleRenderer:
 * - sentence: split on 。！？ and ，、； etc., one line per cue, no punctuation, no mid-phrase hard cut
 * - line: split on newlines only
 * - phrase: fixed-capacity chunks
 */
export const segmentPreviewText = (
  text: string,
  mode: SubtitleStyle["segmentMode"],
  style: SubtitleStyle,
) => {
  const maxChars = clamp(style.maxCharsPerLine || 14, 4, 40);
  const maxLines = clamp(style.maxLines || 2, 1, 4);
  const capacity = maxChars * maxLines;

  if (mode === "line") {
    return (text || "")
      .split(/\r?\n/)
      .map((line) => stripDisplayPunctuation(line))
      .filter(Boolean);
  }

  if (mode === "sentence") {
    const cleaned = (text || "").replace(/\s+/g, " ").trim();
    if (!cleaned) return [];
    // Same as backend: extract non-punctuation runs only.
    return cleaned
      .split(SPLIT_PUNCT)
      .map((part) => stripDisplayPunctuation(part))
      .filter(Boolean);
  }

  // phrase: fixed capacity chunks (punctuation not used as split points)
  const cleaned = (text || "").replace(/\s+/g, " ").trim();
  if (!cleaned) return [];
  const chunks: string[] = [];
  for (let i = 0; i < cleaned.length; i += capacity) {
    const piece = stripDisplayPunctuation(cleaned.slice(i, i + capacity));
    if (piece) chunks.push(wrapPreviewText(piece, maxChars, maxLines).join("\n"));
  }
  return chunks;
};

export const splitPreviewHighlights = (
  text: string,
  highlightWords: string[] = [],
  keywordColors: Record<string, string> = {},
  accentColor = "#FFD43B",
): PreviewHighlightFragment[] => {
  const words = Array.from(
    new Set(
      [
        ...highlightWords,
        ...Object.keys(keywordColors || {}),
      ]
        .map((word) => word.trim())
        .filter(Boolean)
        .sort((left, right) => right.length - left.length),
    ),
  );
  if (!words.length) return text ? [{ text, highlighted: false }] : [];

  const escapePattern = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matcher = new RegExp(`(${words.map(escapePattern).join("|")})`, "giu");
  const highlightKeys = new Set(words.map((word) => word.toLocaleLowerCase()));
  const colorByKey = new Map<string, string>();
  for (const word of words) {
    const key = word.toLocaleLowerCase();
    const override =
      keywordColors[word] ||
      Object.entries(keywordColors || {}).find(([k]) => k.toLocaleLowerCase() === key)?.[1];
    colorByKey.set(key, override || accentColor);
  }

  return text
    .split(matcher)
    .filter(Boolean)
    .map((fragment) => {
      const key = fragment.toLocaleLowerCase();
      const highlighted = highlightKeys.has(key);
      return {
        text: fragment,
        highlighted,
        color: highlighted ? colorByKey.get(key) : undefined,
      };
    });
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
    // Soft blur-like glow for preview (CSS text-shadow blur, not hard offset ghost).
    shadow: clamp(style.shadow || 0, 0, 12) * scale * 1.2,
    marginBottom: clamp(style.marginV || 120, 0, 600) * (canvasHeight / sourceHeight),
  };
};

export const previewTextAlignment = (alignment: number) => {
  if ([1, 4, 7].includes(alignment)) return "left";
  if ([3, 6, 9].includes(alignment)) return "right";
  return "center";
};
