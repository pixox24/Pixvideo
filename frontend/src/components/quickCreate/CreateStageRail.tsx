import React from "react";
import type { SubtitleStyle } from "../../types";

export type StageRailScene = {
  id: number;
  ttsText: string;
};

export type CreateStageRailProps = {
  aspectWidth: number;
  aspectHeight: number;
  canvasLabel: string;
  testImageUrl: string | null;
  subtitleStyle: SubtitleStyle;
  scenes: StageRailScene[];
};

const SAMPLE_FALLBACK = "字幕样式预览";

export const CreateStageRail: React.FC<CreateStageRailProps> = ({
  aspectWidth,
  aspectHeight,
  canvasLabel,
  testImageUrl,
  subtitleStyle,
  scenes,
}) => {
  const highlightWords = subtitleStyle.highlightWords || [];
  const sampleParts = highlightWords.length > 0 ? highlightWords.slice(0, 4) : [SAMPLE_FALLBACK];

  return (
    <aside
      id="create-stage-rail"
      className="hidden xl:block sticky top-24 w-80 shrink-0"
      aria-label="创作预览舞台"
    >
      <div
        className="ui-stage relative w-full overflow-hidden"
        style={{ aspectRatio: `${Math.max(1, aspectWidth)} / ${Math.max(1, aspectHeight)}` }}
      >
        {testImageUrl ? (
          <img src={testImageUrl} alt="" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-1 bg-[var(--color-surface-3)] px-3 text-center">
            <span className="text-caption text-zinc-500">{canvasLabel}</span>
            <span className="text-xs text-zinc-600">
              {aspectWidth}×{aspectHeight}
            </span>
          </div>
        )}
        <div className="pointer-events-none absolute inset-x-2 bottom-2 rounded-md bg-black/45 px-2 py-1.5 text-center">
          <p className="text-xs font-medium leading-relaxed" style={{ color: subtitleStyle.primaryColor }}>
            {sampleParts.map((word, index) => (
              <span
                key={`${word}-${index}`}
                className="mx-0.5"
                style={{
                  color: highlightWords.length
                    ? subtitleStyle.keywordColors?.[word] || subtitleStyle.accentColor || subtitleStyle.primaryColor
                    : subtitleStyle.primaryColor,
                }}
              >
                {word}
              </span>
            ))}
          </p>
        </div>
      </div>
      <p className="mt-2 text-caption text-zinc-500">{canvasLabel}</p>
      <div className="mt-3 space-y-1.5">
        {scenes.length === 0 ? (
          <p className="ui-panel text-caption text-zinc-500">生成口播后，分镜会出现在这里</p>
        ) : (
          <ol className="max-h-64 space-y-1.5 overflow-y-auto">
            {scenes.slice(0, 12).map((scene) => (
              <li key={scene.id} className="flex gap-2 text-caption text-zinc-400">
                <span className="shrink-0 font-mono text-amber-500/80">#{scene.id}</span>
                <span className="line-clamp-2 text-zinc-300">{scene.ttsText || "（空旁白）"}</span>
              </li>
            ))}
            {scenes.length > 12 && (
              <li className="text-caption text-zinc-500">…还有 {scenes.length - 12} 个分镜</li>
            )}
          </ol>
        )}
      </div>
    </aside>
  );
};
