/**
 * Semantic storyboard packing for Quick Create.
 *
 * Product rule: scene count is driven by copy meaning, never by equal character slicing.
 * See docs/plans/2026-08-10-semantic-storyboard-count-plan.md
 */

export type DraftSplitType = "auto" | "paragraph" | "line" | "sentence";
export type StoryboardDensity = "sparse" | "standard" | "dense";

export const STORYBOARD_SCENE_MIN = 1;
export const STORYBOARD_SCENE_MAX = 100;

/** Minimum length of each side when soft-splitting on pause punctuation. */
const SOFT_EXPAND_MIN_PART = 4;
export const AUTO_MAX_CHARS_PER_SEGMENT = 52;
export const AUTO_MIN_CHARS_PER_SEGMENT = 12;
const RHYTHM_TARGET_CHARS = 36;
const RHYTHM_MAX_CHARS = 42;

export const DENSITY_CHARS_PER_SCENE: Record<StoryboardDensity, number> = {
  sparse: 60,
  standard: 40,
  dense: 28,
};

export function charsPerSceneForDensity(density: StoryboardDensity = "standard"): number {
  return DENSITY_CHARS_PER_SCENE[density] || DENSITY_CHARS_PER_SCENE.standard;
}

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

  if (splitType === "auto") return autoSplitDraft(trimmed);

  if (splitType === "paragraph") {
    return trimmed
      .split(/\n\s*\n/)
      .map((segment) => segment.trim())
      .filter(Boolean);
  }

  if (splitType === "sentence") return splitSentenceUnits(trimmed);

  // Explicit line mode
  return trimmed
    .split(/\r?\n/)
    .map((segment) => segment.trim())
    .filter(Boolean);
}

const meaningfulLength = (value: string) => value.replace(/\s+/g, "").length;
const semanticBreak = /(?:与此同时|这意味着|从而|并且|同时|而且|但是|不过|因此|所以|如果|虽然|随后|后来|其实|最终|此时|此后|只要|因为|不仅|以及|还是|并|而|但|却|让|把|将|进入|开始|最后|其中)/gu;

function splitSentenceUnits(text: string): string[] {
  const units: string[] = [];
  let buffer = "";
  const source = String(text || "");
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index] || "";
    if (char === "\n") {
      if (buffer.trim()) units.push(buffer.trim());
      buffer = "";
      continue;
    }
    buffer += char;
    const next = source[index + 1] || "";
    if ("。！？!?…".includes(char)) {
      if ("。！？!?…".includes(next)) continue;
      units.push(buffer.trim());
      buffer = "";
    } else if (char === ".") {
      // Do not split decimal numbers, dates, domains, or version strings.
      if (/\d/.test(next) || next === "." || /[A-Za-z]/.test(next)) continue;
      units.push(buffer.trim());
      buffer = "";
    }
  }
  if (buffer.trim()) units.push(buffer.trim());
  return units.filter(Boolean);
}

function splitLongSentence(sentence: string): string[] {
  if (meaningfulLength(sentence) <= RHYTHM_MAX_CHARS) return [sentence.trim()];

  const tokens = sentence.split(/([，,；;：:]+)/).filter(Boolean);
  const parts: string[] = [];
  let buffer = "";
  for (const token of tokens) {
    buffer = `${buffer}${token}`.trim();
    if (/^[，,；;：:]+$/.test(token)) {
      parts.push(buffer);
      buffer = "";
    }
  }
  if (buffer) parts.push(buffer);

  if (parts.length <= 1) return splitByRhythm(sentence);

  const groups: string[] = [];
  buffer = "";
  for (const part of parts) {
    const candidate = `${buffer}${part}`.trim();
    if (buffer && meaningfulLength(candidate) > RHYTHM_MAX_CHARS) {
      groups.push(buffer);
      buffer = part;
    } else {
      buffer = candidate;
    }
  }
  if (buffer) groups.push(buffer);

  if (groups.length > 1 && meaningfulLength(groups.at(-1) || "") < AUTO_MIN_CHARS_PER_SEGMENT) {
    groups[groups.length - 2] = `${groups[groups.length - 2]}${groups[groups.length - 1]}`;
    groups.pop();
  }
  return groups.some((group) => meaningfulLength(group) > RHYTHM_MAX_CHARS)
    ? splitByRhythm(sentence)
    : (groups.length ? groups : [sentence.trim()]);
}

