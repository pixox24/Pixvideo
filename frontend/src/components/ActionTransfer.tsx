import React, { useState } from "react";
import { Upload, Users, Play, Workflow, Sparkles, Sliders, RefreshCw, Layers } from "lucide-react";

interface ActionTransferProps {
  onGenerateTask: (taskInput: any) => void;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

export const ActionTransfer: React.FC<ActionTransferProps> = ({ onGenerateTask, addToast }) => {
  const [title, setTitle] = useState("国风武侠角色动作迁移测试");
  const [prompt, setPrompt] = useState("A heroic martial arts monk performing sword form, cinematic background, golden autumn forest falling leaves, majestic, high-contrast, amber lights");
  const [conformance, setConformance] = useState(85); // Motion matching rate
  const [workflow, setWorkflow] = useState("runninghub-sdxl-animator");

  // Subject and skeleton video state preview
  const [subjectUrl, setSubjectUrl] = useState("https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&auto=format&fit=crop");
  const [skeletonUrl, setSkeletonUrl] = useState("https://images.unsplash.com/photo-1517841905240-472988babdf9?w=400&auto=format&fit=crop");

  const handleUploadSubject = () => {
    setSubjectUrl("https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&auto=format&fit=crop");
    addToast("已载入目标角色主题素材！已缓存边缘特征", "success");
  };

  const handleUploadSkeleton = () => {
    setSkeletonUrl("https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&auto=format&fit=crop");
    addToast("已载入动作姿态参考源骨架！已解析 OpenPose 数据", "success");
  };

  const handleGenerate = () => {
    if (!subjectUrl || !skeletonUrl) {
      addToast("进行动作迁移前，需先导入角色素材与动作参考素材！", "error");
      return;
    }

    const taskInput = {
      title,
      tabType: "action-transfer",
      workflowId: workflow,
      ttsMode: "edge",
      voice: "zh-CN-YunxiNeural",
      speed: 1.0,
      bgm: "bgm-epic",
      bgmVolume: 35,
      promptPrefix: "action transfer rendering, martial arts fluid movement, extreme detail",
      scenes: [
        { id: 1, ttsText: "动作捕捉，时空折叠。", visualPrompt: prompt, imageUrl: subjectUrl }
      ]
    };

    onGenerateTask(taskInput);
  };

  return (
    <div className="space-y-5 animate-fade-in max-w-4xl pb-10">
      {/* Panel header */}
      <div className="bg-[#101114] border border-zinc-900 rounded-md p-3.5">
        <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-0.5">
          动作迁移项目名称 / Project Title
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="bg-transparent border-b border-zinc-800 text-zinc-100 font-medium text-sm w-full py-0.5 focus:outline-none focus:border-amber-500 font-display transition-colors"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left materials uploaded row */}
        <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <h3 className="text-xs font-semibold text-zinc-400">导入双轨参考轨 / Reference Tracks</h3>

          <div className="grid grid-cols-2 gap-3">
            {/* Subject character */}
            <div className="space-y-2">
              <span className="text-[10px] text-zinc-500 font-medium block">角色/主体素材 (Subject)</span>
              {subjectUrl ? (
                <div className="relative border border-zinc-800 rounded overflow-hidden aspect-[3/4]">
                  <img src={subjectUrl} alt="Subject" className="w-full h-full object-cover" />
                  <button
                    onClick={handleUploadSubject}
                    className="absolute bottom-2 left-2 right-2 py-1 bg-black/80 rounded border border-zinc-750 text-[10px] text-zinc-300 hover:text-white"
                  >
                    替换角色
                  </button>
                </div>
              ) : (
                <div
                  onClick={handleUploadSubject}
                  className="border border-dashed border-zinc-800 hover:border-amber-500/45 rounded aspect-[3/4] flex flex-col items-center justify-center cursor-pointer bg-[#0c0d10]"
                >
                  <Upload className="w-5 h-5 text-zinc-650 mb-1" />
                  <span className="text-[10px] text-zinc-400">导入角色图/视频</span>
                </div>
              )}
            </div>

            {/* Skeleton reference */}
            <div className="space-y-2">
              <span className="text-[10px] text-zinc-500 font-medium block">动作骨骼/视频参考 (Skeleton)</span>
              {skeletonUrl ? (
                <div className="relative border border-zinc-800 rounded overflow-hidden aspect-[3/4]">
                  <img src={skeletonUrl} alt="Skeleton" className="w-full h-full object-cover grayscale opacity-80" />
                  <button
                    onClick={handleUploadSkeleton}
                    className="absolute bottom-2 left-2 right-2 py-1 bg-black/80 rounded border border-zinc-750 text-[10px] text-zinc-300 hover:text-white"
                  >
                    替换骨骼参考
                  </button>
                </div>
              ) : (
                <div
                  onClick={handleUploadSkeleton}
                  className="border border-dashed border-zinc-800 hover:border-amber-500/45 rounded aspect-[3/4] flex flex-col items-center justify-center cursor-pointer bg-[#0c0d10]"
                >
                  <Upload className="w-5 h-5 text-zinc-650 mb-1" />
                  <span className="text-[10px] text-zinc-400">导入骨架/姿态视频</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right prompt guiding */}
        <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1">
            <Workflow className="w-4 h-4 text-amber-500" />
            ControlNet 骨骼一致性迁移权重
          </h3>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">画风融合描述提示词 / Prompts</label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="请输入如何渲染角色画风、背景、光影细节等..."
                className="w-full h-24 bg-[#17181c] border border-zinc-800 rounded p-2.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 leading-relaxed placeholder-zinc-700"
              />
            </div>

            <div className="grid grid-cols-2 gap-3 items-center">
              <div>
                <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                  <span>姿态匹配率: {conformance}%</span>
                </div>
                <input
                  type="range"
                  min="50"
                  max="100"
                  step="5"
                  value={conformance}
                  onChange={(e) => setConformance(parseInt(e.target.value))}
                  className="w-full accent-amber-500 h-1 cursor-pointer bg-zinc-850 rounded"
                />
              </div>

              <div>
                <label className="block text-[10px] text-zinc-500 mb-1">物理渲染引擎</label>
                <select
                  value={workflow}
                  onChange={(e) => setWorkflow(e.target.value)}
                  className="w-full bg-[#17181c] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                >
                  <option value="runninghub-sdxl-animator">RunningHub DW-Pose 精准骨架</option>
                  <option value="bizyair-flux-upscale">BizyAir OpenPose 高清渲染</option>
                </select>
              </div>
            </div>

            <div className="bg-[#17181c] p-2 rounded border border-zinc-850 text-[10px] text-zinc-500 leading-normal font-mono">
              提示: 系统已自动挂载 OpenPose、DW-Pose 算子，支持对非标准人体比例进行自适应姿态对齐迁移。
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
          动作姿态对齐生成 Action Transfer
        </button>
      </div>
    </div>
  );
};
