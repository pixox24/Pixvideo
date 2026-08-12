/**
 * Video canvas (成片规格) vs image-gen whitelist mapping.
 * Mirrors pixelle_video/utils/video_canvas.py
 */

export type VideoCanvasTier = "recommended" | "fast" | "advanced" | "custom";

export interface VideoCanvasPreset {
  id: string;
  label: string;
  aspect: string;
  width: number;
  height: number;
  tier: VideoCanvasTier;
  hint: string;
}

export const DEFAULT_VIDEO_WIDTH = 1080;
export const DEFAULT_VIDEO_HEIGHT = 1920;
export const DEFAULT_VIDEO_FPS = 30;

export const VIDEO_CANVAS_PRESETS: VideoCanvasPreset[] = [
  {
    id: "1080x1920",
    label: "竖屏 1080p（推荐）",
    aspect: "9:16",
    width: 1080,
    height: 1920,
    tier: "recommended",
    hint: "默认成片规格，导出更稳",
  },
  {
    id: "720x1280",
    label: "竖屏 720p（更快）",
    aspect: "9:16",
    width: 720,
    height: 1280,
    tier: "fast",
    hint: "初稿/试片更快",
  },
  {
    id: "1440x2560",
    label: "竖屏 1440p（高级/慢）",
    aspect: "9:16",
    width: 1440,
    height: 2560,
    tier: "advanced",
    hint: "更清晰，导出明显更慢且更易失败",
  },
  {
    id: "1920x1080",
    label: "横屏 1080p",
    aspect: "16:9",
    width: 1920,
    height: 1080,
    tier: "recommended",
    hint: "横版成片",
  },
  {
    id: "1280x720",
    label: "横屏 720p（更快）",
    aspect: "16:9",
    width: 1280,
    height: 720,
    tier: "fast",
    hint: "横版试片",
  },
  {
    id: "2560x1440",
    label: "横屏 1440p（高级/慢）",
    aspect: "16:9",
    width: 2560,
    height: 1440,
    tier: "advanced",
    hint: "横版高清，导出更慢",
  },
  {
    id: "1080x1080",
    label: "方形 1080",
    aspect: "1:1",
    width: 1080,
    height: 1080,
    tier: "recommended",
    hint: "1:1 成片",
  },
  {
    id: "1024x1024",
    label: "方形 1024",
    aspect: "1:1",
    width: 1024,
    height: 1024,
    tier: "fast",
    hint: "接近生图常用方图",
  },
];

/** API-friendly image generation sizes. */
export const IMAGE_GEN_WHITELIST: Array<[number, number]> = [
  [1024, 1024],
  [1024, 1536],
  [1536, 1024],
  [1080, 1920],
  [1920, 1080],
  [720, 1280],
  [1280, 720],
];

export interface VideoCanvasSpec {
  width: number;
  height: number;
  fps: number;
  presetId: string;
  tier: VideoCanvasTier;
  isAdvanced: boolean;
}

export function normalizeVideoCanvas(config?: Record<string, unknown> | null): VideoCanvasSpec {
  const cfg = config || {};
  let width = Math.max(1, Number(cfg.mediaWidth ?? cfg.media_width ?? DEFAULT_VIDEO_WIDTH) || DEFAULT_VIDEO_WIDTH);
  let height = Math.max(1, Number(cfg.mediaHeight ?? cfg.media_height ?? DEFAULT_VIDEO_HEIGHT) || DEFAULT_VIDEO_HEIGHT);
  let fps = Math.max(12, Math.min(60, Number(cfg.videoFps ?? cfg.video_fps ?? DEFAULT_VIDEO_FPS) || DEFAULT_VIDEO_FPS));
  width = Math.max(480, Math.min(3840, Math.round(width)));
  height = Math.max(480, Math.min(3840, Math.round(height)));
  width -= width % 2;
  height -= height % 2;

  const preset = VIDEO_CANVAS_PRESETS.find((p) => p.width === width && p.height === height);
  const tier: VideoCanvasTier = preset?.tier || "custom";
  return {
    width,
    height,
    fps,
    presetId: `${width}x${height}`,
    tier,
    isAdvanced: tier === "advanced",
  };
}

export function mapImageGenSize(videoWidth: number, videoHeight: number): [number, number] {
  const vw = Math.max(1, Math.round(videoWidth || DEFAULT_VIDEO_WIDTH));
  const vh = Math.max(1, Math.round(videoHeight || DEFAULT_VIDEO_HEIGHT));
  const targetAspect = vw / vh;
  const targetPixels = vw * vh;
  const portrait = vh >= vw;

  for (const [w, h] of IMAGE_GEN_WHITELIST) {
    if (w === vw && h === vh) return [w, h];
  }

  const oriented = IMAGE_GEN_WHITELIST.filter(([w, h]) => (h >= w) === portrait);
  const pool = oriented.length ? oriented : IMAGE_GEN_WHITELIST;

  let best = pool[0]!;
  let bestScore = Number.POSITIVE_INFINITY;
  for (const size of pool) {
    const [w, h] = size;
    const aspectDelta = Math.abs(w / h - targetAspect);
    const pixelDelta = Math.abs(w * h - targetPixels) / Math.max(targetPixels, 1);
    const undersizePenalty = w * h >= targetPixels * 0.45 ? 0 : 1;
    const score = aspectDelta * 10 + undersizePenalty + pixelDelta;
    if (score < bestScore) {
      bestScore = score;
      best = size;
    }
  }
  return [best[0], best[1]];
}

export function imageGenSizeFromConfig(config?: Record<string, unknown> | null): [number, number] {
  const canvas = normalizeVideoCanvas(config);
  return mapImageGenSize(canvas.width, canvas.height);
}
