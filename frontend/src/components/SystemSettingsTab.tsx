import React, { useState } from "react";
import { Server, Database, Key, CheckCircle, RefreshCw, Cpu, HelpCircle } from "lucide-react";
import { SystemSettings } from "../types";

interface SystemSettingsProps {
  settings: SystemSettings;
  onUpdateSettings: (newSettings: SystemSettings) => void;
  onSaveSettings: (newSettings: SystemSettings) => void | Promise<void>;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

export const SystemSettingsTab: React.FC<SystemSettingsProps> = ({
  settings,
  onUpdateSettings,
  onSaveSettings,
  addToast,
}) => {
  const [testingService, setTestingService] = useState<string | null>(null);

  const providerDefaults = {
    gemini: { model: "gemini-3.5-flash", baseUrl: "" },
    deepseek: { model: "deepseek-v4-flash", baseUrl: "https://api.deepseek.com" },
    openai: { model: "gpt-4o-mini", baseUrl: "https://api.openai.com/v1" },
    anthropic: { model: "claude-sonnet-4-5", baseUrl: "https://api.anthropic.com/v1/" },
  };

  const handleFieldChange = (section: keyof SystemSettings, field: string, value: any) => {
    const updated = { ...settings };
    if (section === "llm") {
      updated.llm = { ...updated.llm, [field]: value };
    } else if (section === "imageGeneration") {
      updated.imageGeneration = { ...updated.imageGeneration, [field]: value };
    } else if (section === "comfy") {
      updated.comfy = { ...updated.comfy, [field]: value };
    } else if (section === "runninghub") {
      updated.runninghub = { ...updated.runninghub, [field]: value };
    } else {
      (updated as any)[section] = value;
    }
    onUpdateSettings(updated);
  };

  const handleProviderChange = (provider: SystemSettings["llm"]["provider"]) => {
    const defaults = providerDefaults[provider];
    onUpdateSettings({
      ...settings,
      llm: {
        ...settings.llm,
        provider,
        model: defaults.model,
        baseUrl: defaults.baseUrl,
      },
    });
  };

  const testConnection = async (service: string, payload: any) => {
    setTestingService(service);
    try {
      const res = await fetch("/api/test-connection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service, config: payload }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        addToast(data.message || "连接测试成功！", "success");
        if (service === "llm") {
          await onSaveSettings(settings);
        }
      } else {
        addToast(data.detail || data.error || data.message || "连接测试失败，请检查配置。", "error");
      }
    } catch (err: any) {
      addToast(err.message || "网络请求异常，无法连接服务器。", "error");
    } finally {
      setTestingService(null);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl animate-fade-in">
      <div className="flex flex-col gap-1 border-b border-zinc-800 pb-4">
        <h2 className="text-lg font-semibold text-zinc-100 flex items-center gap-2 font-display">
          <Database className="w-5 h-5 text-amber-500" />
          系统连接配置
        </h2>
        <p className="text-xs text-zinc-400">
          配置底层大模型 (LLM)、ComfyUI、RunningHub 等云端算力节点。设置将保存在本次会话中。
        </p>
      </div>

      {/* 1. LLM Configurations */}
      <div className="bg-[#101114] border border-zinc-800 p-4 rounded-lg space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="text-sm font-medium text-zinc-200 flex items-center gap-2 font-display">
            <Cpu className="w-4 h-4 text-amber-500" />
            LLM 语言大模型设置 (脚本生成)
          </h3>
          <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 rounded">
            推荐使用 Gemini 3.5
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">供应商 Preset</label>
            <select
              value={settings.llm.provider}
              onChange={(e) => handleProviderChange(e.target.value as SystemSettings["llm"]["provider"])}
              className="w-full bg-[#17181c] border border-zinc-800 rounded px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
            >
              <option value="gemini">Google Gemini AI</option>
              <option value="deepseek">DeepSeek API</option>
              <option value="openai">OpenAI GPT-4</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">模型型号 Select</label>
            <select
              value={settings.llm.model}
              onChange={(e) => handleFieldChange("llm", "model", e.target.value)}
              className="w-full bg-[#17181c] border border-zinc-800 rounded px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
            >
              {settings.llm.provider === "gemini" && (
                <>
                  <option value="gemini-3.5-flash">gemini-3.5-flash (默认高性价比)</option>
                  <option value="gemini-3.1-pro-preview">gemini-3.1-pro-preview (高精度)</option>
                </>
              )}
              {settings.llm.provider === "deepseek" && (
                <>
                  <option value="deepseek-v4-pro">deepseek-v4-pro</option>
                  <option value="deepseek-v4-flash">deepseek-v4-flash</option>
                </>
              )}
              {settings.llm.provider === "openai" && (
                <>
                  <option value="gpt-4o">gpt-4o</option>
                  <option value="gpt-4o-mini">gpt-4o-mini</option>
                </>
              )}
            </select>
          </div>

          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-zinc-400 mb-1">API Key</label>
            <div className="relative">
              <input
                type="password"
                placeholder={settings.llm.provider === "gemini" ? "已自动检测系统注入的 GEMINI_API_KEY" : "请输入 API Key"}
                value={settings.llm.apiKey}
                onChange={(e) => handleFieldChange("llm", "apiKey", e.target.value)}
                className="w-full bg-[#17181c] border border-zinc-800 rounded pl-8 pr-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
              />
              <Key className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-2.5" />
            </div>
          </div>

          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-zinc-400 mb-1">Base URL (API 代理地址)</label>
            <input
              type="text"
              placeholder="https://api.github.com/..."
              value={settings.llm.baseUrl}
              onChange={(e) => handleFieldChange("llm", "baseUrl", e.target.value)}
              className="w-full bg-[#17181c] border border-zinc-800 rounded px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
            />
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <button
            onClick={() => testConnection("llm", settings.llm)}
            disabled={testingService !== null}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border border-zinc-800 bg-[#17181c] hover:bg-zinc-800 text-zinc-300 transition-colors disabled:opacity-50"
          >
            {testingService === "llm" ? (
              <RefreshCw className="w-3 h-3 animate-spin" />
            ) : (
              <Server className="w-3 h-3 text-amber-500" />
            )}
            测试 LLM 连接
          </button>
        </div>
      </div>

      {/* 2. Image Generation API */}
      <div className="bg-[#101114] border border-zinc-800 p-4 rounded-lg space-y-4">
        <div className="flex justify-between items-center">
          <h3 className="text-sm font-medium text-zinc-200 flex items-center gap-2 font-display">
            <Cpu className="w-4 h-4 text-amber-500" />
            图片生成模型设置
          </h3>
          <span className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 px-1.5 py-0.5 rounded">
            OpenAI Images 兼容
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="md:col-span-2">
            <label className="block text-xs font-medium text-zinc-400 mb-1">Base URL</label>
            <input
              type="text"
              placeholder="https://img-cn.65535.space/v1"
              value={settings.imageGeneration.baseUrl}
              onChange={(e) => handleFieldChange("imageGeneration", "baseUrl", e.target.value)}
              className="w-full bg-[#17181c] border border-zinc-800 rounded px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">API Key</label>
            <input
              type="password"
              placeholder="请输入图片生成 API Key"
              value={settings.imageGeneration.apiKey}
              onChange={(e) => handleFieldChange("imageGeneration", "apiKey", e.target.value)}
              className="w-full bg-[#17181c] border border-zinc-800 rounded px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">Model</label>
            <input
              type="text"
              placeholder="gpt-image-2"
              value={settings.imageGeneration.model}
              onChange={(e) => handleFieldChange("imageGeneration", "model", e.target.value)}
              className="w-full bg-[#17181c] border border-zinc-800 rounded px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
            />
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <button
            onClick={() => testConnection("image_generation", settings.imageGeneration)}
            disabled={testingService !== null}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border border-zinc-800 bg-[#17181c] hover:bg-zinc-800 text-zinc-300 transition-colors disabled:opacity-50"
          >
            {testingService === "image_generation" ? (
              <RefreshCw className="w-3 h-3 animate-spin" />
            ) : (
              <Server className="w-3 h-3 text-amber-500" />
            )}
            测试图片生成配置
          </button>
        </div>
      </div>

      {/* 3. ComfyUI Local Settings */}
      <div className="bg-[#101114] border border-zinc-800 p-4 rounded-lg space-y-4">
        <h3 className="text-sm font-medium text-zinc-200 flex items-center gap-2 font-display">
          <Cpu className="w-4 h-4 text-amber-500" />
          ComfyUI 本地服务端配置
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">ComfyUI Web API 地址</label>
            <input
              type="text"
              value={settings.comfy.url}
              onChange={(e) => handleFieldChange("comfy", "url", e.target.value)}
              className="w-full bg-[#17181c] border border-zinc-800 rounded px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-zinc-400 mb-1">ComfyUI API Key (可选)</label>
            <input
              type="password"
              placeholder="请输入 ComfyUI 安全秘钥"
              value={settings.comfy.apiKey}
              onChange={(e) => handleFieldChange("comfy", "apiKey", e.target.value)}
              className="w-full bg-[#17181c] border border-zinc-800 rounded px-3 py-1.5 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
            />
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <button
            onClick={() => testConnection("comfy", settings.comfy)}
            disabled={testingService !== null}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border border-zinc-800 bg-[#17181c] hover:bg-zinc-800 text-zinc-300 transition-colors disabled:opacity-50"
          >
            {testingService === "comfy" ? (
              <RefreshCw className="w-3 h-3 animate-spin" />
            ) : (
              <Server className="w-3 h-3 text-amber-500" />
            )}
            测试 ComfyUI 本地连接
          </button>
        </div>
      </div>

      {/* 4. Cloud Render node integrations */}
      <div className="bg-[#101114] border border-zinc-800 p-4 rounded-lg space-y-4">
        <h3 className="text-sm font-medium text-zinc-200 flex items-center gap-2 font-display">
          <Cpu className="w-4 h-4 text-amber-500" />
          云端算力托管及模型接口 (RunningHub / BizyAir / MiniMax)
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-zinc-900 pt-4">
          {/* RunningHub */}
          <div className="space-y-3">
            <h4 className="text-xs font-medium text-amber-400">RunningHub 云端 ComfyUI</h4>
            <div>
              <label className="block text-[10px] text-zinc-500 mb-1">RunningHub API Key</label>
              <input
                type="password"
                placeholder="请输入 RunningHub Key"
                value={settings.runninghub.apiKey}
                onChange={(e) => handleFieldChange("runninghub", "apiKey", e.target.value)}
                className="w-full bg-[#17181c] border border-zinc-800 rounded px-2.5 py-1 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[10px] text-zinc-500 mb-1">并发路数限制</label>
                <input
                  type="number"
                  min="1"
                  max="10"
                  value={settings.runninghub.concurrency}
                  onChange={(e) => handleFieldChange("runninghub", "concurrency", parseInt(e.target.value))}
                  className="w-full bg-[#17181c] border border-zinc-800 rounded px-2.5 py-1 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                />
              </div>
              <div>
                <label className="block text-[10px] text-zinc-500 mb-1">物理实例规格</label>
                <select
                  value={settings.runninghub.instanceType}
                  onChange={(e) => handleFieldChange("runninghub", "instanceType", e.target.value)}
                  className="w-full bg-[#17181c] border border-zinc-800 rounded px-2.5 py-1 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
                >
                  <option value="24G">RTX 4090 (24G)</option>
                  <option value="48G">RTX A6000 (48G)</option>
                </select>
              </div>
            </div>
            <button
              onClick={() => testConnection("runninghub", settings.runninghub)}
              disabled={testingService !== null}
              className="w-full flex justify-center items-center gap-1 py-1 text-[11px] rounded border border-zinc-800 bg-[#17181c] text-zinc-400 hover:text-zinc-200"
            >
              测试 RunningHub 连接
            </button>
          </div>

          {/* MiniMax / BizyAir */}
          <div className="space-y-3 md:border-l md:border-zinc-900 md:pl-4">
            <h4 className="text-xs font-medium text-amber-400">BizyAir 节点 / MiniMax TTS</h4>
            <div>
              <label className="block text-[10px] text-zinc-500 mb-1">BizyAir API Key</label>
              <input
                type="password"
                placeholder="请输入 BizyAir API Key"
                value={settings.bizyairKey}
                onChange={(e) => handleFieldChange("bizyairKey", "", e.target.value)}
                className="w-full bg-[#17181c] border border-zinc-800 rounded px-2.5 py-1 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
              />
            </div>
            <div>
              <label className="block text-[10px] text-zinc-500 mb-1">MiniMax API Key</label>
              <input
                type="password"
                placeholder="请输入 MiniMax API Key"
                value={settings.minimaxKey}
                onChange={(e) => handleFieldChange("minimaxKey", "", e.target.value)}
                className="w-full bg-[#17181c] border border-zinc-800 rounded px-2.5 py-1 text-xs text-zinc-300 focus:outline-none focus:border-amber-500"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => testConnection("bizyair", { apiKey: settings.bizyairKey })}
                className="flex justify-center items-center gap-1 py-1 text-[10px] rounded border border-zinc-800 bg-[#17181c] text-zinc-400 hover:text-zinc-200"
              >
                测试 BizyAir
              </button>
              <button
                onClick={() => testConnection("minimax", { apiKey: settings.minimaxKey })}
                className="flex justify-center items-center gap-1 py-1 text-[10px] rounded border border-zinc-800 bg-[#17181c] text-zinc-400 hover:text-zinc-200"
              >
                测试 MiniMax
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="flex gap-3 justify-end">
        <button
          onClick={() => onSaveSettings(settings)}
          className="px-5 py-2 text-xs font-semibold rounded bg-amber-500 text-[#07080a] hover:bg-amber-400 transition-colors shadow-lg shadow-amber-500/10"
        >
          保存所有设置
        </button>
      </div>
    </div>
  );
};
