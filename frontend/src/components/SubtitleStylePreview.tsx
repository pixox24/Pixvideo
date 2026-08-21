import React, { useEffect, useMemo, useState } from "react";
import { SubtitleStyle } from "../types";
import {
  PREVIEW_SAMPLE_TEXT,
  PreviewAspect,
  previewTextAlignment,
  scaleStyleForPreview,
  segmentPreviewText,
  splitPreviewHighlights,
  wrapPreviewText,
} from "../lib/subtitlePreview";

type PreviewScene = "bright" | "dark" | "portrait" | "complex";

interface SubtitleStylePreviewProps {
  style: SubtitleStyle;
}

const SCENES: Array<{ id: PreviewScene; label: string; background: string }> = [
  { id: "bright", label: "明亮", background: "linear-gradient(135deg, #fde68a 0%, #fb7185 48%, #7dd3fc 100%)" },
  { id: "dark", label: "暗色", background: "radial-gradient(circle at 70% 18%, #475569 0%, #111827 38%, #030712 100%)" },
  { id: "portrait", label: "人像", background: "radial-gradient(ellipse at 52% 35%, #f1c6a5 0 18%, transparent 18.5%), linear-gradient(130deg, #365314 0%, #a3e635 45%, #fef3c7 100%)" },
  { id: "complex", label: "复杂", background: "linear-gradient(120deg, #0f172a 0 21%, #0ea5e9 21% 38%, #f97316 38% 56%, #4338ca 56% 73%, #eab308 73% 100%)" },
];

