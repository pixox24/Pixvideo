import React, { useState } from "react";
import { Upload, FileImage, Sliders, Play, Move, Sparkles, Trash2, Video } from "lucide-react";

interface ImageToVideoProps {
  onGenerateTask: (taskInput: any) => void;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

export const ImageToVideo: React.FC<ImageToVideoProps> = ({ onGenerateTask, addToast }) => {
  const [title, setTitle] = useState("星舰穿越光速图生视频渲染");
  const [motionPrompt, setMotionPrompt] = useState("Dramatic zoom-in shot, spaceship engine glowing with intense orange light, stars stretching into neon hyperdrive lines, hyperrealistic, 4k");
  const [motionStrength, setMotionStrength] = useState(7);
  const [workflow, setWorkflow] = useState("runninghub-sdxl-animator");
  const [imageUrl, setImageUrl] = useState("https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=600&auto=format&fit=crop");

  const handleUploadClick = () => {
    // Simulated upload of new base photo
    setImageUrl("https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?w=600&auto=format&fit=crop");
    addToast("成功载入图生视频起始参考底图！", "success");
  };

  const handleGenerate = () => {
    if (!imageUrl) {
      addToast("图生视频需要先导入 1 张起始参考图片！", "error");
      return;
    }

    const taskInput = {
      title,
      tabType: "image-to-video",
      workflowId: workflow,
      ttsMode: "edge",
      voice: "zh-CN-YunxiNeural",
      speed: 1.0,
      bgm: "bgm-cyber",
      bgmVolume: 35,
      promptPrefix: "high dynamic motion, cosmic depth, starry parallax",
      scenes: [
        { id: 1, ttsText: "光速之门正在缓缓打开。", visualPrompt: motionPrompt, imageUrl }
      ]
    };

    onGenerateTask(taskInput);
  };

  return (
    <div className="space-y-5 animate-fade-in max-w-4xl pb-10">
      {/* Panel header */}
      <div className="bg-[#101114] border border-zinc-900 rounded-md p-3.5">
        <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-0.5">
          图生视频项目名称 / Project Title
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="bg-transparent border-b border-zinc-800 text-zinc-100 font-medium text-sm w-full py-0.5 focus:outline-none focus:border-amber-500 font-display transition-colors"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left base image config */}
        <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-xs font-semibold text-zinc-400">起始参考底稿 / Starting Frame</h3>
            {imageUrl && (
              <button
                onClick={() => setImageUrl("")}
                className="text-[10px] text-rose-400 hover:underline flex items-center gap-0.5"
              >
                清除底图
              </button>
            )}
          </div>

          {imageUrl ? (
            <div className="relative border border-zinc-800 rounded overflow-hidden aspect-video group">
              <img src={imageUrl} alt="Base" className="w-full h-full object-cover" />
              <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <button
                  onClick={handleUploadClick}
                  className="px-3 py-1.5 bg-black/80 rounded border border-zinc-750 text-xs text-zinc-300 hover:text-white"
                >
                  替换底稿图片
                </button>
              </div>
            </div>
          ) : (
            <div
              onClick={handleUploadClick}
              className="border-2 border-dashed border-zinc-800 hover:border-amber-500/40 rounded-lg p-10 flex flex-col items-center justify-center cursor-pointer bg-[#0c0d10]"
            >
              <Upload className="w-6 h-6 text-zinc-600 mb-2" />
              <span className="text-xs font-medium text-zinc-300">导入本地首帧图</span>
              <span className="text-[10px] text-zinc-500 mt-1">推荐比例 16:9, 分辨率 1080p+</span>
            </div>
          )}

          <div className="bg-[#17181c] p-2.5 rounded border border-zinc-850 text-[10px] text-zinc-500 leading-normal">
            图生视频算法（Image-to-Video）支持提取图片中的语义、轮廓、材质与空间结构，融合 AnimateDiff 进行时序运动扩散，能最大程度保障人物或商品不走样变形。
          </div>
        </div>

        {/* Right movement parameters */}
        <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1">
            <Move className="w-4 h-4 text-amber-500" />
            动力学与摄像机摇移设置
          </h3>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">视频运动提示词 / Motion Guidance</label>
              <textarea
                value={motionPrompt}
                onChange={(e) => setMotionPrompt(e.target.value)}
                placeholder="例如: 镜头剧烈推入，星云闪烁，火焰喷射，碎屑飞舞，高动态摄影。"
                className="w-full h-24 bg-[#17181c] border border-zinc-800 rounded p-2 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 leading-relaxed placeholder-zinc-700"
              />
            </div>

            <div className="grid grid-cols-2 gap-3 items-center">
              <div>
                <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                  <span>运动幅度强度: {motionStrength}</span>
                  <span>1-10</span>
                </div>
                <input
                  type="range"
                  min="1"
                  max="10"
                  step="1"
                  value={motionStrength}
                  onChange={(e) => setMotionStrength(parseInt(e.target.value))}
                  className="w-full accent-amber-500 h-1 cursor-pointer bg-zinc-850 rounded"
                />
              </div>

              <div>
                <label className="block text-[10px] text-zinc-500 mb-1">渲染引擎 / Flow</label>
                <select
                  value={workflow}
                  onChange={(e) => setWorkflow(e.target.value)}
                  className="w-full bg-[#17181c] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                >
                  <option value="runninghub-sdxl-animator">SDXL AnimateDiff v3</option>
                  <option value="bizyair-flux-upscale">FLUX SVD Upscale</option>
                </select>
              </div>
            </div>

            <div className="bg-[#17181c] p-2 rounded border border-zinc-850 space-y-1 text-[10px] text-zinc-500 font-mono">
              <span className="text-[11px] font-semibold text-zinc-400 block mb-0.5">运动特性:</span>
              <p>• 时序连贯度(Guidance): 7.5 | 去噪循环数(Steps): 25 步</p>
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
          图生视频合成渲染 Image to Video
        </button>
      </div>
    </div>
  );
};
