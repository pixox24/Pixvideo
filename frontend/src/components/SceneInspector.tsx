import React, { useEffect, useState } from "react";
import { Check, Loader, Lock, RefreshCw, Unlock, Upload, Volume2 } from "lucide-react";
import { WorkbenchScene } from "../types";

interface Props {
  scene: WorkbenchScene | null;
  onSave: (patch: Partial<Pick<WorkbenchScene, "narration" | "visualPrompt" | "visualFocus" | "textAnchors" | "lockedFields" | "editedFields" | "locked">>) => Promise<void>;
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
  useEffect(() => { setNarration(scene?.narration || ""); setPrompt(scene?.visualPrompt || ""); setSaveState("idle"); }, [scene?.sceneId, scene?.narration, scene?.visualPrompt]);
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
        <span className="flex items-center gap-1.5">
          提示词 / 版本
          {scene.locked && <span className="ui-chip ui-chip-brand !py-0"><Lock className="h-3 w-3" />已锁定</span>}
          {!scene.locked && (scene.editedFields || []).length > 0 && <span className="text-sky-300">人工编辑</span>}
        </span>
        <span className="text-caption">
          {saveState === "saving" ? "保存中" : saveState === "saved" ? "已保存" : saveState === "failed" ? "保存失败" : ""}
        </span>
      </div>
      <div className="mb-3 flex items-center justify-between gap-2 rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] px-2 py-1.5 text-caption text-zinc-400">
        <span>{scene.locked ? "重新生成会跳过此镜头" : "人工修改会自动保留"}</span>
        <button
          type="button"
          disabled={Boolean(busy)}
          onClick={() => run("lock", () => onSave({ locked: !scene.locked }))}
          className="ui-btn ui-btn-secondary ui-btn-sm"
          title={scene.locked ? "解锁此镜头" : "锁定此镜头"}
        >
          {scene.locked ? <Unlock className="h-3.5 w-3.5" /> : <Lock className="h-3.5 w-3.5" />}
          {scene.locked ? "解锁" : "锁定"}
        </button>
      </div>
      <label className="mb-2 block text-label">
        旁白
        <textarea
          value={narration}
          onChange={(event) => setNarration(event.target.value)}
          disabled={Boolean(scene.locked || scene.lockedFields?.includes("narration"))}
          className="ui-input mt-1 min-h-20 w-full resize-y !h-auto py-2"
        />
      </label>
      {(scene.visualFocus || (scene.textAnchors || []).length > 0) && (
        <div className="mb-3 rounded border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] px-2 py-1.5 text-caption text-zinc-400">
          <div>视觉焦点：{scene.visualFocus || "—"}</div>
          {(scene.textAnchors || []).length > 0 && <div className="mt-0.5">文字锚点：{scene.textAnchors!.join("、")}</div>}
        </div>
      )}
      <button
        type="button"
        disabled={Boolean(busy) || scene.locked || !narration.trim()}
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
          disabled={Boolean(scene.locked || scene.lockedFields?.includes("visualPrompt"))}
          className="ui-input mt-1 min-h-24 w-full resize-y !h-auto py-2"
        />
      </label>
      <div className="mb-3 grid grid-cols-2 gap-2">
        <button
          type="button"
          title="重新生成"
          aria-label="重新生成"
          disabled={Boolean(busy) || scene.locked || !prompt.trim()}
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
            disabled={Boolean(scene.locked)}
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
