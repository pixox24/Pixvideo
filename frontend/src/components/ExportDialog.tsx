import React, { useMemo, useState } from "react";
import { AlertTriangle, Download, X } from "lucide-react";
import { ExportSubmission, Project } from "../types";
import { buildTimelineLayout, getTimelineDuration } from "../lib/workbenchState";

interface Props {
  project: Project;
  open: boolean;
  onClose: () => void;
  onExport: (allowIncomplete: boolean) => Promise<ExportSubmission>;
  onLocateScene: (sceneId: string) => void;
}

export const ExportDialog: React.FC<Props> = ({ project, open, onClose, onExport, onLocateScene }) => {
  const [allowIncomplete, setAllowIncomplete] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const blocking = useMemo(
    () => project.scenes.filter((scene) => !scene.currentVersionId || !scene.audioUrl),
    [project],
  );
  const candidateScenes = useMemo(
    () => project.scenes.filter((scene) => scene.versions.some(
      (version) => version.source === "ai" && version.versionId !== scene.currentVersionId,
    )),
    [project],
  );
  if (!open) return null;
  const canSubmit = blocking.length === 0 || (allowIncomplete && confirmed);
  const totalDuration = getTimelineDuration(buildTimelineLayout(project.scenes));
  const bgm = String(project.config.bgm || project.config.bgm_path || "bgm-none");
  const bgmVolume = Number(project.config.bgmVolume || project.config.bgm_volume || 30);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div role="dialog" aria-modal="true" className="w-full max-w-lg rounded-xl border border-zinc-700 bg-[var(--color-surface-2)] p-5 shadow-2xl animate-soft-scale-in">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">导出检查</h2>
            <p className="mt-1 text-xs text-zinc-500">导出使用当前确认版本，生成不可变快照</p>
          </div>
          <button type="button" title="关闭" aria-label="关闭" onClick={onClose}>
            <X className="h-4 w-4 text-zinc-400" />
          </button>
        </div>
        {blocking.length > 0 ? (
          <div className="mb-4 border border-amber-500/30 bg-amber-500/5 p-3">
            <div className="mb-2 flex items-center gap-2 text-xs text-amber-300">
              <AlertTriangle className="h-4 w-4" />
              {blocking.length} 个场景缺少图片或配音
            </div>
            <div className="max-h-36 space-y-1 overflow-y-auto">
              {blocking.map((scene) => (
                <button type="button" key={scene.sceneId} onClick={() => onLocateScene(scene.sceneId)} className="block w-full text-left text-xs text-zinc-400 hover:text-zinc-200">
                  定位场景 #{scene.position + 1}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mb-4 text-xs text-emerald-400">全部场景已通过导出检查</div>
        )}
        <dl className="mb-4 grid grid-cols-2 gap-2 text-xs text-zinc-400"><div className="border border-zinc-800 p-2"><dt className="text-zinc-600">分镜 / 总时长</dt><dd className="mt-1 text-zinc-200">{project.scenes.length} / {totalDuration.toFixed(1)} 秒</dd></div><div className="border border-zinc-800 p-2"><dt className="text-zinc-600">背景音乐</dt><dd className="mt-1 truncate text-zinc-200">{bgm === "bgm-none" ? "无" : bgm} · {bgmVolume > 1 ? bgmVolume : Math.round(bgmVolume * 100)}%</dd></div></dl>
        {candidateScenes.length > 0 && (
          <div className="mb-4 border border-sky-500/30 bg-sky-500/5 p-3">
            <div className="mb-2 flex items-center gap-2 text-xs text-sky-300">
              <AlertTriangle className="h-4 w-4" />
              {candidateScenes.length} 个场景有未确认的 AI 候选版本
            </div>
            <p className="text-xs leading-5 text-zinc-400">导出仍将使用每个场景的当前版本，不会自动替换。</p>
            <div className="mt-2 max-h-24 space-y-1 overflow-y-auto">
              {candidateScenes.map((scene) => (
                <button type="button" key={scene.sceneId} onClick={() => onLocateScene(scene.sceneId)} className="block w-full text-left text-xs text-zinc-400 hover:text-zinc-200">
                  定位场景 #{scene.position + 1}
                </button>
              ))}
            </div>
          </div>
        )}
        {blocking.length > 0 && (
          <div className="space-y-2">
            <label className="flex items-center gap-2 text-xs text-zinc-300">
              <input type="checkbox" checked={allowIncomplete} onChange={(event) => { setAllowIncomplete(event.target.checked); setConfirmed(false); }} />
              只导出当前已完成版本
            </label>
            {allowIncomplete && (
              <label className="flex items-center gap-2 text-xs text-amber-300">
                <input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
                二次确认：接受缺失场景被省略
              </label>
            )}
          </div>
        )}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} className="border border-zinc-700 px-3 py-2 text-xs text-zinc-300">取消</button>
          <button
            type="button"
            disabled={!canSubmit || submitting}
            onClick={async () => { setSubmitting(true); try { await onExport(allowIncomplete); onClose(); } finally { setSubmitting(false); } }}
            className="flex items-center gap-1 bg-amber-500 px-3 py-2 text-xs font-semibold text-black disabled:opacity-40"
          >
            <Download className="h-3.5 w-3.5" />
            {submitting ? "正在提交" : "开始导出"}
          </button>
        </div>
      </div>
    </div>
  );
};
