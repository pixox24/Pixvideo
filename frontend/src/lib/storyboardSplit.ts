/**
 * Semantic storyboard packing for Quick Create.
 *
 * Product rule: scene count is driven by copy meaning, never by equal character slicing.
 * See docs/plans/2026-08-10-semantic-storyboard-count-plan.md
 */

export type DraftSplitType = "paragraph" | "line" | "sentence";

export const STORYBOARD_SCENE_MIN = 1;
export const STORYBOARD_SCENE_MAX = 30;

/** Minimum length of each side when soft-splitting on pause punctuation. */
const SOFT_EXPAND_MIN_PART = 4;

export const clampSceneCount = (value: number, min = STORYBOARD_SCENE_MIN, max = STORYBOARD_SCENE_MAX) => {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, Math.round(value)));
};

/**
 * Split draft text into semantic units using the user-selected rule.
 * Mirrors the previous QuickCreate.splitDraftByCurrentRule behavior.
 */
export function splitDraftByRule(text: string, splitType: DraftSplitType): string[] {
  const trimmed = String(text || "").trim();
  if (!trimmed) return [];

  if (splitType === "paragraph") {
    return trimmed
      .split(/\n\s*\n/)
      .map((segment) => segment.trim())
      .filter(Boolean);
  }

  if (splitType === "sentence") {
    return (
      trimmed
        .match(/[^。！？.!?\n]+[。！？.!?]?/g)
        ?.map((segment) => segment.trim())
        .filter(Boolean) || []
    );
  }

  // line (default)
  return trimmed
    .split(/\r?\n/)
    .map((segment) => segment.trim())
    .filter(Boolean);
}

/**
 * Soft-expand units on pause punctuation (，；) only when both sides are substantial.
 * Never hard-cuts mid-phrase without punctuation.
 * Keeps the pause mark on the *left* segment so clause boundaries stay speakable.
 */
export function softExpandByPause(units: string[]): string[] {
  const expanded: string[] = [];
  for (const unit of units) {
    const trimmed = unit.trim();
    if (!trimmed) continue;
    // Keep delimiters: "A，B，C。" → ["A，", "B，", "C。"]
    const tokens = trimmed.split(/([，,；;]+)/).filter((part) => part.length > 0);
    const parts: string[] = [];
    let buffer = "";
    for (const token of tokens) {
      if (/^[，,；;]+$/.test(token)) {
        buffer = `${buffer}${token}`.trim();
        if (buffer) {
          parts.push(buffer);
          buffer = "";
        }
      } else {
        buffer = `${buffer}${token}`.trim();
      }
    }
    if (buffer) parts.push(buffer);

    if (parts.length > 1 && parts.every((part) => Array.from(part.replace(/[，,；;]/g, "")).length >= SOFT_EXPAND_MIN_PART)) {
      expanded.push(...parts);
    } else {
      expanded.push(trimmed);
    }
  }
  return expanded;
}

/**
 * Suggest storyboard count from draft semantics.
 */
export function suggestSceneCount(
  text: string,
  splitType: DraftSplitType,
  options?: { softExpand?: boolean; min?: number; max?: number },
): number {
  const softExpand = options?.softExpand !== false;
  let units = splitDraftByRule(text, splitType);
  if (softExpand) units = softExpandByPause(units);
  return clampSceneCount(units.length || 1, options?.min, options?.max);
}

/** Count CJK/meaningful characters for rhythm estimates (ignore pure whitespace). */
export function countCopyChars(text: string): number {
  return Array.from(String(text || "").replace(/\s+/g, "")).length;
}

/**
 * Rhythm-based scene count: total chars ÷ target chars per scene.
 * Default ~40 chars/scene ≈ 8–12s oral delivery at typical short-video pace.
 */
export function suggestRhythmSceneCount(
  textOrCharCount: string | number,
  options?: { charsPerScene?: number; min?: number; max?: number },
): number {
  const chars =
    typeof textOrCharCount === "number"
      ? Math.max(0, textOrCharCount)
      : countCopyChars(textOrCharCount);
  const per = Math.max(12, options?.charsPerScene ?? 40);
  return clampSceneCount(Math.max(1, Math.round(chars / per)), options?.min, options?.max);
}

export interface StoryboardRecommendation {
  semantic: number;
  rhythm: number;
  charCount: number;
  /** Preferred default adopt target: semantic first. */
  preferred: number;
}

/**
 * Step-2 analysis after pure copy is ready (no LLM required).
 */
