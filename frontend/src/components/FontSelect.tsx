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
const RECENT_FONTS_KEY = "pixvideo.recent-fonts.v1";

const readRecentFonts = (): string[] => {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(RECENT_FONTS_KEY) || "[]");
    return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
};

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
  const recentFonts = readRecentFonts();
  const orderedFonts = useMemo(() => {
    const recentIndex = new Map(recentFonts.map((path, index) => [path, index]));
    return [...fonts].sort((a, b) => (recentIndex.get(a.path) ?? 9999) - (recentIndex.get(b.path) ?? 9999));
  }, [fonts, recentFonts.join("\u0000")]);

  const handleChange = (fontPath: string) => {
    if (fontPath) {
      const next = [fontPath, ...readRecentFonts().filter((path) => path !== fontPath)].slice(0, 8);
      try {
        window.localStorage.setItem(RECENT_FONTS_KEY, JSON.stringify(next));
      } catch {
        // Ignore storage restrictions; selection still works.
      }
    }
    onChange(fontPath);
  };

  const options = useMemo(
    () =>
      orderedFonts.map((font) => {
        const family = loadedFamilies[font.path];
        return (
          <option key={font.path} value={font.path}>
            <span className="flex min-w-0 flex-col gap-0.5">
              <span
                className="truncate text-xs"
                style={family ? { fontFamily: `"${family}", sans-serif` } : undefined}
              >
                {font.name}
                <span className="ml-1 text-caption">· {font.source}</span>
              </span>
              <span
                className="truncate text-caption text-zinc-400"
                style={family ? { fontFamily: `"${family}", sans-serif` } : undefined}
              >
                {previewText}
              </span>
            </span>
          </option>
        );
      }),
    [orderedFonts, loadedFamilies, previewText],
  );

  return (
    <div className="space-y-2">
      <Select
        value={value || ""}
        onChange={(e) => handleChange(e.target.value)}
        className={className}
        aria-label="字幕字体"
      >
        <option value="">{emptyLabel}</option>
        {options}
      </Select>
      <div
        className="ui-panel px-3 py-2 text-sm text-zinc-200"
        style={
          selectedFamily
            ? { fontFamily: `"${selectedFamily}", sans-serif` }
            : undefined
        }
      >
        <div className="text-caption uppercase tracking-wider text-zinc-500">
          {selectedFont ? `${selectedFont.name} 预览` : "默认字体预览"}
        </div>
        <div className="mt-1 truncate text-base leading-relaxed">{previewText}</div>
      </div>
    </div>
  );
};
