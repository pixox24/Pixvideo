import React, { useEffect, useState } from "react";
import type { StageSubtitleModel } from "../lib/stageSubtitle";

const CUSTOM_STAGE_FONT = "PixelleStageSubtitleFont";

const colorWithOpacity = (color: string, opacity: number) => {
  const normalized = String(color || "").replace("#", "");
  if (!/^[0-9a-f]{6}$/iu.test(normalized)) return color;
  const red = parseInt(normalized.slice(0, 2), 16);
  const green = parseInt(normalized.slice(2, 4), 16);
  const blue = parseInt(normalized.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${Math.min(Math.max(opacity, 0), 100) / 100})`;
};

interface StageSubtitleOverlayProps {
  model: StageSubtitleModel;
  className?: string;
}

/**
 * CSS subtitle layer for the workbench stage.
 * Approximate preview only — final look is export-burned video.
 */
export const StageSubtitleOverlay: React.FC<StageSubtitleOverlayProps> = ({
  model,
  className = "",
}) => {
  const [fontFamily, setFontFamily] = useState<string | null>(null);
  const style = model.style;

  useEffect(() => {
    if (!style.fontPath || !document.fonts || typeof FontFace === "undefined") {
      setFontFamily(null);
      return;
    }
    let disposed = false;
    const font = new FontFace(
      CUSTOM_STAGE_FONT,
      `url("/api/resources/fonts/file?path=${encodeURIComponent(style.fontPath)}")`,
    );
    font
      .load()
      .then((loaded) => {
        if (disposed) return;
        document.fonts.add(loaded);
        setFontFamily(CUSTOM_STAGE_FONT);
      })
      .catch(() => {
        if (!disposed) setFontFamily(null);
      });
    return () => {
      disposed = true;
      try {
        document.fonts.delete(font);
      } catch {
        /* ignore */
      }
    };
  }, [style.fontPath]);

  if (!model.visible || model.lines.length === 0) return null;

  const boxEnabled = style.preset === "caption-box" || style.boxEnabled === true;
  const boxColor = style.boxColor || style.backColor || "#000000";
  const boxOpacity = style.boxOpacity ?? style.backgroundOpacity ?? 72;
  // Use layout-scaled pad/radius so preview proportions match full-res Pillow export
  // (previously used raw CSS px while fontSize was scaled → box looked fatter than export).
  const boxPadX = boxEnabled ? Math.max(1, model.layout.boxPadX || 0) : 0;
  const boxPadY = boxEnabled ? Math.max(1, model.layout.boxPadY || 0) : 0;
  const boxRadius = boxEnabled ? Math.max(0, model.layout.boxRadius || 0) : 0;
  const strokeWidth = boxEnabled ? 0 : model.layout.outlineWidth;
  const strokeColor = style.strokeColor || style.outlineColor || "#000000";
  const highlightStyle = style.highlightStyle || "accent";
  const highlightScale = Math.min(Math.max(style.highlightScale || 125, 100), 180) / 100;
  const activeFont = fontFamily || style.fontFamily || "system-ui, sans-serif";
  const textShadow =
    model.layout.shadow > 0
      ? `0 0 ${Math.max(2, model.layout.shadow * 2)}px ${strokeColor}, 0 0 ${Math.max(4, model.layout.shadow * 3)}px ${strokeColor}`
      : "none";
  const justify =
    model.layout.textAlign === "left"
      ? "flex-start"
      : model.layout.textAlign === "right"
        ? "flex-end"
        : "center";

  return (
    <div
      className={`pointer-events-none absolute inset-0 flex flex-col justify-end ${className}`.trim()}
      aria-hidden
      data-stage-subtitle="1"
      data-in-hold={model.inHold ? "1" : "0"}
    >
      <div
        className="flex w-full px-2"
        style={{
          justifyContent: justify,
          paddingBottom: Math.max(4, model.layout.marginBottom),
        }}
      >
        <div
          className="max-w-[92%] text-center leading-snug"
          style={{
            fontFamily: activeFont,
            fontSize: model.layout.fontSize,
            color: style.primaryColor || "#FFFFFF",
            textAlign: model.layout.textAlign,
            background: boxEnabled ? colorWithOpacity(boxColor, boxOpacity) : "transparent",
            borderRadius: boxEnabled ? boxRadius : 0,
            // Keep sub-pixel padding for correct scale match at small preview sizes
            padding: boxEnabled ? `${boxPadY}px ${boxPadX}px` : "0px",
            textShadow,
            WebkitTextStroke:
              strokeWidth > 0 ? `${strokeWidth}px ${strokeColor}` : undefined,
            paintOrder: strokeWidth > 0 ? "stroke fill" : undefined,
          }}
        >
          {model.fragmentsByLine.map((fragments, lineIndex) => (
            <div key={`line-${lineIndex}`} className="whitespace-pre-wrap">
              {fragments.map((fragment, fragmentIndex) => {
                if (!fragment.highlighted) {
                  return <span key={`f-${lineIndex}-${fragmentIndex}`}>{fragment.text}</span>;
                }
                const color = fragment.color || style.accentColor || "#FFD43B";
                if (highlightStyle === "badge") {
                  return (
                    <span
                      key={`f-${lineIndex}-${fragmentIndex}`}
                      className="mx-[0.05em] inline-block rounded px-[0.15em]"
                      style={{
                        backgroundColor: colorWithOpacity(color, 88),
                        color: "#111",
                        transform: `scale(${highlightScale})`,
                      }}
                    >
                      {fragment.text}
                    </span>
                  );
                }
                return (
                  <span
                    key={`f-${lineIndex}-${fragmentIndex}`}
                    style={{
                      color,
                      fontWeight: 700,
                      display: "inline-block",
                      transform: highlightStyle === "pop" ? `scale(${highlightScale})` : undefined,
                    }}
                  >
                    {fragment.text}
                  </span>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
