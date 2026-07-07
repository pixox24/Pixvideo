import React, { useState } from "react";
import { Upload, FileImage, Layers, Play, Mic, Trash2, Clock, Sparkles } from "lucide-react";

interface CustomMediaProps {
  onGenerateTask: (taskInput: any) => void;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

export const CustomMedia: React.FC<CustomMediaProps> = ({ onGenerateTask, addToast }) => {
  const [title, setTitle] = useState("自定义露营素材混剪短视频");
  const [desc, setDesc] = useState("将上传的森林露营多维度风景图片，融合成流畅的日系治愈微电影风短片。");
  const [duration, setDuration] = useState(15);
  const [voice, setVoice] = useState("zh-CN-XiaoxiaoNeural");
  
  // Material list states
  const [materials, setMaterials] = useState<Array<{ id: string; name: string; size: string; type: string; url: string }>>([
    { id: "mat-1", name: "forest_camping_fire.jpg", size: "2.4MB", type: "image/jpeg", url: "https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?w=400&auto=format&fit=crop" },
    { id: "mat-2", name: "starry_sky_tent.jpg", size: "3.1MB", type: "image/jpeg", url: "https://images.unsplash.com/photo-1537905569762-fc72c2b2d4f5?w=400&auto=format&fit=crop" }
  ]);

  const handleUploadClick = () => {
    // Mock local file selection and populate lists
    const newId = `mat-${Date.now()}`;
    const mockFiles = [
      { id: newId, name: "tent_coffee_steam.jpg", size: "1.8MB", type: "image/jpeg", url: "https://images.unsplash.com/photo-1520201163981-8cc95007dd2a?w=400&auto=format&fit=crop" }
    ];
    setMaterials([...materials, ...mockFiles]);
    addToast("成功追加上传 1 个本地多媒体素材！已生成特征预览", "success");
  };

  const removeMaterial = (id: string) => {
    setMaterials(materials.filter((m) => m.id !== id));
    addToast("素材已从队列中移除", "info");
  };

  const handleGenerate = () => {
    if (materials.length === 0) {
      addToast("请先上传至少 1 个多媒体素材用于生成视频！", "error");
      return;
    }
    
    const taskInput = {
      title,
      tabType: "custom-media",
      workflowId: "runninghub-sdxl-animator",
      ttsMode: "edge",
      voice,
      speed: 1.0,
      bgm: "bgm-tech",
      bgmVolume: 25,
      promptPrefix: "cinematic camping visual, warm light, glowing fire sparks, highly detailed, cozy mood",
      scenes: materials.map((m, idx) => ({
        id: idx + 1,
        ttsText: idx === 0 ? "在温暖的林间篝火旁，让我们感受夜的低语。" : "星空之下，一顶帐篷支撑起所有的宁静港湾。",
        visualPrompt: `Sleek camera pan across ${m.name}, high detail, cozy aesthetic`,
        imageUrl: m.url
      }))
    };

    onGenerateTask(taskInput);
  };

  return (
    <div className="space-y-5 animate-fade-in max-w-4xl pb-10">
      {/* Panel header */}
      <div className="bg-[#101114] border border-zinc-900 rounded-md p-3.5">
        <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-0.5">
          自定义素材视频项目名称 / Title
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="bg-transparent border-b border-zinc-800 text-zinc-100 font-medium text-sm w-full py-0.5 focus:outline-none focus:border-amber-500 font-display transition-colors"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left materials manager */}
        <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-xs font-semibold text-zinc-400">素材库队列 (支持混剪排列)</h3>
            <span className="text-[10px] text-zinc-500 font-mono">已导入 {materials.length} 项</span>
          </div>

          <div
            onClick={handleUploadClick}
            className="border-2 border-dashed border-zinc-800 hover:border-amber-500/40 rounded-lg p-6 flex flex-col items-center justify-center cursor-pointer bg-[#0c0d10] hover:bg-[#121318] transition-all group"
          >
            <Upload className="w-6 h-6 text-zinc-600 group-hover:text-amber-500 mb-2 transition-colors" />
            <span className="text-xs font-medium text-zinc-300">点击或拖拽文件到这里上传</span>
            <span className="text-[10px] text-zinc-500 mt-1">支持 MP4, MOV, PNG, JPG, WebP 格式</span>
          </div>

          {/* Materials thumbnails lists */}
          <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
            {materials.map((mat) => (
              <div
                key={mat.id}
                className="bg-[#17181c] border border-zinc-850 p-2.5 rounded flex items-center justify-between gap-3 text-xs"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <img src={mat.url} alt={mat.name} className="w-10 h-10 object-cover rounded border border-zinc-800" />
                  <div className="min-w-0">
                    <span className="font-medium text-zinc-300 block truncate">{mat.name}</span>
                    <span className="text-[9px] font-mono text-zinc-500">{mat.size} • {mat.type.split("/")[1]}</span>
                  </div>
                </div>

                <button
                  onClick={() => removeMaterial(mat.id)}
                  className="p-1.5 hover:bg-rose-950/20 text-zinc-650 hover:text-rose-400 rounded transition-colors"
                  title="删除素材"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Right configuration panel */}
        <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
            <Layers className="w-4 h-4 text-amber-500" />
            生成剧本与剪辑控制
          </h3>

          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">剪辑创作意图 & 描述</label>
              <textarea
                value={desc}
                onChange={(e) => setDesc(e.target.value)}
                placeholder="例如: 让图片产生平滑的呼吸过渡，配合微风拂动与轻微阳光晕染效果。"
                className="w-full h-16 bg-[#17181c] border border-zinc-800 rounded p-2 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 placeholder-zinc-700"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                  <span>目标总时长: {duration}s</span>
                </div>
                <input
                  type="range"
                  min="5"
                  max="60"
                  step="5"
                  value={duration}
                  onChange={(e) => setDuration(parseInt(e.target.value))}
                  className="w-full accent-amber-500 h-1 cursor-pointer bg-zinc-850 rounded"
                />
              </div>

              <div>
                <label className="block text-[10px] text-zinc-500 mb-1">解说配音音色</label>
                <select
                  value={voice}
                  onChange={(e) => setVoice(e.target.value)}
                  className="w-full bg-[#17181c] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                >
                  <option value="zh-CN-XiaoxiaoNeural">晓晓 (女声 - 温暖治愈)</option>
                  <option value="zh-CN-YunxiNeural">云希 (男声 - 自然温和)</option>
                </select>
              </div>
            </div>

            <div className="bg-[#17181c] p-2.5 rounded border border-zinc-850 font-mono text-[10px] text-zinc-500 space-y-1">
              <span className="text-[11px] font-semibold text-zinc-400 block mb-1">混合渲染引擎方案:</span>
              <p>• 自动按素材数量规划分镜: 每一张图片生成 4.5s 融合切片</p>
              <p>• 自动转接流畅淡入过渡: CrossFade (15帧渲染)</p>
            </div>
          </div>
        </div>
      </div>

      <div className="flex justify-end pt-2">
        <button
          onClick={handleGenerate}
          className="px-6 py-2.5 bg-amber-500 text-black font-semibold text-xs rounded hover:bg-amber-400 shadow-xl shadow-amber-500/10 flex items-center gap-2 transition-transform active:scale-[0.99]"
        >
          <Sparkles className="w-4 h-4 text-black" />
          开始混合剪辑生成 Custom Video
        </button>
      </div>
    </div>
  );
};
