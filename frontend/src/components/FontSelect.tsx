import React, { useEffect, useMemo, useState } from "react";
import { Select } from "./Select";
import { FontOption } from "../types";

type FontSelectProps = {
  value: string;
  fonts: FontOption[];
  onChange: (fontPath: string) => void;
  className?: string;
  emptyLabel?: string;
  previewText?: string;
};

const fontFamilyForPath = (path: string) =>
  `PixFont_${path.replace(/[^a-zA-Z0-9_-]/g, "_").slice(-48)}`;

/**
 * Font picker that loads real font faces and previews them in the dropdown.
 */
export const FontSelect: React.FC<FontSelectProps> = ({
  value,
  fonts,
  onChange,
  className = "",
  emptyLabel = "自动选择中文字体",
  previewText = "字幕预览 Aa 123",
}) => {
  const [loadedFamilies, setLoadedFamilies] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!document.fonts || typeof FontFace === "undefined") return;

    let cancelled = false;
    const loaded: FontFace[] = [];

    const load = async () => {
      const next: Record<string, string> = {};
      await Promise.all(
        fonts.map(async (font) => {
          if (!font.path) return;
          const family = fontFamilyForPath(font.path);
          try {
            const face = new FontFace(
              family,
              `url("/api/resources/fonts/file?path=${encodeURIComponent(font.path)}")`,
            );
            const ready = await face.load();
            if (cancelled) return;
            document.fonts.add(ready);
            loaded.push(ready);
            next[font.path] = family;
          } catch {
            // Keep system fallback; option still lists the font name.
          }
        }),
      );
      if (!cancelled) setLoadedFamilies(next);
    };

    void load();
    return () => {
      cancelled = true;
      for (const face of loaded) {
        try {
          document.fonts.delete(face);
        } catch {
          // ignore
        }
      }
    };
  }, [fonts]);

  const selectedFamily = value ? loadedFamilies[value] : undefined;
  const selectedFont = fonts.find((font) => font.path === value);

  const options = useMemo(
    () =>
      fonts.map((font) => {
        const family = loadedFamilies[font.path];
        return (
          <option key={font.path} value={font.path}>
            <span className="flex min-w-0 flex-col gap-0.5">
              <span
                className="truncate text-xs"
                style={family ? { fontFamily: `"${family}", sans-serif` } : undefined}
              >
                {font.name}
                <span className="ml-1 text-[10px] text-zinc-500">· {font.source}</span>
              </span>
              <span
                className="truncate text-[11px] text-zinc-400"
                style={family ? { fontFamily: `"${family}", sans-serif` } : undefined}
              >
                {previewText}
              </span>
            </span>
          </option>
        );
      }),
    [fonts, loadedFamilies, previewText],
  );

  return (
    <div className="space-y-2">
      <Select
        value={value || ""}
        onChange={(e) => onChange(e.target.value)}
        className={className}
        aria-label="字幕字体"
      >
        <option value="">{emptyLabel}</option>
        {options}
      </Select>
      <div
        className="rounded border border-zinc-800 bg-[#0c0d10] px-3 py-2 text-sm text-zinc-200"
        style={
          selectedFamily
            ? { fontFamily: `"${selectedFamily}", sans-serif` }
            : undefined
        }
      >
        <div className="text-[10px] uppercase tracking-wider text-zinc-500">
          {selectedFont ? `${selectedFont.name} 预览` : "默认字体预览"}
        </div>
        <div className="mt-1 truncate text-base leading-relaxed">{previewText}</div>
      </div>
    </div>
  );
};