const colorWithOpacity = (color: string, opacity: number) => {
  const normalized = color.replace("#", "");
  if (!/^[0-9a-f]{6}$/iu.test(normalized)) return color;
  const red = parseInt(normalized.slice(0, 2), 16);
  const green = parseInt(normalized.slice(2, 4), 16);
  const blue = parseInt(normalized.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${Math.min(Math.max(opacity, 0), 100) / 100})`;
};

const CUSTOM_PREVIEW_FONT_FAMILY = "PixelleSubtitlePreviewFont";

export const SubtitleStylePreview: React.FC<SubtitleStylePreviewProps> = ({ style }) => {
  const [scene, setScene] = useState<PreviewScene>("dark");
  const [aspect, setAspect] = useState<PreviewAspect>("landscape");
  const [isPlaying, setIsPlaying] = useState(false);
  const [segmentIndex, setSegmentIndex] = useState(0);
  const [fontAvailable, setFontAvailable] = useState(true);
  const [previewFontFamily, setPreviewFontFamily] = useState<string | null>(null);
  const scaledStyle = useMemo(() => scaleStyleForPreview(style, aspect), [aspect, style]);
  const segments = useMemo(() => segmentPreviewText(PREVIEW_SAMPLE_TEXT, style.segmentMode, style), [style]);
  const text = isPlaying ? segments[segmentIndex] || PREVIEW_SAMPLE_TEXT : PREVIEW_SAMPLE_TEXT;
  const lines = useMemo(() => wrapPreviewText(text, style.maxCharsPerLine, style.maxLines), [style.maxCharsPerLine, style.maxLines, text]);
  const activeScene = SCENES.find((item) => item.id === scene) || SCENES[0];

  useEffect(() => {
    if (!style.fontPath || !document.fonts || typeof FontFace === "undefined") {
      setFontAvailable(true);
      setPreviewFontFamily(null);
      return;
    }

    let disposed = false;
    const font = new FontFace(
      CUSTOM_PREVIEW_FONT_FAMILY,
      `url("/api/resources/fonts/file?path=${encodeURIComponent(style.fontPath)}")`,
    );
    setFontAvailable(false);
    setPreviewFontFamily(null);

    font.load()
      .then((loadedFont) => {
        if (disposed) return;
        document.fonts.add(loadedFont);
        setPreviewFontFamily(CUSTOM_PREVIEW_FONT_FAMILY);
        setFontAvailable(true);
      })
      .catch(() => {
        if (!disposed) setFontAvailable(false);
      });

    return () => {
      disposed = true;
      document.fonts.delete(font);
    };
  }, [style.fontPath]);

  useEffect(() => {
    if (!isPlaying) return;
    const timeout = window.setTimeout(() => {
      if (segmentIndex + 1 < segments.length) setSegmentIndex((current) => current + 1);
      else setIsPlaying(false);
    }, Math.max(500, Math.floor(2500 / Math.max(segments.length, 1))));
    return () => window.clearTimeout(timeout);
  }, [isPlaying, segmentIndex, segments.length]);

  const replay = () => {
    setSegmentIndex(0);
    setIsPlaying(true);
  };
  const boxEnabled = style.preset === "caption-box" || style.boxEnabled === true;
  const boxColor = style.boxColor || style.backColor || "#000000";
  const boxOpacity = style.boxOpacity ?? style.backgroundOpacity ?? 72;
  // Scaled pads (export-space formula × canvas scale) — matches Pillow burn-in proportions.
  const boxPadX = boxEnabled ? Math.max(1, scaledStyle.boxPadX ?? 0) : 0;
  const boxPadY = boxEnabled ? Math.max(1, scaledStyle.boxPadY ?? 0) : 0;
  const boxRadius = boxEnabled ? Math.max(0, scaledStyle.boxRadius ?? 0) : 0;
  const strokeWidth = boxEnabled ? 0 : scaledStyle.outlineWidth;
  const strokeColor = style.strokeColor || style.outlineColor;
  const subtitleBackground = boxEnabled ? colorWithOpacity(boxColor, boxOpacity) : "transparent";
  // Soft glow (blur) instead of hard offset double-shadow.
  const textShadow =
    scaledStyle.shadow > 0
      ? `0 0 ${Math.max(2, scaledStyle.shadow * 2)}px ${strokeColor}, 0 0 ${Math.max(4, scaledStyle.shadow * 3)}px ${strokeColor}`
      : "none";
  const highlightStyle = style.highlightStyle || "accent";
  const highlightScale = Math.min(Math.max(style.highlightScale || 125, 100), 180) / 100;
  const highlightAnimated = isPlaying && style.animation === "word-pop";
  const activeFontFamily = previewFontFamily || style.fontFamily || "system-ui, sans-serif";

  return (
    <section className="ui-panel space-y-2.5" aria-label="字幕样式预览">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-xs font-semibold text-zinc-200">样式预览</p>
          <p className="text-caption">
            {boxEnabled
              ? "底框预览与成片对齐（ASS 为直角；圆角仅动态字幕）"
              : "样式预览；描边/颜色与成片一致"}
          </p>
        </div>
        <button type="button" onClick={replay} className="ui-btn ui-btn-secondary ui-btn-sm">
          {isPlaying ? "播放中" : "播放效果"}
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5" aria-label="预览场景">
        {SCENES.map((item) => (
          <button key={item.id} type="button" aria-pressed={scene === item.id} onClick={() => setScene(item.id)} className={`rounded-[var(--radius-md)] px-2 py-1 text-caption transition-colors ${scene === item.id ? "bg-zinc-100 text-zinc-900" : "bg-[var(--color-surface-3)] text-zinc-400 hover:text-zinc-200"}`}>
            {item.label}
          </button>
        ))}
        <span className="mx-0.5 h-5 w-px bg-[var(--color-border-subtle)]" />
        {(["landscape", "portrait"] as PreviewAspect[]).map((item) => (
          <button key={item} type="button" aria-pressed={aspect === item} onClick={() => setAspect(item)} className={`rounded-[var(--radius-md)] px-2 py-1 text-caption transition-colors ${aspect === item ? "bg-amber-500/20 text-amber-200" : "bg-[var(--color-surface-3)] text-zinc-400 hover:text-zinc-200"}`}>
            {item === "landscape" ? "16:9" : "9:16"}
          </button>
        ))}
      </div>

      <div className={`mx-auto overflow-hidden rounded border border-white/10 ${aspect === "landscape" ? "aspect-video w-full" : "aspect-[9/16] w-36"}`} style={{ background: activeScene.background }}>
        <div className="relative h-full w-full bg-gradient-to-t from-black/60 via-transparent to-black/10">
          <div className="absolute inset-x-[8%]" style={{ bottom: `${scaledStyle.marginBottom}px`, textAlign: previewTextAlignment(style.alignment) }}>
            <div
              className="inline-block max-w-full"
              style={{
                backgroundColor: subtitleBackground,
                borderRadius: boxEnabled ? boxRadius : 0,
                padding: `${boxPadY}px ${boxPadX}px`,
              }}
            >
              {lines.map((line, index) => (
                <p key={`${line}-${index}`} className={isPlaying && style.animation === "pop" ? "animate-[bounce_0.55s_ease-out]" : isPlaying && style.animation === "fade" ? "animate-[pulse_0.7s_ease-out]" : undefined} style={{ color: style.primaryColor, fontFamily: activeFontFamily, fontSize: `${scaledStyle.fontSize}px`, fontWeight: style.preset === "short-video-bold" ? 800 : 600, lineHeight: 1.35, WebkitTextStroke: strokeWidth > 0 ? `${strokeWidth}px ${strokeColor}` : "0", textShadow }}>
                  {splitPreviewHighlights(line, style.highlightWords, style.keywordColors, style.accentColor).map((fragment, fragmentIndex) => fragment.highlighted ? (
                    <span key={`${fragment.text}-${fragmentIndex}`} className={highlightAnimated ? "inline-block animate-[bounce_0.55s_ease-out]" : "inline-block"} style={{ color: highlightStyle === "badge" ? "#17110a" : (fragment.color || style.accentColor), backgroundColor: highlightStyle === "badge" ? (fragment.color || style.accentColor) : "transparent", borderRadius: highlightStyle === "badge" ? "0.16em" : undefined, padding: highlightStyle === "badge" ? "0.02em 0.16em" : undefined, fontWeight: highlightStyle === "pop" ? 900 : undefined, transform: highlightAnimated ? `scale(${highlightScale})` : undefined, WebkitTextStroke: highlightStyle === "badge" ? "0" : undefined, textShadow: highlightStyle === "badge" ? "none" : undefined }}>
                      {fragment.text}
                    </span>
                  ) : fragment.text)}
                </p>
              ))}
            </div>
          </div>
        </div>
      </div>

      {!fontAvailable && <p className="text-caption text-amber-300">无法加载所选字体，预览使用回退字体。</p>}
    </section>
  );
};
