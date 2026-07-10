import React, { useRef, useState } from "react";
import { Move, Sparkles, Upload } from "lucide-react";

import { SpecialistUploadedFile, uploadSpecialistFiles } from "../lib/api";
import { Select } from "./Select";

interface ImageToVideoProps {
  onGenerateTask: (taskInput: any) => void;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

export const ImageToVideo: React.FC<ImageToVideoProps> = ({ onGenerateTask, addToast }) => {
  const [title, setTitle] = useState("图生视频");
  const [motionPrompt, setMotionPrompt] = useState("Smooth cinematic camera movement, preserve the subject and scene composition.");
  const [workflowKey, setWorkflowKey] = useState("runninghub/i2v_LTX2.json");
  const [image, setImage] = useState<SpecialistUploadedFile | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const imageFile = event.target.files?.item(0);
    event.target.value = "";
    if (!imageFile) return;

    setUploading(true);
    try {
      const [uploaded] = await uploadSpecialistFiles("image-to-video", [imageFile]);
      setImage(uploaded);
      addToast("参考图已上传", "success");
    } catch (error: any) {
      addToast(error.message || "参考图上传失败", "error");
    } finally {
      setUploading(false);
    }
  };

  const handleGenerate = () => {
    if (!image) {
      addToast("请先上传一张参考图", "error");
      return;
    }
    if (!motionPrompt.trim()) {
      addToast("请填写运动提示词", "error");
      return;
    }
    onGenerateTask({
      title,
      tabType: "image-to-video",
      imageFileKey: image.file_key,
      motionPrompt,
      workflowKey,
      scenes: [{ id: 1, ttsText: "", visualPrompt: motionPrompt, imageUrl: image.url }],
    });
  };

  return (
    <div className="space-y-5 animate-fade-in max-w-4xl pb-10">
      <div className="bg-[#101114] border border-zinc-900 rounded-md p-3.5">
        <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-0.5">项目名称 / Title</label>
        <input value={title} onChange={(event) => setTitle(event.target.value)} className="bg-transparent border-b border-zinc-800 text-zinc-100 font-medium text-sm w-full py-0.5 focus:outline-none focus:border-amber-500" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <section className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <div className="flex justify-between items-center"><h3 className="text-xs font-semibold text-zinc-400">起始参考图</h3>{image && <button type="button" onClick={() => setImage(null)} className="text-[10px] text-rose-400 hover:underline">清除</button>}</div>
          {image ? (
            <button type="button" onClick={() => fileInputRef.current?.click()} className="relative border border-zinc-800 rounded overflow-hidden aspect-video group w-full">
              <img src={image.url} alt={image.filename} className="w-full h-full object-cover" />
              <span className="absolute inset-0 bg-black/45 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-xs">替换参考图</span>
            </button>
          ) : (
            <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading} className="w-full border-2 border-dashed border-zinc-800 hover:border-amber-500/40 disabled:opacity-60 rounded-lg p-10 flex flex-col items-center bg-[#0c0d10]">
              <Upload className="w-6 h-6 text-zinc-600 mb-2" /><span className="text-xs font-medium text-zinc-300">{uploading ? "正在上传…" : "选择本地参考图"}</span><span className="text-[10px] text-zinc-500 mt-1">JPG、PNG、WebP</span>
            </button>
          )}
          <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={handleUpload} />
        </section>

        <section className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1"><Move className="w-4 h-4 text-amber-500" />运动与工作流</h3>
          <div><label className="block text-xs font-medium text-zinc-400 mb-1.5">运动提示词</label><textarea value={motionPrompt} onChange={(event) => setMotionPrompt(event.target.value)} className="w-full h-28 bg-[#17181c] border border-zinc-800 rounded p-2 text-xs text-zinc-300 focus:outline-none focus:border-amber-500" /></div>
          <div><label className="block text-[10px] text-zinc-500 mb-1">图生视频工作流</label><Select value={workflowKey} onChange={(event) => setWorkflowKey(event.target.value)} className="w-full bg-[#17181c] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-300"><option value="runninghub/i2v_LTX2.json">LTX-2 · RunningHub</option></Select></div>
        </section>
      </div>

      <div className="flex justify-end pt-2"><button type="button" onClick={handleGenerate} disabled={!image || uploading} className="px-6 py-2.5 bg-amber-500 disabled:opacity-60 text-black font-semibold text-xs rounded hover:bg-amber-400 flex items-center gap-2"><Sparkles className="w-4 h-4" />开始图生视频</button></div>
    </div>
  );
};
