import React, { useState } from "react";
import { User, FileText, Settings, Sparkles, Mic, Play, ArrowRight, Volume2, Upload } from "lucide-react";
import { VOICE_OPTIONS } from "../data";

interface DigitalHumanProps {
  onGenerateTask: (taskInput: any) => void;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

export const DigitalHuman: React.FC<DigitalHumanProps> = ({ onGenerateTask, addToast }) => {
  const [title, setTitle] = useState("智能AI数字人口播带货短视频");
  const [speech, setSpeech] = useState("大家好！今天给大家推荐一款颠覆性的 AI 生产力应用。无需繁琐的剪辑，只需输入创意主题，三步即可生成大片级视觉视频！");
  const [voice, setVoice] = useState("male-qn-qingse");
  const [activeAvatar, setActiveAvatar] = useState("av-1");
  const [bgType, setBgType] = useState<"office" | "studio" | "upload">("studio");
  const [generatingScript, setGeneratingScript] = useState(false);

  // Ready avatar list
  const avatars = [
    { id: "av-1", name: "知性女主播 (雨涵)", desc: "适合带货、教育、知识分享", img: "https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=150&auto=format&fit=crop" },
    { id: "av-2", name: "青年男讲师 (子轩)", desc: "适合科技讲解、时事评述", img: "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=150&auto=format&fit=crop" },
    { id: "av-3", name: "元气少女 (小萌)", desc: "适合二次元与生活好物推荐", img: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop" }
  ];

  // AI copywriting generator via simulated micro-LLM prompt
  const handleAIGenerateSpeech = () => {
    setGeneratingScript(true);
    addToast("大模型正在撰写数字人带货爆款文案...", "info");
    setTimeout(() => {
      setSpeech("【爆款降临】各位创作者注意了！Pixelle-Video 终于迎来了史诗级工作台升级！搭载 MiniMax 精致音色与 SDXL AnimateDiff v3 引擎，支持多分支工作流，一键拉满短视频生产品质。抢先体验，颠覆传统视频生产效率！");
      setGeneratingScript(false);
      addToast("带货口播文案自动撰写就绪！已填入文案面板", "success");
    }, 1200);
  };

  const handleGenerate = () => {
    if (!speech.trim()) {
      addToast("口播文案不能为空！请输入数字人演讲脚本。", "error");
      return;
    }

    const taskInput = {
      title,
      tabType: "digital-human",
      workflowId: "bizyair-flux-upscale",
      ttsMode: "minimax",
      voice,
      speed: 1.05,
      minimaxModel: "speech-2.8-turbo",
      bgm: "bgm-tech",
      bgmVolume: 15,
      promptPrefix: `talking digital human anchor, detailed face, speaking realistically, high-fidelity lip sync`,
      scenes: [
        { id: 1, ttsText: speech, visualPrompt: "Talking digital human, realistic details, high fidelity, 4k" }
      ]
    };

    onGenerateTask(taskInput);
  };

  return (
    <div className="space-y-5 animate-fade-in max-w-4xl pb-10">
      {/* Panel header */}
      <div className="bg-[#101114] border border-zinc-900 rounded-md p-3.5">
        <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-0.5">
          数字人口播项目名称 / Project Name
        </label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="bg-transparent border-b border-zinc-800 text-zinc-100 font-medium text-sm w-full py-0.5 focus:outline-none focus:border-amber-500 font-display transition-colors"
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left Avatars Selector */}
        <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <h3 className="text-xs font-semibold text-zinc-400">选择数字人角色模特 / Avatar Model</h3>
          
          <div className="grid grid-cols-1 gap-2.5 max-h-[240px] overflow-y-auto pr-1">
            {avatars.map((av) => (
              <div
                key={av.id}
                onClick={() => setActiveAvatar(av.id)}
                className={`p-2.5 rounded border cursor-pointer flex items-center gap-3 transition-colors ${
                  activeAvatar === av.id
                    ? "bg-[#17181c] border-amber-500 text-zinc-200"
                    : "bg-[#121316] border-zinc-900 text-zinc-400 hover:text-zinc-250"
                }`}
              >
                <img src={av.img} alt={av.name} className="w-11 h-11 object-cover rounded-md border border-zinc-800" />
                <div>
                  <span className="text-xs font-semibold text-zinc-200 block">{av.name}</span>
                  <span className="text-[10px] text-zinc-500 block leading-normal mt-0.5">{av.desc}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Backdrop Type */}
          <div className="space-y-2 pt-2 border-t border-zinc-900">
            <label className="block text-[11px] text-zinc-500 font-medium">配置直播间/口播背景 (Backdrop)</label>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <button
                onClick={() => setBgType("studio")}
                className={`py-1.5 rounded border transition-colors ${
                  bgType === "studio" ? "bg-amber-500/10 border-amber-500/30 text-amber-400" : "bg-[#17181c] border-zinc-800 text-zinc-400"
                }`}
              >
                科技写实影棚
              </button>
              <button
                onClick={() => setBgType("office")}
                className={`py-1.5 rounded border transition-colors ${
                  bgType === "office" ? "bg-amber-500/10 border-amber-500/30 text-amber-400" : "bg-[#17181c] border-zinc-800 text-zinc-400"
                }`}
              >
                简约白领办公室
              </button>
              <button
                onClick={() => setBgType("upload")}
                className={`py-1.5 rounded border transition-colors flex items-center justify-center gap-1 ${
                  bgType === "upload" ? "bg-amber-500/10 border-amber-500/30 text-amber-400" : "bg-[#17181c] border-zinc-800 text-zinc-400"
                }`}
              >
                <Upload className="w-3 h-3" />
                自定义上传
              </button>
            </div>
          </div>
        </div>

        {/* Right speech text editor */}
        <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
          <div className="flex justify-between items-center pb-1">
            <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1">
              <FileText className="w-4 h-4 text-amber-500" />
              口播演说脚本与配音
            </h3>
            <button
              onClick={handleAIGenerateSpeech}
              disabled={generatingScript}
              className="text-[10px] text-amber-500 flex items-center gap-1 hover:underline disabled:opacity-50"
            >
              <Sparkles className="w-3 h-3" />
              AI 撰写爆款文案
            </button>
          </div>

          <div className="space-y-3.5">
            <div>
              <textarea
                value={speech}
                onChange={(e) => setSpeech(e.target.value)}
                placeholder="请输入数字人口播时念出的全部文案..."
                className="w-full h-28 bg-[#17181c] border border-zinc-800 rounded p-2.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 leading-relaxed placeholder-zinc-750"
              />
              <span className="text-[10px] text-zinc-500 font-mono flex justify-end">
                字数估计: {speech.length} 字 | 预计时间: {Math.round(speech.length / 4.2)} 秒
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[10px] text-zinc-500 mb-1">配音音色 / Voice Type</label>
                <select
                  value={voice}
                  onChange={(e) => setVoice(e.target.value)}
                  className="w-full bg-[#17181c] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                >
                  {VOICE_OPTIONS.minimax.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[10px] text-zinc-500 mb-1">背景伴奏微音量</label>
                <select
                  className="w-full bg-[#17181c] border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-300 focus:outline-none"
                  defaultValue="tech"
                >
                  <option value="tech">科技律动 BGM (15% 降噪避让)</option>
                  <option value="epic">无伴奏 (仅唇形配音)</option>
                </select>
              </div>
            </div>

            <div className="bg-[#17181c] p-2 rounded border border-zinc-850 text-[10px] text-zinc-500">
              提示: 数字人口播模式开启后将自动同步口型（Lip-sync 深度学习对其），支持超高清人像超分上色，预计耗时约 40s。
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
          开始渲染口播视频 Generate Digital Actor
        </button>
      </div>
    </div>
  );
};
