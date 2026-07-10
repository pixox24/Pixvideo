import React, { useRef, useState } from "react";
import { FileText, Image, Sparkles, Upload } from "lucide-react";

import { SpecialistUploadedFile, uploadSpecialistFiles } from "../lib/api";
import { Select } from "./Select";

interface DigitalHumanProps {
  onGenerateTask: (taskInput: any) => void;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

export const DigitalHuman: React.FC<DigitalHumanProps> = ({ onGenerateTask, addToast }) => {
  const [title, setTitle] = useState("数字人口播");
  const [mode, setMode] = useState<"customize" | "digital">("customize");
  const [script, setScript] = useState("欢迎来到 Pixelle-Video，今天为你介绍这款产品。");
  const [productTitle, setProductTitle] = useState("");
  const [voice, setVoice] = useState("zh-CN-XiaoxiaoNeural");
  const [character, setCharacter] = useState<SpecialistUploadedFile | null>(null);
  const [product, setProduct] = useState<SpecialistUploadedFile | null>(null);
  const [uploading, setUploading] = useState<"character" | "product" | null>(null);
  const characterInputRef = useRef<HTMLInputElement>(null);
  const productInputRef = useRef<HTMLInputElement>(null);

  const uploadImage = async (kind: "character" | "product", file: File | null) => {
    if (!file) return;
    setUploading(kind);
    try {
      const [uploaded] = await uploadSpecialistFiles(kind === "character" ? "digital-human-character" : "digital-human-product", [file]);
      if (kind === "character") setCharacter(uploaded);
      else setProduct(uploaded);
      addToast(kind === "character" ? "数字人角色图片已上传" : "商品图片已上传", "success");
    } catch (error: any) {
      addToast(error.message || "图片上传失败", "error");
    } finally {
      setUploading(null);
    }
  };

  const handleGenerate = () => {
    if (!character) return addToast("请先上传数字人角色图片", "error");
    if (mode === "digital" && !product) return addToast("商品模式需要上传商品图片", "error");
    if (mode === "customize" && !script.trim()) return addToast("口播模式需要填写脚本", "error");
    if (mode === "digital" && !script.trim() && !productTitle.trim()) return addToast("商品模式需要脚本或商品名称", "error");
    onGenerateTask({
      title,
      tabType: "digital-human",
      mode,
      characterFileKey: character.file_key,
      productFileKey: product?.file_key,
      productTitle,
      script,
      voice,
      speed: 1,
      scenes: [{ id: 1, ttsText: script, visualPrompt: mode === "digital" ? productTitle : "digital human" , imageUrl: character.url }],
    });
  };

  const imagePicker = (kind: "character" | "product", current: SpecialistUploadedFile | null, ref: React.RefObject<HTMLInputElement | null>) => <>
    <button type="button" onClick={() => ref.current?.click()} disabled={uploading !== null} className="w-full min-h-36 border border-dashed border-zinc-800 hover:border-amber-500/45 disabled:opacity-60 rounded flex flex-col items-center justify-center bg-[#0c0d10] overflow-hidden">
      {current ? <img src={current.url} alt={current.filename} className="w-full h-36 object-cover" /> : <><Image className="w-5 h-5 text-zinc-650 mb-1" /><span className="text-[10px] text-zinc-400">{uploading === kind ? "正在上传…" : kind === "character" ? "上传角色图片" : "上传商品图片"}</span></>}
    </button>
    <input ref={ref} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(event) => { const file = event.target.files?.item(0) || null; event.target.value = ""; uploadImage(kind, file); }} />
  </>;

  return (
    <div className="space-y-5 animate-fade-in max-w-4xl pb-10">
      <div className="bg-[#101114] border border-zinc-900 rounded-md p-3.5"><label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-0.5">项目名称 / Title</label><input value={title} onChange={(event) => setTitle(event.target.value)} className="bg-transparent border-b border-zinc-800 text-zinc-100 font-medium text-sm w-full py-0.5 focus:outline-none focus:border-amber-500" /></div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <section className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4"><h3 className="text-xs font-semibold text-zinc-400">真实素材</h3>{imagePicker("character", character, characterInputRef)}{mode === "digital" && imagePicker("product", product, productInputRef)}</section>
        <section className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4"><h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1"><FileText className="w-4 h-4 text-amber-500" />口播设置</h3><div className="grid grid-cols-2 gap-2"><button type="button" onClick={() => setMode("customize")} className={`py-2 rounded border text-xs ${mode === "customize" ? "border-amber-500 text-amber-400" : "border-zinc-800 text-zinc-400"}`}>直接口播</button><button type="button" onClick={() => setMode("digital")} className={`py-2 rounded border text-xs ${mode === "digital" ? "border-amber-500 text-amber-400" : "border-zinc-800 text-zinc-400"}`}>商品合成</button></div>{mode === "digital" && <input value={productTitle} onChange={(event) => setProductTitle(event.target.value)} placeholder="商品名称（无脚本时用于生成文案）" className="w-full bg-[#17181c] border border-zinc-800 rounded p-2 text-xs text-zinc-300" />}<textarea value={script} onChange={(event) => setScript(event.target.value)} placeholder="输入口播脚本；商品模式中可留空并填写商品名称" className="w-full h-28 bg-[#17181c] border border-zinc-800 rounded p-2 text-xs text-zinc-300 focus:outline-none focus:border-amber-500" /><Select value={voice} onChange={(event) => setVoice(event.target.value)} className="w-full bg-[#17181c] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-300"><option value="zh-CN-XiaoxiaoNeural">晓晓</option><option value="zh-CN-YunxiNeural">云希</option></Select></section>
      </div>
      <div className="flex justify-end pt-2"><button type="button" onClick={handleGenerate} disabled={!character || uploading !== null || (mode === "digital" && !product)} className="px-6 py-2.5 bg-amber-500 disabled:opacity-60 text-black font-semibold text-xs rounded hover:bg-amber-400 flex items-center gap-2"><Sparkles className="w-4 h-4" />生成数字人口播</button></div>
    </div>
  );
};
