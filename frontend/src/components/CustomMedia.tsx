import React, { useRef, useState } from "react";
import { FileImage, Layers, Sparkles, Trash2, Upload } from "lucide-react";

import { SpecialistUploadedFile, uploadSpecialistFiles } from "../lib/api";
import { Select } from "./Select";

interface CustomMediaProps {
  onGenerateTask: (taskInput: any) => void;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

export const CustomMedia: React.FC<CustomMediaProps> = ({ onGenerateTask, addToast }) => {
  const [title, setTitle] = useState("自定义素材混剪短视频");
  const [intent, setIntent] = useState("将上传的素材编排成连贯、自然的短视频。");
  const [duration, setDuration] = useState(15);
  const [voice, setVoice] = useState("zh-CN-XiaoxiaoNeural");
  const [materials, setMaterials] = useState<SpecialistUploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files: File[] = [];
    const selectedFiles = event.target.files;
    if (selectedFiles) {
      for (let index = 0; index < selectedFiles.length; index += 1) {
        const file = selectedFiles.item(index);
        if (file) files.push(file);
      }
    }
    event.target.value = "";
    if (files.length === 0) return;

    setUploading(true);
    try {
      const uploaded = await uploadSpecialistFiles("custom-media", files);
      setMaterials((current) => [...current, ...uploaded]);
      addToast(`已上传 ${uploaded.length} 个素材`, "success");
    } catch (error: any) {
      addToast(error.message || "素材上传失败", "error");
    } finally {
      setUploading(false);
    }
  };

  const removeMaterial = (fileKey: string) => {
    setMaterials((current) => current.filter((material) => material.file_key !== fileKey));
  };

  const handleGenerate = () => {
    if (materials.length === 0) {
      addToast("请先上传至少一个图片或视频素材", "error");
      return;
    }

    onGenerateTask({
      title,
      tabType: "custom-media",
      assetFileKeys: materials.map((material) => material.file_key),
      intent,
      duration,
      voice,
      speed: 1,
      scenes: materials.map((material, index) => ({
        id: index + 1,
        ttsText: index === 0 ? intent : "",
        visualPrompt: material.filename,
        imageUrl: material.url,
      })),
    });
  };

  return (
    <div className="space-y-5 animate-fade-in max-w-4xl pb-10">
      <div className="bg-[#101114] border border-zinc-900 rounded-md p-3.5">
        <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-0.5">
          项目名称 / Title
        </label>
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          className="bg-transparent border-b border-zinc-800 text-zinc-100 font-medium text-sm w-full py-0.5 focus:outline-none focus:border-amber-500"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <section className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-xs font-semibold text-zinc-400">素材队列</h3>
            <span className="text-[10px] text-zinc-500 font-mono">{materials.length} 项</span>
          </div>

          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="w-full border-2 border-dashed border-zinc-800 hover:border-amber-500/40 disabled:opacity-60 rounded-lg p-6 flex flex-col items-center justify-center bg-[#0c0d10] hover:bg-[#121318] transition-all"
          >
            <Upload className="w-6 h-6 text-zinc-600 mb-2" />
            <span className="text-xs font-medium text-zinc-300">{uploading ? "正在上传…" : "选择图片或视频素材"}</span>
            <span className="text-[10px] text-zinc-500 mt-1">MP4、MOV、PNG、JPG、GIF、WebP</span>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime,video/x-msvideo,video/x-matroska,video/webm"
            className="hidden"
            onChange={handleUpload}
          />

          <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
            {materials.map((material) => (
              <div key={material.file_key} className="bg-[#17181c] border border-zinc-850 p-2.5 rounded flex items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-2.5 min-w-0">
                  {material.content_type.startsWith("image/") ? (
                    <img src={material.url} alt={material.filename} className="w-10 h-10 object-cover rounded border border-zinc-800" />
                  ) : (
                    <div className="w-10 h-10 rounded border border-zinc-800 flex items-center justify-center text-zinc-500"><FileImage className="w-4 h-4" /></div>
                  )}
                  <div className="min-w-0">
                    <span className="font-medium text-zinc-300 block truncate">{material.filename}</span>
                    <span className="text-[9px] font-mono text-zinc-500">{(material.size / 1024 / 1024).toFixed(1)} MB · {material.content_type.split("/")[1] || "media"}</span>
                  </div>
                </div>
                <button type="button" onClick={() => removeMaterial(material.file_key)} className="p-1.5 hover:bg-rose-950/20 text-zinc-650 hover:text-rose-400 rounded" title="移除素材">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        </section>

        <section className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5"><Layers className="w-4 h-4 text-amber-500" />创作与剪辑控制</h3>
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">创作意图</label>
            <textarea value={intent} onChange={(event) => setIntent(event.target.value)} className="w-full h-24 bg-[#17181c] border border-zinc-800 rounded p-2 text-xs text-zinc-300 focus:outline-none focus:border-amber-500" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-[10px] text-zinc-500 mb-1">目标时长 · {duration}s</label>
              <input type="range" min="5" max="60" step="5" value={duration} onChange={(event) => setDuration(Number(event.target.value))} className="w-full accent-amber-500" />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 mb-1">解说音色</label>
              <Select value={voice} onChange={(event) => setVoice(event.target.value)} className="w-full bg-[#17181c] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-300">
                <option value="zh-CN-XiaoxiaoNeural">晓晓</option>
                <option value="zh-CN-YunxiNeural">云希</option>
              </Select>
            </div>
          </div>
        </section>
      </div>

      <div className="flex justify-end pt-2">
        <button type="button" onClick={handleGenerate} disabled={uploading || materials.length === 0} className="px-6 py-2.5 bg-amber-500 disabled:opacity-60 text-black font-semibold text-xs rounded hover:bg-amber-400 flex items-center gap-2">
          <Sparkles className="w-4 h-4" />开始混剪生成
        </button>
      </div>
    </div>
  );
};
