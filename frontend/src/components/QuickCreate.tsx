import React, { useState } from "react";
import {
  Sparkles,
  Edit3,
  Layers,
  Music,
  Sliders,
  Volume2,
  Mic2,
  Play,
  FileVideo,
  Eye,
  Loader,
  AlertTriangle,
  Upload,
  Workflow,
  Plus,
  Trash2,
  SquareEqual,
} from "lucide-react";
import { Preset, WorkbenchResources } from "../types";
import { VOICE_OPTIONS } from "../data";

interface QuickCreateProps {
  onGenerateTask: (taskInput: any) => void;
  activePreset: Preset | null;
  onSavePreset: (presetInput: any) => void;
  resources: WorkbenchResources;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

const IMAGE_SIZE_PRESETS = [
  { id: "1024x1024", label: "1:1 正方形", width: 1024, height: 1024 },
  { id: "1024x1536", label: "2:3 竖版", width: 1024, height: 1536 },
  { id: "1536x1024", label: "3:2 横版", width: 1536, height: 1024 },
  { id: "2048x2048", label: "1:1 2K", width: 2048, height: 2048 },
  { id: "2560x1440", label: "16:9 QHD", width: 2560, height: 1440 },
  { id: "1440x2560", label: "9:16 QHD", width: 1440, height: 2560 },
  { id: "2880x2880", label: "1:1 4K", width: 2880, height: 2880 },
  { id: "3840x2160", label: "16:9 4K", width: 3840, height: 2160 },
  { id: "2160x3840", label: "9:16 4K", width: 2160, height: 3840 },
  { id: "custom", label: "自定义", width: 1024, height: 1536 },
];

export const QuickCreate: React.FC<QuickCreateProps> = ({
  onGenerateTask,
  activePreset,
  onSavePreset,
  resources,
  addToast,
}) => {
  // Main states
  const [mode, setMode] = useState<"ai" | "manual" | "batch">("ai");
  const [title, setTitle] = useState("新品发布创意科技短视频");
  
  // AI Creation states
  const [aiTopic, setAiTopic] = useState("探索未来世界的智能机器人生活碎片");
  const [aiSceneCount, setAiSceneCount] = useState(5);
  const [aiLoading, setAiLoading] = useState(false);

  // Manual Creation states (Scenes list)
  const [scenes, setScenes] = useState<Array<{ id: number; ttsText: string; visualPrompt: string }>>([
    { id: 1, ttsText: "这是一个科技感爆棚的高能概念画卷。", visualPrompt: "Cinematic digital art of high-tech lab, warm amber lighting, futuristic, 4k" },
    { id: 2, ttsText: "每一个齿轮的咬合，都是精工美学的体现。", visualPrompt: "Macro close-up of amber golden machine gears interlocking in motion, cinematic depth of field" }
  ]);

  // Batch Creation states
  const [batchInput, setBatchInput] = useState("主题一: 智能机器人在雨夜撑伞\n主题二: 机械宠物狗在客厅嬉戏\n主题三: 未来城市空中飞车速递");
  const [batchCount, setBatchCount] = useState(3);
  const [splitType, setSplitType] = useState<"paragraph" | "line" | "sentence">("line");

  // BGM states
  const [bgm, setBgm] = useState("bgm-none");
  const [volume, setVolume] = useState(30);
  const [playingBgm, setPlayingBgm] = useState<string | null>(null);
  const [audioObj, setAudioObj] = useState<HTMLAudioElement | null>(null);

  // TTS States
  const [ttsMode, setTtsMode] = useState<"edge" | "comfyui" | "minimax">("minimax");
  const [voice, setVoice] = useState("male-qn-qingse");
  const [speed, setSpeed] = useState(1.0);
  const [emotion, setEmotion] = useState("");
  const [minimaxModel, setMinimaxModel] = useState("speech-2.8-turbo");
  const [customAudioFile, setCustomAudioFile] = useState<string | null>(null);
  const [previewingTts, setPreviewingTts] = useState(false);
  const [previewTtsText, setPreviewTtsText] = useState("这是一段 TTS 试听文案，用来检查音色、语速和发音效果。");
  const [previewTtsAudioUrl, setPreviewTtsAudioUrl] = useState<string | null>(null);

  // Layout Template states
  const [viewMode, setViewMode] = useState<"template" | "pure-image">("template");
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [enableMotion, setEnableMotion] = useState(true);
  const [enableSubtitles, setEnableSubtitles] = useState(true);
  const [imageAspectRatio, setImageAspectRatio] = useState("1024x1536");
  const [imageWidth, setImageWidth] = useState(1024);
  const [imageHeight, setImageHeight] = useState(1536);

  // Render Workflow states
  const [workflowId, setWorkflowId] = useState("");
  const [promptPrefix, setPromptPrefix] = useState("masterpiece, best quality, ultra-detailed, photorealistic, cinematic volumetric lighting, warm color palette, amber glow");

  const bgmOptions = resources.bgm;
  const templateOptions = resources.templates;
  const workflowOptions = resources.workflows;

  React.useEffect(() => {
    if (workflowOptions.length === 0) return;
    if (!workflowId || !workflowOptions.some((workflow) => workflow.id === workflowId)) {
      setWorkflowId(workflowOptions[0].id);
    }
  }, [workflowOptions, workflowId]);

  React.useEffect(() => {
    if (templateOptions.length === 0) return;
    const preferredTemplate =
      templateOptions.find((template) => template.id === "1080x1920/image_default.html") ||
      templateOptions[0];
    if (!selectedTemplate || !templateOptions.some((template) => template.id === selectedTemplate)) {
      setSelectedTemplate(preferredTemplate.id);
    }
  }, [templateOptions, selectedTemplate]);

  React.useEffect(() => {
    if (bgmOptions.length === 0) return;
    if (!bgmOptions.some((item) => item.id === bgm)) {
      setBgm("bgm-none");
    }
  }, [bgmOptions, bgm]);

  // BGM listen toggle
  const toggleBgmListen = (selectedBgmId: string) => {
    if (playingBgm === selectedBgmId) {
      if (audioObj) {
        audioObj.pause();
        audioObj.currentTime = 0;
      }
      setPlayingBgm(null);
      addToast("伴奏试听已暂停", "info");
      return;
    }

    const matchedBgm = bgmOptions.find((b) => b.id === selectedBgmId);
    if (!matchedBgm || !matchedBgm.src) {
      addToast("无法试听此类型的音频配置", "error");
      return;
    }

    if (audioObj) {
      audioObj.pause();
    }

    const newAudio = new Audio(matchedBgm.src);
    newAudio.volume = volume / 100;
    newAudio.loop = true;
    newAudio.play();
    setAudioObj(newAudio);
    setPlayingBgm(selectedBgmId);
    addToast(`开始试听: ${matchedBgm.name}`, "success");
  };

  const audioPathToUrl = (audioPath: string) => {
    if (/^https?:\/\//.test(audioPath)) return audioPath;
    return `/api/files/${audioPath}`;
  };

  const applyImageSizePreset = (presetId: string) => {
    setImageAspectRatio(presetId);
    const preset = IMAGE_SIZE_PRESETS.find((item) => item.id === presetId);
    if (preset && preset.id !== "custom") {
      setImageWidth(preset.width);
      setImageHeight(preset.height);
    }
  };

  // TTS Speak Preview
  const handlePreviewTts = async () => {
    if (!previewTtsText.trim()) {
      addToast("请先填写试听文案。", "error");
      return;
    }

    setPreviewingTts(true);
    setPreviewTtsAudioUrl(null);
    const previewInferenceMode = ttsMode === "edge" ? "local" : ttsMode;
    const previewServiceName = ttsMode === "minimax" ? "MiniMax" : ttsMode === "comfyui" ? "ComfyUI" : "Edge";
    addToast(`正在生成 ${previewServiceName} TTS 试听音频...`, "info");

    try {
      const response = await fetch("/api/tts/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: previewTtsText,
          inference_mode: previewInferenceMode,
          voice_id: voice,
          speed,
          minimax_model: ttsMode === "minimax" ? minimaxModel : undefined,
          minimax_emotion: ttsMode === "minimax" ? emotion || undefined : undefined,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.detail || data.error || `${previewServiceName} TTS 试听生成失败。`);
      }
      const audioUrl = audioPathToUrl(data.audio_path);
      setPreviewTtsAudioUrl(audioUrl);
      addToast(`${previewServiceName} TTS 试听音频已生成。`, "success");

      const audio = new Audio(audioUrl);
      audio.play().catch(() => {
        addToast("试听音频已生成，请点击播放器播放。", "info");
      });
    } catch (err: any) {
      addToast(err.message || "TTS 试听生成失败。", "error");
    } finally {
      setPreviewingTts(false);
    }
  };

  // Apply Preset
  React.useEffect(() => {
    if (activePreset) {
      setTtsMode(activePreset.ttsMode);
      setVoice(activePreset.voice);
      setSpeed(activePreset.speed);
      setWorkflowId(activePreset.workflow);
      setBgm(activePreset.bgm);
      setVolume(activePreset.bgmVolume);
      setPromptPrefix(activePreset.promptPrefix);
      setSplitType(activePreset.splitType);
      if (activePreset.template) setSelectedTemplate(activePreset.template);
      if (activePreset.viewMode) setViewMode(activePreset.viewMode);
      if (activePreset.enableMotion !== undefined) setEnableMotion(activePreset.enableMotion);
      if (activePreset.enableSubtitles !== undefined) setEnableSubtitles(activePreset.enableSubtitles);
      setMinimaxModel(activePreset.minimaxModel || "speech-2.8-turbo");
      setEmotion(activePreset.emotion || "");
      addToast(`已成功应用预设: ${activePreset.name}`, "success");
    }
  }, [activePreset]);

  // AI Generation fetch via Gemini API route
  const handleAIGenerateScript = async () => {
    if (!aiTopic.trim()) {
      addToast("请输入创作主题，以便 AI 生成分镜脚本", "error");
      return;
    }
    setAiLoading(true);
    addToast("大模型正在深度构思分镜逻辑，请稍候...", "info");

    try {
      const response = await fetch("/api/generate-script", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: aiTopic,
          sceneCount: aiSceneCount,
          splitType
        }),
      });
      const resData = await response.json();
      if (response.ok && resData.success) {
        // Transform incoming data into scenes list
        const generated = resData.data.map((item: any) => ({
          id: item.id,
          ttsText: item.ttsText,
          visualPrompt: item.visualPrompt,
        }));
        setScenes(generated);
        setMode("manual"); // switch to manual scene editor so user can review and edit
        addToast(`AI 分镜脚本生成就绪！已帮您切分成 ${generated.length} 个分镜，您可直接在下方编辑或点击渲染。`, "success");
      } else {
        addToast(resData.detail || resData.error || "脚本构思异常，请检查 LLM 设置。", "error");
      }
    } catch (err: any) {
      addToast("连接服务器超时，请确保 dev 服务器就绪。", "error");
    } finally {
      setAiLoading(false);
    }
  };

  // Scene CRUD
  const addScene = () => {
    const newId = scenes.length > 0 ? Math.max(...scenes.map((s) => s.id)) + 1 : 1;
    setScenes([...scenes, { id: newId, ttsText: "", visualPrompt: "" }]);
  };

  const removeScene = (id: number) => {
    setScenes(scenes.filter((s) => s.id !== id));
  };

  const updateScene = (id: number, key: "ttsText" | "visualPrompt", value: string) => {
    setScenes(scenes.map((s) => (s.id === id ? { ...s, [key]: value } : s)));
  };

  // Trigger main generator callback
  const handleTriggerRender = () => {
    if (!title.trim()) {
      addToast("请先指定视频生产任务标题！", "error");
      return;
    }

    if (mode === "manual" && scenes.some((s) => !s.ttsText.trim())) {
      addToast("检测到未填写的旁白文本，请完善每一个分镜！", "error");
      return;
    }

    const taskInput = {
      title,
      tabType: "quick-create",
      workflowId,
      ttsMode,
      voice,
      speed,
      minimaxModel,
      emotion: emotion || undefined,
      mediaWidth: imageWidth,
      mediaHeight: imageHeight,
      bgm,
      bgmVolume: volume,
      promptPrefix,
      templateId: selectedTemplate,
      viewMode,
      enableMotion,
      enableSubtitles,
      splitType,
      scenes: mode === "manual" ? scenes : [
        { id: 1, ttsText: aiTopic, visualPrompt: "Creative visualization of: " + aiTopic }
      ]
    };

    onGenerateTask(taskInput);
  };

  // Preset Save Callback
  const handleTriggerSavePreset = () => {
    const presetData = {
      name: `预设-${title.substring(0, 8)}`,
      ttsMode,
      voice,
      speed,
      workflow: workflowId,
      bgm,
      bgmVolume: volume,
      promptPrefix,
      splitType,
      template: selectedTemplate,
      viewMode,
      enableMotion,
      enableSubtitles,
      minimaxModel,
      emotion: emotion || undefined,
      mediaWidth: imageWidth,
      mediaHeight: imageHeight
    };
    onSavePreset(presetData);
  };

  const currentWorkflow = workflowOptions.find((w) => w.id === workflowId);

  return (
    <div className="space-y-6 animate-fade-in max-w-4xl pb-10">
      {/* Task Header Title */}
      <div className="bg-[#101114] border border-zinc-900 rounded-md p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex-1">
          <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-0.5">
            当前生产项目名称 / Project Title
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="bg-transparent border-b border-zinc-800 text-zinc-100 font-medium text-sm w-full py-0.5 focus:outline-none focus:border-amber-500 font-display transition-colors"
          />
        </div>
        <button
          onClick={handleTriggerSavePreset}
          className="px-3 py-1.5 text-xs text-amber-500 border border-amber-500/20 hover:border-amber-500/40 bg-amber-500/5 hover:bg-amber-500/10 rounded font-medium flex items-center gap-1 flex-shrink-0 transition-colors"
        >
          保存为常用预设
        </button>
      </div>

      {/* 1. Creative Mode Tab Switches */}
      <div className="space-y-3">
        <label className="block text-xs font-semibold text-zinc-400">选择内容源创作模式</label>
        <div className="grid grid-cols-3 gap-2 p-1 bg-[#101114] border border-zinc-900 rounded-md max-w-lg">
          <button
            onClick={() => setMode("ai")}
            className={`flex items-center justify-center gap-1.5 py-1.5 text-xs rounded transition-all ${
              mode === "ai"
                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20 font-semibold"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            AI 创作 (一键脚本)
          </button>
          <button
            onClick={() => setMode("manual")}
            className={`flex items-center justify-center gap-1.5 py-1.5 text-xs rounded transition-all ${
              mode === "manual"
                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20 font-semibold"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Edit3 className="w-3.5 h-3.5" />
            自行创作 (分镜编辑)
          </button>
          <button
            onClick={() => setMode("batch")}
            className={`flex items-center justify-center gap-1.5 py-1.5 text-xs rounded transition-all ${
              mode === "batch"
                ? "bg-amber-500/10 text-amber-400 border border-amber-500/20 font-semibold"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            批量生成 (多主题)
          </button>
        </div>
      </div>

      {/* 2. Content Input panel */}
      <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
        {mode === "ai" && (
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">输入创作主题 / Prompt Idea</label>
              <textarea
                placeholder="例如: 智能机器人在雨夜的霓虹小巷穿梭，极具颗粒感写实，带有温暖孤独色彩的科幻故事。"
                value={aiTopic}
                onChange={(e) => setAiTopic(e.target.value)}
                className="w-full h-24 bg-[#17181c] border border-zinc-800 rounded p-2.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 placeholder-zinc-650"
              />
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="font-medium text-zinc-400">分镜切片数量: {aiSceneCount} 帧</span>
                  <span className="text-[10px] text-zinc-500 font-mono">建议 5-10 帧</span>
                </div>
                <input
                  type="range"
                  min="3"
                  max="30"
                  step="1"
                  value={aiSceneCount}
                  onChange={(e) => setAiSceneCount(parseInt(e.target.value))}
                  className="w-full accent-amber-500 cursor-pointer h-1.5 bg-zinc-800 rounded"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">切分规则方式</label>
                <select
                  value={splitType}
                  onChange={(e: any) => setSplitType(e.target.value)}
                  className="w-full bg-[#17181c] border border-zinc-800 rounded px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                >
                  <option value="paragraph">按段落智能切分</option>
                  <option value="line">按每一行/换行切分</option>
                  <option value="sentence">按句子标点切分</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end pt-2 border-t border-zinc-900">
              <button
                onClick={handleAIGenerateScript}
                disabled={aiLoading}
                className="px-4 py-1.5 bg-amber-500 hover:bg-amber-400 disabled:bg-zinc-800 text-black font-semibold text-xs rounded shadow-md flex items-center gap-1.5 transition-colors"
              >
                {aiLoading ? (
                  <>
                    <Loader className="w-3.5 h-3.5 animate-spin" />
                    AI 正在构建智能分镜脚本...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5 text-black" />
                    生成 AI 分镜脚本
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {mode === "manual" && (
          <div className="space-y-4">
            <div className="flex justify-between items-center pb-2 border-b border-zinc-900">
              <span className="text-xs font-medium text-zinc-300 flex items-center gap-1">
                分镜列表编辑器 (精细化定制旁白与画面提示词)
              </span>
              <button
                onClick={addScene}
                className="px-2 py-1 bg-[#17181c] hover:bg-zinc-800 text-zinc-300 border border-zinc-800 rounded text-[11px] font-medium flex items-center gap-1 transition-colors"
              >
                <Plus className="w-3 h-3 text-amber-500" />
                新增分镜
              </button>
            </div>

            <div className="space-y-3 max-h-[360px] overflow-y-auto pr-1">
              {scenes.map((scene, idx) => (
                <div
                  key={scene.id}
                  className="bg-[#17181c] border border-zinc-850 p-3 rounded flex items-start gap-3 relative hover:border-zinc-800 group"
                >
                  <div className="w-6 h-6 rounded bg-zinc-800/80 text-zinc-400 text-xs font-bold flex items-center justify-center font-mono mt-1">
                    {idx + 1}
                  </div>

                  <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                        分镜配音旁白 (TTS Text)
                      </label>
                      <input
                        type="text"
                        placeholder="请输入本帧念出来的配音旁白文案..."
                        value={scene.ttsText}
                        onChange={(e) => updateScene(scene.id, "ttsText", e.target.value)}
                        className="w-full bg-[#101114] border border-zinc-900 rounded px-2 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                      />
                    </div>
                    <div>
                      <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                        画面视觉绘图 Prompt (英文最佳)
                      </label>
                      <input
                        type="text"
                        placeholder="请输入本帧的画面提示词，留空将沿用主题..."
                        value={scene.visualPrompt}
                        onChange={(e) => updateScene(scene.id, "visualPrompt", e.target.value)}
                        className="w-full bg-[#101114] border border-zinc-900 rounded px-2 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                      />
                    </div>
                  </div>

                  <button
                    onClick={() => removeScene(scene.id)}
                    className="p-1.5 hover:bg-rose-950/20 text-zinc-650 hover:text-rose-400 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                    title="删除此分镜"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {mode === "batch" && (
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1.5">
                输入多个主题 (每个主题将独立渲染一个短视频)
              </label>
              <textarea
                value={batchInput}
                onChange={(e) => {
                  setBatchInput(e.target.value);
                  const count = e.target.value.split("\n").filter((l) => l.trim() !== "").length;
                  setBatchCount(count);
                }}
                placeholder="一行一个主题进行配置..."
                className="w-full h-32 bg-[#17181c] border border-zinc-800 rounded p-2.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 font-mono placeholder-zinc-700"
              />
            </div>
            
            <div className="bg-amber-550/5 border border-amber-500/10 p-3 rounded text-xs text-zinc-400 flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                系统检测到 <strong>{batchCount}</strong> 个合法待渲染主题。
              </span>
              <span className="text-[10px] font-mono uppercase tracking-wider bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded">
                批量生成并发
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 3. TTS Voice Synthesis & BGM Mixing */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* TTS Panel */}
        <div className="bg-[#101114] border border-zinc-900 p-4 rounded-lg space-y-4">
          <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
            <Mic2 className="w-4 h-4 text-amber-500" />
            配音合成 TTS 引擎
          </h3>

          <div className="grid grid-cols-3 gap-1 p-0.5 bg-[#17181c] border border-zinc-850 rounded">
            {(["edge", "comfyui", "minimax"] as const).map((opt) => (
              <button
                key={opt}
                onClick={() => {
                  setTtsMode(opt);
                  setVoice(VOICE_OPTIONS[opt][0].id);
                }}
                className={`py-1 text-[10px] rounded uppercase font-semibold text-center transition-all ${
                  ttsMode === opt ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {opt === "edge" && "Edge 极速"}
                {opt === "comfyui" && "Comfy 克隆"}
                {opt === "minimax" && "MiniMax 精致"}
              </button>
            ))}
          </div>

          <div className="space-y-3 pt-1">
            {/* Voices list */}
            <div>
              <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                选择合成音色及风格 / Voice Model
              </label>
              <select
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                className="w-full bg-[#17181c] border border-zinc-800 rounded px-2 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
              >
                {VOICE_OPTIONS[ttsMode].map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Sub options if MiniMax */}
            {ttsMode === "minimax" && (
              <div className="grid grid-cols-2 gap-2 bg-[#17181c] p-2 rounded border border-zinc-850">
                <div>
                  <label className="block text-[9px] text-zinc-500 mb-0.5">声音情感 / Emotion</label>
                  <select
                    value={emotion}
                    onChange={(e) => setEmotion(e.target.value)}
                    className="w-full bg-[#101114] border border-zinc-900 rounded px-1.5 py-1 text-[11px] text-zinc-300 focus:outline-none focus:border-amber-500"
                  >
                    <option value="">自动匹配 (Auto)</option>
                    <option value="happy">欢快愉悦 (Happy)</option>
                    <option value="sad">悲伤低落 (Sad)</option>
                    <option value="angry">严厉愤怒 (Angry)</option>
                    <option value="fearful">紧张害怕 (Fearful)</option>
                    <option value="disgusted">厌恶嫌弃 (Disgusted)</option>
                    <option value="surprised">惊讶意外 (Surprised)</option>
                    <option value="calm">平静克制 (Calm)</option>
                    <option value="fluent">流畅自然 (Fluent)</option>
                    <option value="whisper">低声耳语 (Whisper)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[9px] text-zinc-500 mb-0.5">MiniMax 基座模型</label>
                  <select
                    value={minimaxModel}
                    onChange={(e) => setMinimaxModel(e.target.value)}
                    className="w-full bg-[#101114] border border-zinc-900 rounded px-1.5 py-1 text-[11px] text-zinc-300 focus:outline-none focus:border-amber-500"
                  >
                    <option value="speech-2.8-turbo">speech-2.8-turbo</option>
                    <option value="speech-2.8-hd">speech-2.8-hd</option>
                    <option value="speech-2.6-turbo">speech-2.6-turbo</option>
                    <option value="speech-2.6-hd">speech-2.6-hd</option>
                    <option value="speech-02-turbo">speech-02-turbo</option>
                    <option value="speech-02-hd">speech-02-hd</option>
                  </select>
                </div>
              </div>
            )}

            {/* Audio Upload if ComfyUI clone */}
            {ttsMode === "comfyui" && (
              <div className="bg-[#17181c] p-2.5 rounded border border-zinc-850 space-y-2">
                <span className="text-[10px] text-zinc-400 font-medium block">
                  上传您要克隆的目标参考音频 (10MB以内的 MP3/WAV, 最好 5s-30s):
                </span>
                <div className="border border-dashed border-zinc-800 rounded flex flex-col items-center justify-center p-3 hover:border-amber-500/40 cursor-pointer">
                  <Upload className="w-5 h-5 text-zinc-600 mb-1.5" />
                  <span className="text-[10px] text-zinc-500">点击上传或将文件拖拽于此</span>
                </div>
              </div>
            )}

            <div className="bg-[#17181c] p-2.5 rounded border border-zinc-850 space-y-2">
              <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider">
                试听文案 / Preview Script
              </label>
              <textarea
                value={previewTtsText}
                onChange={(e) => setPreviewTtsText(e.target.value)}
                rows={3}
                className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-2 text-xs text-zinc-300 leading-relaxed resize-none focus:outline-none focus:border-amber-500"
                placeholder="输入一段用于试听配音效果的文案"
              />
              {previewTtsAudioUrl && (
                <audio
                  src={previewTtsAudioUrl}
                  controls
                  className="w-full h-8"
                />
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center pt-2">
              <div>
                <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                  <span>语速调节: {speed}x</span>
                  <span>建议 0.9 - 1.2</span>
                </div>
                <input
                  type="range"
                  min="0.8"
                  max="1.5"
                  step="0.05"
                  value={speed}
                  onChange={(e) => setSpeed(parseFloat(e.target.value))}
                  className="w-full accent-amber-500 h-1 cursor-pointer bg-zinc-850 rounded"
                />
              </div>

              <div className="flex justify-end">
                <button
                  onClick={handlePreviewTts}
                  disabled={previewingTts}
                  className="px-2.5 py-1 bg-zinc-800 text-zinc-300 hover:text-white rounded border border-zinc-750 hover:border-zinc-650 text-xs font-medium flex items-center gap-1 transition-colors"
                >
                  {previewingTts ? <Loader className="w-3 h-3 animate-spin text-amber-500" /> : <Play className="w-3 h-3 text-amber-500" />}
                  试听 TTS 语音
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* BGM Panel */}
        <div className="bg-[#101114] border border-zinc-900 p-4 rounded-lg space-y-4">
          <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
            <Music className="w-4 h-4 text-amber-500" />
            背景伴奏 BGM 混音配乐
          </h3>

          <div className="space-y-3">
            <div>
              <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                选择背景配乐 / Background Audio
              </label>
              <div className="space-y-1.5">
                {bgmOptions.map((b) => (
                  <div
                    key={b.id}
                    className={`flex items-center justify-between p-2 rounded border text-xs transition-colors ${
                      bgm === b.id
                        ? "bg-[#17181c] border-amber-500/30 text-amber-400"
                        : "bg-[#121316] border-zinc-900 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    <label className="flex items-center gap-2 cursor-pointer flex-1">
                      <input
                        type="radio"
                        name="bgmRadio"
                        checked={bgm === b.id}
                        onChange={() => setBgm(b.id)}
                        className="accent-amber-500"
                      />
                      <div className="truncate">
                        <span className="font-medium text-zinc-300 block text-[11px] truncate">{b.name}</span>
                        {b.author && <span className="text-[9px] text-zinc-500">{b.author} • {b.duration}</span>}
                      </div>
                    </label>

                    {b.src && (
                      <button
                        onClick={() => toggleBgmListen(b.id)}
                        className={`p-1 rounded text-[10px] border flex items-center gap-0.5 ${
                          playingBgm === b.id
                            ? "bg-amber-500/10 border-amber-500/20 text-amber-400"
                            : "bg-[#17181c] border-zinc-800 text-zinc-400 hover:text-zinc-200"
                        }`}
                      >
                        <Volume2 className="w-3 h-3" />
                        {playingBgm === b.id ? "暂停" : "试听"}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-2">
              <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                <span>配乐音量: {volume}%</span>
                <span>主旁白自动避让降噪</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                value={volume}
                onChange={(e) => setVolume(parseInt(e.target.value))}
                className="w-full accent-amber-500 h-1 cursor-pointer bg-zinc-850 rounded"
              />
            </div>
          </div>
        </div>
      </div>

      {/* 4. Canvas Mode & Templates */}
      <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
        <div className="flex justify-between items-center pb-2 border-b border-zinc-900">
          <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
            <FileVideo className="w-4 h-4 text-amber-500" />
            分镜画风及画面渲染模式
          </h3>

          <div className="flex gap-1.5 bg-[#17181c] border border-zinc-850 p-0.5 rounded">
            <button
              onClick={() => setViewMode("template")}
              className={`px-2 py-0.5 text-[10px] rounded transition-all ${
                viewMode === "template" ? "bg-amber-500/10 text-amber-400 font-medium" : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              分镜模板渲染
            </button>
            <button
              onClick={() => setViewMode("pure-image")}
              className={`px-2 py-0.5 text-[10px] rounded transition-all ${
                viewMode === "pure-image" ? "bg-amber-500/10 text-amber-400 font-medium" : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              图片运动生成
            </button>
          </div>
        </div>

        {viewMode === "template" ? (
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-h-[460px] overflow-y-auto pr-1">
              {templateOptions.length === 0 && (
                <div className="sm:col-span-3 border border-dashed border-zinc-800 rounded p-6 text-center text-xs text-zinc-500">
                  正在等待后端模板资源...
                </div>
              )}
              {templateOptions.map((t) => (
                <div
                  key={t.id}
                  onClick={() => setSelectedTemplate(t.id)}
                  className={`border rounded overflow-hidden cursor-pointer bg-[#17181c] transition-all hover:scale-[1.01] ${
                    selectedTemplate === t.id
                      ? "border-amber-500 shadow-md shadow-amber-500/5"
                      : "border-zinc-850 opacity-60 hover:opacity-100"
                  }`}
                >
                  <div className="w-full h-24 bg-[#0c0d10] border-b border-zinc-900 flex items-center justify-center">
                    <div
                      className={`border border-amber-500/35 bg-amber-500/10 shadow-inner shadow-amber-500/5 ${
                        t.orientation === "landscape"
                          ? "w-24 h-14"
                          : t.orientation === "square"
                            ? "w-16 h-16"
                            : "w-12 h-20"
                      }`}
                    />
                  </div>
                  <div className="p-2 space-y-1">
                    <span className="text-[11px] font-semibold text-zinc-200 block truncate">{t.name}</span>
                    <span className="text-[9px] text-zinc-500 block uppercase font-mono tracking-wider">
                      {t.type} / {t.dimensions}
                    </span>
                    <p className="text-[10px] text-zinc-400 line-clamp-2 leading-relaxed mt-1">
                      {t.desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="p-3 bg-[#17181c] border border-zinc-850 rounded-md space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                  图片比例 / Size
                </label>
                <select
                  value={imageAspectRatio}
                  onChange={(e) => applyImageSizePreset(e.target.value)}
                  className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                >
                  {IMAGE_SIZE_PRESETS.map((preset) => (
                    <option key={preset.id} value={preset.id}>
                      {preset.label} · {preset.id === "custom" ? "手动输入" : `${preset.width}x${preset.height}`}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                  宽度 / Width
                </label>
                <input
                  type="number"
                  min="512"
                  max="3840"
                  step="16"
                  value={imageWidth}
                  onChange={(e) => {
                    setImageAspectRatio("custom");
                    setImageWidth(parseInt(e.target.value || "1024"));
                  }}
                  className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                />
              </div>
              <div>
                <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
                  高度 / Height
                </label>
                <input
                  type="number"
                  min="512"
                  max="3840"
                  step="16"
                  value={imageHeight}
                  onChange={(e) => {
                    setImageAspectRatio("custom");
                    setImageHeight(parseInt(e.target.value || "1536"));
                  }}
                  className="w-full bg-[#101114] border border-zinc-900 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="flex items-center gap-3 cursor-pointer p-1">
              <input
                type="checkbox"
                checked={enableMotion}
                onChange={(e) => setEnableMotion(e.target.checked)}
                className="accent-amber-500 w-4 h-4 rounded"
              />
              <div>
                <span className="text-xs font-semibold text-zinc-300 block">开启镜头 3D 微动效果</span>
                <span className="text-[10px] text-zinc-500 block">通过深度估算添加摄像机推拉摇移</span>
              </div>
            </label>

            <label className="flex items-center gap-3 cursor-pointer p-1">
              <input
                type="checkbox"
                checked={enableSubtitles}
                onChange={(e) => setEnableSubtitles(e.target.checked)}
                className="accent-amber-500 w-4 h-4 rounded"
              />
              <div>
                <span className="text-xs font-semibold text-zinc-300 block">添加高清晰中文字幕</span>
                <span className="text-[10px] text-zinc-500 block">自动对其 TTS 脚本音频进行叠字渲染</span>
              </div>
            </label>
            </div>
          </div>
        )}
      </div>

      {/* 5. ComfyUI Media Workflows selections */}
      <div className="bg-[#101114] border border-zinc-900 rounded-lg p-4 space-y-4">
        <h3 className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
          <Workflow className="w-4 h-4 text-amber-500" />
          后台渲染 Workflows 源工作流配置
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-h-[360px] overflow-y-auto pr-1">
          {workflowOptions.length === 0 && (
            <div className="sm:col-span-3 border border-dashed border-zinc-800 rounded p-6 text-center text-xs text-zinc-500">
              正在等待后端工作流资源...
            </div>
          )}
          {workflowOptions.map((wf) => (
            <div
              key={wf.id}
              onClick={() => setWorkflowId(wf.id)}
              className={`p-3 rounded border text-left cursor-pointer transition-colors ${
                workflowId === wf.id
                  ? "bg-[#17181c] border-amber-500/30 text-amber-400"
                  : "bg-[#121316] border-zinc-900 text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <div className="flex justify-between items-start mb-1">
                <span className="text-[11px] font-semibold text-zinc-200 block truncate">{wf.name}</span>
                <span className="text-[8px] bg-amber-500/10 text-amber-400 border border-amber-500/20 px-1 py-0.5 rounded font-mono">
                  {wf.source}
                </span>
              </div>
              <span className="text-[9px] font-mono text-zinc-500 block">类型: {wf.type} | {wf.resolution}</span>
              <p className="text-[10px] text-zinc-400 leading-relaxed mt-2 line-clamp-2">
                {wf.desc}
              </p>
            </div>
          ))}
        </div>

        <div>
          <label className="block text-[10px] text-zinc-500 font-mono uppercase tracking-wider mb-1">
            底模提示词前缀固定参数 / Prompt Prefix
          </label>
          <input
            type="text"
            value={promptPrefix}
            onChange={(e) => setPromptPrefix(e.target.value)}
            className="w-full bg-[#17181c] border border-zinc-800 rounded px-2.5 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500 font-mono"
          />
        </div>
      </div>

      {/* Primary Action Button */}
      <div className="flex justify-end pt-2">
        <button
          onClick={handleTriggerRender}
          className="px-6 py-2.5 bg-amber-500 text-black font-semibold text-xs rounded hover:bg-amber-400 shadow-xl shadow-amber-500/10 flex items-center gap-2 transition-transform active:scale-[0.99]"
        >
          <Sparkles className="w-4 h-4 text-black" />
          立即开始生成视频 Generate Video
        </button>
      </div>
    </div>
  );
};