function splitByRhythm(text: string): string[] {
  const source = String(text || "").trim();
  if (meaningfulLength(source) <= RHYTHM_MAX_CHARS) return source ? [source] : [];

  const result: string[] = [];
  let cursor = 0;
  while (meaningfulLength(source.slice(cursor)) > RHYTHM_MAX_CHARS) {
    const limit = Math.min(source.length, cursor + RHYTHM_MAX_CHARS);
    const candidates: number[] = [];
    for (let index = cursor; index < limit; index += 1) {
      if (/[，,；;：:。！？!?…]/.test(source[index] || "") && source.length - index - 1 >= AUTO_MIN_CHARS_PER_SEGMENT) {
        candidates.push(index + 1);
      }
    }
    semanticBreak.lastIndex = cursor + AUTO_MIN_CHARS_PER_SEGMENT;
    let match: RegExpExecArray | null;
    while ((match = semanticBreak.exec(source))) {
      const position = match.index;
      if (position > limit) break;
      if (position >= limit || source.length - position < AUTO_MIN_CHARS_PER_SEGMENT) continue;
      const previous = source[position - 1] || "";
      const first = source[position] || "";
      if (/[A-Za-z0-9]/.test(previous) && /[A-Za-z0-9]/.test(first)) continue;
      candidates.push(position);
    }

    let cut = candidates.length
      ? candidates.reduce((best, position) =>
        Math.abs(position - cursor - RHYTHM_TARGET_CHARS) < Math.abs(best - cursor - RHYTHM_TARGET_CHARS)
          ? position
          : best,
      candidates[0]!)
      // ponytail: fixed-width CJK fallback; replace with a tokenizer only if cut quality is measured as a problem.
      : Math.min(cursor + RHYTHM_TARGET_CHARS, source.length - Math.max(AUTO_MIN_CHARS_PER_SEGMENT, source.length - cursor - RHYTHM_TARGET_CHARS));
    cut = Math.max(cursor + AUTO_MIN_CHARS_PER_SEGMENT, Math.min(cut, limit));
    if (cut > 0 && cut < source.length && /[A-Za-z0-9]/.test(source[cut - 1] || "") && /[A-Za-z0-9]/.test(source[cut] || "")) {
      for (let candidate = cut - 1; candidate >= cursor + AUTO_MIN_CHARS_PER_SEGMENT; candidate -= 1) {
        if (!(/[A-Za-z0-9]/.test(source[candidate - 1] || "") && /[A-Za-z0-9]/.test(source[candidate] || ""))) {
          cut = candidate;
          break;
        }
      }
    }
    if (cut <= cursor) cut = Math.min(limit, cursor + RHYTHM_TARGET_CHARS);
    result.push(source.slice(cursor, cut).trim());
    cursor = cut;
  }
  const tail = source.slice(cursor).trim();
  if (tail) result.push(tail);
  return result.length ? result : [source];
}

/** Split only at sentence or explicit pause boundaries; never character-slice. */
export function autoSplitDraft(text: string): string[] {
  const trimmed = String(text || "").trim();
  if (!trimmed) return [];
  const sentences = splitSentenceUnits(trimmed);
  const units: string[] = [];
  for (const sentence of sentences) {
    const clean = sentence.trim();
    if (clean) units.push(...splitLongSentence(clean));
  }
  return units.length ? units : [trimmed];
}

/** Keep custom targets soft without allowing a packed unit over the rhythm ceiling. */
export function rebalanceLongUnits(units: string[]): string[] {
  return units.flatMap((unit) => {
    const clean = unit.trim();
    return meaningfulLength(clean) > RHYTHM_MAX_CHARS ? splitLongSentence(clean) : (clean ? [clean] : []);
  });
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
  units: string[];
  longestChars: number;
  longestSeconds: number;
  warnings: string[];
  /** Preferred default adopt target: semantic first. */
  preferred: number;
  density: StoryboardDensity;
  recommendedSceneCount: number;
  actualSceneCount: number;
  targetSceneCount: number | null;
  estimatedDurationSeconds: number;
}

/**
 * Step-2 analysis after pure copy is ready (no LLM required).
 */
export function analyzeStoryboardRecommendation(
  text: string,
  splitType: DraftSplitType,
  options?: {
    softExpand?: boolean;
    charsPerScene?: number;
    density?: StoryboardDensity;
    targetSceneCount?: number | null;
    min?: number;
    max?: number;
  },
): StoryboardRecommendation {
  const charCount = countCopyChars(text);
  const semantic = suggestSceneCount(text, splitType, options);
  const density = options?.density || "standard";
  const rhythm = suggestRhythmSceneCount(charCount, {
    ...options,
    charsPerScene: options?.charsPerScene ?? charsPerSceneForDensity(density),
  });
  let units = splitDraftByRule(text, splitType);
  if (options?.softExpand !== false) units = softExpandByPause(units);
  units = rebalanceLongUnits(units);
  const longestChars = Math.max(0, ...units.map((unit) => meaningfulLength(unit)));
  const longestSeconds = (longestChars / 260) * 60;
  const warnings: string[] = [];
  if (longestChars > AUTO_MAX_CHARS_PER_SEGMENT) {
    warnings.push(`仍有 ${longestChars} 字的旁白无法在现有标点处安全拆分`);
  }
  if (longestSeconds > (AUTO_MAX_CHARS_PER_SEGMENT * 60) / 260) {
    warnings.push(`最长分镜预计 ${longestSeconds.toFixed(1)} 秒，建议启用视觉节拍或补充停顿标点`);
  }
  const targetSceneCount = options?.targetSceneCount == null
    ? null
    : clampSceneCount(options.targetSceneCount, options?.min, options?.max);
  const actualUnits = rebalanceLongUnits(
    targetSceneCount == null ? units : packSemanticUnits(units, targetSceneCount),
  );
  const actualSceneCount = actualUnits.length || 1;
  if (targetSceneCount != null && actualSceneCount !== targetSceneCount) {
    warnings.push(`目标 ${targetSceneCount} 镜，实际采用 ${actualSceneCount} 个自然语义镜头`);
  }
  return {
    semantic,
    rhythm,
    charCount,
    units,
    longestChars,
    longestSeconds,
    warnings,
    preferred: semantic,
    density,
    recommendedSceneCount: semantic,
    actualSceneCount,
    targetSceneCount,
    estimatedDurationSeconds: Math.max(1, Math.round((charCount / 260) * 60)),
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
  packed = rebalanceLongUnits(packed);
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
