import React, { useEffect, useState } from "react";
import { Check, Loader, RefreshCw, Upload, Volume2 } from "lucide-react";
import { WorkbenchScene } from "../types";

interface Props {
  scene: WorkbenchScene | null;
  onSave: (patch: { narration?: string; visualPrompt?: string }) => Promise<void>;
  onRegenerateImage: (prompt: string) => Promise<void>;
  onRegenerateTts: (narration: string) => Promise<void>;
  onUpload: (file: File) => Promise<void>;
  onSelectVersion: (versionId: string) => Promise<void>;
  className?: string;
}

export const SceneInspector: React.FC<Props> = ({ scene, onSave, onRegenerateImage, onRegenerateTts, onUpload, onSelectVersion, className = "" }) => {
  const [narration, setNarration] = useState("");
  const [prompt, setPrompt] = useState("");
  const [saveState, setSaveState] = useState("idle");
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { setNarration(scene?.narration || ""); setPrompt(scene?.visualPrompt || ""); setSaveState("idle"); }, [scene?.sceneId]);
  useEffect(() => {
    if (!scene || (narration === scene.narration && prompt === scene.visualPrompt)) return;
    const timer = window.setTimeout(async () => { setSaveState("saving"); try { await onSave({ narration, visualPrompt: prompt }); setSaveState("saved"); } catch { setSaveState("failed"); } }, 500);
    return () => window.clearTimeout(timer);
  }, [scene, narration, prompt, onSave]);
  const run = async (key: string, action: () => Promise<void>) => { setBusy(key); try { await action(); } finally { setBusy(null); } };
  if (!scene) {
    return (
      <aside
        className={`border-l border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-4 text-xs text-zinc-500 ${className}`}
      >
        选择一个分镜查看提示词与候选版本
      </aside>
    );
  }
  return (
    <aside
      className={`min-h-0 overflow-y-auto border-l border-[var(--color-border-subtle)] bg-[var(--color-surface-1)] p-4 ${className}`}
    >
      <div className="mb-3 flex items-center justify-between text-xs font-semibold text-zinc-200">
        <span>提示词 / 版本</span>
        <span className="text-caption">
          {saveState === "saving" ? "保存中" : saveState === "saved" ? "已保存" : saveState === "failed" ? "保存失败" : ""}
        </span>
      </div>
      <label className="mb-2 block text-label">
        旁白
        <textarea
          value={narration}
          onChange={(event) => setNarration(event.target.value)}
          className="ui-input mt-1 min-h-20 w-full resize-y !h-auto py-2"
        />
      </label>
      <button
        type="button"
        disabled={Boolean(busy) || !narration.trim()}
        onClick={() => run("tts", () => onRegenerateTts(narration))}
        className="ui-btn ui-btn-secondary mb-3 w-full"
      >
        {busy === "tts" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <Volume2 className="h-3.5 w-3.5" />}
        重新生成配音
      </button>
      <label className="mb-3 block text-label">
        提示词
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          className="ui-input mt-1 min-h-24 w-full resize-y !h-auto py-2"
        />
      </label>
      <div className="mb-3 grid grid-cols-2 gap-2">
        <button
          type="button"
          title="重新生成"
          aria-label="重新生成"
          disabled={Boolean(busy) || !prompt.trim()}
          onClick={() => run("image", () => onRegenerateImage(prompt))}
          className="ui-btn ui-btn-primary ui-btn-sm"
        >
          {busy === "image" ? <Loader className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          重新生成
        </button>
        <label className="ui-btn ui-btn-secondary ui-btn-sm cursor-pointer">
          <Upload className="h-3.5 w-3.5" />
          上传
          <input
            className="hidden"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void run("upload", () => onUpload(file));
            }}
          />
        </label>
      </div>
      <div className="space-y-2">
        {scene.versions.map((version) => {
          const current = version.versionId === scene.currentVersionId;
          return (
            <div
              key={version.versionId}
              className={`rounded-[var(--radius-md)] border p-2 ${
                current ? "border-amber-500/50 ring-1 ring-amber-500/20" : "border-[var(--color-border-subtle)]"
              }`}
            >
              <img
                src={version.thumbnailUrl || version.imageUrl}
                alt="候选版本"
                className="aspect-video w-full rounded-[var(--radius-sm)] object-cover"
              />
              <div className="mt-2 flex items-center justify-between text-caption">
                <span>{current ? "当前版本" : "候选版本"}</span>
                {current ? (
                  <Check className="h-3.5 w-3.5 text-amber-400" />
                ) : (
                  <button
                    type="button"
                    disabled={Boolean(busy)}
                    onClick={() => run(version.versionId, () => onSelectVersion(version.versionId))}
                    className="ui-btn ui-btn-secondary ui-btn-sm !h-7 !px-2"
                  >
                    使用此版本
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </aside>
  );
};
