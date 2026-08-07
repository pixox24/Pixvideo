import React from "react";
import { RefreshCw, Upload } from "lucide-react";
import { WorkbenchScene } from "../types";

interface Props { scene: WorkbenchScene | null; onRegenerateImage?: (prompt: string) => void; onUpload?: (file: File) => void; }
export const SceneInspector: React.FC<Props> = ({ scene, onRegenerateImage, onUpload }) => {
  if (!scene) return <aside className="border-l border-zinc-800 bg-[#0d0e11] p-4 text-xs text-zinc-500">选择一个分镜查看提示词与候选版本</aside>;
  return <aside className="min-h-0 overflow-y-auto border-l border-zinc-800 bg-[#0d0e11] p-4">
    <div className="mb-3 text-xs font-semibold text-zinc-200">提示词 / 版本</div>
    <label className="mb-2 block text-[10px] text-zinc-500">旁白<textarea className="mt-1 min-h-20 w-full resize-y border border-zinc-800 bg-zinc-950 p-2 text-xs text-zinc-200" defaultValue={scene.narration} /></label>
    <label className="mb-3 block text-[10px] text-zinc-500">提示词<textarea className="mt-1 min-h-24 w-full resize-y border border-zinc-800 bg-zinc-950 p-2 text-xs text-zinc-200" defaultValue={scene.visualPrompt} /></label>
    <div className="mb-3 grid grid-cols-2 gap-2"><button type="button" title="重新生成" aria-label="重新生成" onClick={() => onRegenerateImage?.(scene.visualPrompt)} className="flex items-center justify-center gap-1 bg-amber-500 px-2 py-2 text-xs font-semibold text-black"><RefreshCw className="h-3.5 w-3.5" />重新生成</button><label className="flex cursor-pointer items-center justify-center gap-1 border border-zinc-700 px-2 py-2 text-xs text-zinc-300"><Upload className="h-3.5 w-3.5" />上传<input className="hidden" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => event.target.files?.[0] && onUpload?.(event.target.files[0])} /></label></div>
    <div className="space-y-2">{scene.versions.map((version) => <div key={version.versionId} className={`border p-2 ${version.versionId === scene.currentVersionId ? "border-amber-500" : "border-zinc-800"}`}><img src={version.thumbnailUrl || version.imageUrl} alt="候选版本" className="aspect-video w-full object-cover" /><div className="mt-1 text-[10px] text-zinc-500">{version.versionId === scene.currentVersionId ? "当前版本" : "候选版本"}</div></div>)}</div>
  </aside>;
};

