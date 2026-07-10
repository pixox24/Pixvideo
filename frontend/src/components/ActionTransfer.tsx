import React, { useRef, useState } from "react";
import { Image, Sparkles, Upload, Video } from "lucide-react";

import { SpecialistUploadedFile, uploadSpecialistFiles } from "../lib/api";

interface ActionTransferProps {
  onGenerateTask: (taskInput: any) => void;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

export const ActionTransfer: React.FC<ActionTransferProps> = ({ onGenerateTask, addToast }) => {
  const [title, setTitle] = useState("动作迁移");
  const [prompt, setPrompt] = useState("Preserve the subject identity while following the reference motion.");
  const [duration, setDuration] = useState(12);
  const [subjectImage, setSubjectImage] = useState<SpecialistUploadedFile | null>(null);
  const [referenceVideo, setReferenceVideo] = useState<SpecialistUploadedFile | null>(null);
  const [uploading, setUploading] = useState<"image" | "video" | null>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const videoInputRef = useRef<HTMLInputElement>(null);

  const uploadOne = async (kind: "image" | "video", file: File | null) => {
    if (!file) return;
    setUploading(kind);
    try {
      const [uploaded] = await uploadSpecialistFiles(kind === "image" ? "action-transfer-image" : "action-transfer-video", [file]);
      if (kind === "image") setSubjectImage(uploaded);
      else setReferenceVideo(uploaded);
      addToast(kind === "image" ? "主体图片已上传" : "动作参考视频已上传", "success");
    } catch (error: any) {
      addToast(error.message || "素材上传失败", "error");
    } finally {
      setUploading(null);
    }
  };

  const handleGenerate = () => {
    if (!subjectImage || !referenceVideo) {
      addToast("请上传主体图片和动作参考视频", "error");
      return;
    }
    if (!prompt.trim()) {
      addToast("请填写动作迁移提示词", "error");
      return;
    }
    onGenerateTask({
      title,
      tabType: "action-transfer",
      imageFileKey: subjectImage.file_key,
      videoFileKey: referenceVideo.file_key,
      prompt,
      duration,
      workflowKey: "runninghub/af_scail.json",
      scenes: [{ id: 1, ttsText: "", visualPrompt: prompt, imageUrl: subjectImage.url }],
    });
  };

  return (
    <div className="space-y-5 animate-fade-in max-w-4xl pb-10">
      <div className="bg-[#101114] border border-zinc-900 rounded-md p-3.5"><label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-0.5">项目名称 / Title</label><input value={title} onChange={(event) => setTitle(event.target.value)} className="bg-transparent border-b border-zinc-800 text-zinc-100 font-medium text-sm w-full py-0.5 focus:outline-none focus:border-amber-500" /></div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <section className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-3">
          <h3 className="text-xs font-semibold text-zinc-400">输入素材</h3>
          <button type="button" onClick={() => imageInputRef.current?.click()} disabled={uploading !== null} className="w-full min-h-40 border border-dashed border-zinc-800 hover:border-amber-500/45 disabled:opacity-60 rounded flex flex-col items-center justify-center bg-[#0c0d10] overflow-hidden">
            {subjectImage ? <img src={subjectImage.url} alt={subjectImage.filename} className="w-full h-40 object-cover" /> : <><Image className="w-5 h-5 text-zinc-650 mb-1" /><span className="text-[10px] text-zinc-400">{uploading === "image" ? "正在上传主体…" : "选择主体图片"}</span></>}
          </button>
          <input ref={imageInputRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(event) => { const file = event.target.files?.item(0) || null; event.target.value = ""; uploadOne("image", file); }} />
          <button type="button" onClick={() => videoInputRef.current?.click()} disabled={uploading !== null} className="w-full min-h-28 border border-dashed border-zinc-800 hover:border-amber-500/45 disabled:opacity-60 rounded flex flex-col items-center justify-center bg-[#0c0d10] overflow-hidden">
            {referenceVideo ? <video src={referenceVideo.url} className="w-full h-28 object-cover" muted controls /> : <><Video className="w-5 h-5 text-zinc-650 mb-1" /><span className="text-[10px] text-zinc-400">{uploading === "video" ? "正在上传参考视频…" : "选择动作参考视频"}</span></>}
          </button>
          <input ref={videoInputRef} type="file" accept="video/mp4,video/quicktime,video/x-matroska" className="hidden" onChange={(event) => { const file = event.target.files?.item(0) || null; event.target.value = ""; uploadOne("video", file); }} />
        </section>
        <section className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <h3 className="text-xs font-semibold text-zinc-400">动作控制</h3>
          <div><label className="block text-xs font-medium text-zinc-400 mb-1">提示词</label><textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} className="w-full h-28 bg-[#17181c] border border-zinc-800 rounded p-2 text-xs text-zinc-300 focus:outline-none focus:border-amber-500" /></div>
          <div><label className="block text-[10px] text-zinc-500 mb-1">输出时长 · {duration}s</label><input type="range" min="1" max="30" value={duration} onChange={(event) => setDuration(Number(event.target.value))} className="w-full accent-amber-500" /></div>
          <p className="text-[10px] text-zinc-500">使用 RunningHub 动作迁移工作流。输出会保存到共享任务历史。</p>
        </section>
      </div>
      <div className="flex justify-end pt-2"><button type="button" onClick={handleGenerate} disabled={!subjectImage || !referenceVideo || uploading !== null} className="px-6 py-2.5 bg-amber-500 disabled:opacity-60 text-black font-semibold text-xs rounded hover:bg-amber-400 flex items-center gap-2"><Sparkles className="w-4 h-4" />开始动作迁移</button></div>
    </div>
  );
};
