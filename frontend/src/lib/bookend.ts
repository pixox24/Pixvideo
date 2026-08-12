/**
 * Project-level intro/outro bookend packaging (preview + config).
 * Mirrors pixelle_video/utils/bookend.py defaults.
 */

export interface BookendConfig {
  enabled: boolean;
  introSeconds: number;
  outroSeconds: number;
  introFadeSeconds: number;
  outroFadeSeconds: number;
}

export const DEFAULT_BOOKEND: BookendConfig = {
  enabled: true,
  introSeconds: 1.2,
  outroSeconds: 2.0,
  introFadeSeconds: 0.6,
  outroFadeSeconds: 1.0,
};

const clamp = (value: number, min: number, max: number) =>
  Math.min(max, Math.max(min, value));

export function normalizeBookendConfig(
  config?: Record<string, unknown> | null,
): BookendConfig {
  const cfg = config || {};
  const nested =
    cfg.bookend && typeof cfg.bookend === "object"
      ? (cfg.bookend as Record<string, unknown>)
      : {};
  const source: Record<string, unknown> = { ...DEFAULT_BOOKEND, ...nested, ...cfg };

  const enabledRaw = source.bookendEnabled ?? source.bookend_enabled ?? source.enabled ?? true;
  const enabled =
    typeof enabledRaw === "string"
      ? !["0", "false", "no", "off", ""].includes(enabledRaw.trim().toLowerCase())
      : Boolean(enabledRaw);

  let introSeconds = clamp(
    Number(source.bookendIntroSeconds ?? source.intro_seconds ?? source.introSeconds ?? DEFAULT_BOOKEND.introSeconds) || 0,
    0,
    5,
  );
  let outroSeconds = clamp(
    Number(source.bookendOutroSeconds ?? source.outro_seconds ?? source.outroSeconds ?? DEFAULT_BOOKEND.outroSeconds) || 0,
    0,
    6,
  );
  let introFadeSeconds = clamp(
    Number(
      source.bookendIntroFadeSeconds
        ?? source.intro_fade_seconds
        ?? source.introFadeSeconds
        ?? DEFAULT_BOOKEND.introFadeSeconds,
    ) || 0,
    0,
    3,
  );
  let outroFadeSeconds = clamp(
    Number(
      source.bookendOutroFadeSeconds
        ?? source.outro_fade_seconds
        ?? source.outroFadeSeconds
        ?? DEFAULT_BOOKEND.outroFadeSeconds,
    ) || 0,
    0,
    4,
  );

  if (!enabled) {
    introSeconds = 0;
    outroSeconds = 0;
    introFadeSeconds = 0;
    outroFadeSeconds = 0;
  } else {
    introFadeSeconds = introSeconds > 0 ? Math.min(introFadeSeconds, introSeconds) : 0;
    outroFadeSeconds = outroSeconds > 0 ? Math.min(outroFadeSeconds, outroSeconds) : 0;
  }

  return {
    enabled: enabled && (introSeconds > 0 || outroSeconds > 0),
    introSeconds,
    outroSeconds,
    introFadeSeconds,
    outroFadeSeconds,
  };
}

export type BookendPhase = "intro" | "content" | "outro";

export interface BookendPlaybackState {
  phase: BookendPhase;
  /** Time within content timeline (0-based). Negative in intro; > contentDuration in outro. */
  contentTime: number;
  /** 0–1 opacity for stage picture fade approximation */
  pictureOpacity: number;
  /** 0–1 multiplier for BGM volume */
  bgmGain: number;
  /** Whether narration should play */
  narrationEnabled: boolean;
}

/**
 * Map absolute playback clock (includes intro/outro) to bookend visual/audio state.
 */
export function getBookendPlaybackState(
  playbackTime: number,
  contentDuration: number,
  bookend: BookendConfig,
): BookendPlaybackState {
  const intro = bookend.enabled ? bookend.introSeconds : 0;
  const outro = bookend.enabled ? bookend.outroSeconds : 0;
  const fadeIn = bookend.enabled ? bookend.introFadeSeconds : 0;
  const fadeOut = bookend.enabled ? bookend.outroFadeSeconds : 0;
  const total = Math.max(0, contentDuration) + intro + outro;
  const t = Math.max(0, Math.min(total, playbackTime));

  if (intro > 0 && t < intro) {
    const local = t;
    const opacity = fadeIn > 0 ? Math.min(1, local / fadeIn) : 1;
    const bgmGain = fadeIn > 0 ? Math.min(1, local / fadeIn) : 1;
    return {
      phase: "intro",
      contentTime: local - intro,
      pictureOpacity: opacity,
      bgmGain,
      narrationEnabled: false,
    };
  }

  const contentEnd = intro + Math.max(0, contentDuration);
  if (outro > 0 && t >= contentEnd) {
    const intoOutro = t - contentEnd;
    const remaining = Math.max(0, outro - intoOutro);
    // Fade only in the last fadeOut seconds of the full timeline
    let opacity = 1;
    let bgmGain = 1;
    if (fadeOut > 0) {
      const fadeStart = total - fadeOut;
      if (t >= fadeStart) {
        const u = (t - fadeStart) / fadeOut;
        opacity = Math.max(0, 1 - u);
        bgmGain = Math.max(0, 1 - u);
      }
    }
    return {
      phase: "outro",
      contentTime: Math.max(0, contentDuration) + intoOutro,
      pictureOpacity: opacity,
      bgmGain,
      narrationEnabled: false,
      // remaining unused but kept for future UI
    };
  }

  // Content region — optional mild edge fades already applied outside
  void fadeIn;
  return {
    phase: "content",
    contentTime: t - intro,
    pictureOpacity: 1,
    bgmGain: 1,
    narrationEnabled: true,
  };
}

export function getPlaybackTotalDuration(contentDuration: number, bookend: BookendConfig): number {
  if (!bookend.enabled) return Math.max(0, contentDuration);
  return Math.max(0, contentDuration) + bookend.introSeconds + bookend.outroSeconds;
}