export function analyzeStoryboardRecommendation(
  text: string,
  splitType: DraftSplitType,
  options?: { softExpand?: boolean; charsPerScene?: number; min?: number; max?: number },
): StoryboardRecommendation {
  const charCount = countCopyChars(text);
  const semantic = suggestSceneCount(text, splitType, options);
  const rhythm = suggestRhythmSceneCount(charCount, options);
  return {
    semantic,
    rhythm,
    charCount,
    preferred: semantic,
  };
}

/**
 * Pack semantic units into targetCount scenes.
 * - More units than target → merge adjacent units evenly.
 * - Fewer units than target → keep units as-is (do NOT character-slice).
 */
export function packSemanticUnits(units: string[], targetCount: number): string[] {
  const clean = units.map((unit) => unit.trim()).filter(Boolean);
  if (clean.length === 0) return [];

  const target = clampSceneCount(targetCount || clean.length);
  if (clean.length === target) return clean;

  if (clean.length > target) {
    return Array.from({ length: target }, (_, index) => {
      const start = Math.floor((index * clean.length) / target);
      const end = Math.floor(((index + 1) * clean.length) / target);
      return clean.slice(start, Math.max(end, start + 1)).join("").trim();
    }).filter(Boolean);
  }

  // clean.length < target: semantic priority — never invent mid-sentence cuts.
  return clean;
}

/**
 * Full pipeline: rule split → optional soft expand → pack to target.
 */
/**
 * Merge hard mid-word cuts like 「科学家发」+「现，光速」.
 */
export function healMidCuts(segments: string[]): string[] {
  const clean = segments.map((s) => s.trim()).filter(Boolean);
  if (clean.length < 2) return clean;
  const terminalOrPause = /[。！？.!?…，,；;]$/;
  const merged: string[] = [];
  let index = 0;
  while (index < clean.length) {
    let current = clean[index]!;
    while (index + 1 < clean.length) {
      const next = clean[index + 1]!;
      if (terminalOrPause.test(current)) break;
      const leftEnd = current[current.length - 1] || "";
      const rightStart = next[0] || "";
      const cjk =
        /[\u4e00-\u9fff]/.test(leftEnd) && /[\u4e00-\u9fff]/.test(rightStart);
      const alnum = /[a-zA-Z0-9]/.test(leftEnd) && /[a-zA-Z0-9]/.test(rightStart);
      if (!cjk && !alnum) break;
      // Long independent clauses without periods — leave alone
      if (Array.from(current).length >= 24 && Array.from(next).length >= 24 && /[这那他她你我神心]/.test(rightStart)) {
        break;
      }
      const should =
        Array.from(current).length <= 40
        || Array.from(next).length <= 12
        || /[现得着过了们到上下中里出来去]/.test(rightStart)
        || Array.from(current).length < 16;
      if (!should) break;
      current = `${current}${next}`;
      index += 1;
    }
    merged.push(current);
    index += 1;
  }
  return merged;
}

export function buildStoryboardNarrations(
  text: string,
  splitType: DraftSplitType,
  targetCount: number,
  options?: { softExpand?: boolean; heal?: boolean },
): string[] {
  const softExpand = options?.softExpand !== false;
  const heal = options?.heal !== false;
  let units = splitDraftByRule(text, splitType);
  if (softExpand) units = softExpandByPause(units);
  let packed = packSemanticUnits(units, targetCount);
  if (heal) packed = healMidCuts(packed);
  return packed;
}

/**
 * Detect likely mid-phrase hard cuts (heuristic for UI warnings / tests).
 * Returns true if any adjacent pair looks like a broken CJK phrase with no terminal punct.
 */
export function looksLikeMidSentenceCut(segments: string[]): boolean {
  if (segments.length < 2) return false;
  const terminal = /[。！？.!?]$/;
  for (let i = 0; i < segments.length - 1; i += 1) {
    const left = segments[i]?.trim() || "";
    const right = segments[i + 1]?.trim() || "";
    if (!left || !right) continue;
    if (terminal.test(left)) continue;
    // Very short trailing fragment on the right often means a hard cut ("己", "的自己")
    if (Array.from(right).length <= 3 && !/[，,；;]/.test(left)) return true;
    // Left ends mid-clause without pause mark and right continues same sentence style
    if (!/[，,；;。！？.!?]$/.test(left) && Array.from(left).length >= 2 && Array.from(right).length >= 2) {
      // Only flag when left is not a full clause ending with pause
      if (Array.from(left).length < 8 || Array.from(right).length < 8) {
        // weak signal; skip short noise
      }
    }
  }
  return false;
}
