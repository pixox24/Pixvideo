import React, { useState } from "react";
import { Select } from "./Select";
import { Server, Database, Key, RefreshCw, Cpu } from "lucide-react";
import { SystemSettings } from "../types";

interface SystemSettingsProps {
  settings: SystemSettings;
  onUpdateSettings: (newSettings: SystemSettings) => void;
  onSaveSettings: (newSettings: SystemSettings) => void | Promise<void>;
  addToast: (text: string, type: "success" | "error" | "info") => void;
}

const fieldLabel = "text-label mb-1.5 block";
const selectClass = "ui-input";
const savedHint = "mt-1 block text-caption text-emerald-400";

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

  const TestBtn: React.FC<{ service: string; label: string; onClick: () => void; full?: boolean }> = ({
    service,
    label,
    onClick,
    full,
  }) => (
    <button
      type="button"
      onClick={onClick}
      disabled={testingService !== null}
      className={`ui-btn ui-btn-secondary ui-btn-sm ${full ? "w-full" : ""}`}
    >
      {testingService === service ? (
        <RefreshCw className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <Server className="h-3.5 w-3.5 text-amber-500" />
      )}
      {label}
    </button>
  );

  return (
    <div className="mx-auto max-w-4xl animate-fade-in space-y-5 pb-8">
      <div className="flex flex-col gap-1 border-b border-[var(--color-border-subtle)] pb-4">
        <h2 className="font-display flex items-center gap-2 text-lg font-semibold text-zinc-100">
          <Database className="h-5 w-5 text-amber-500" />
          系统连接配置
        </h2>
        <p className="text-sm text-zinc-400">
          配置语言模型、图像生成、ComfyUI、RunningHub 等服务。保存后写入服务器配置，刷新后仍保留。
        </p>
        <button
          type="button"
          onClick={() => {
            try {
              localStorage.removeItem("pixvideo.onboarding.coach.v1");
              localStorage.removeItem("pixvideo.onboarding.create-tip.v1");
              localStorage.removeItem("pixvideo.onboarding.workbench-keys.v1");
            } catch {
              /* ignore */
            }
            addToast("已重置入门提示，刷新页面后将再次显示引导。", "info");
          }}
          className="mt-2 self-start text-xs text-amber-400/90 underline-offset-2 hover:text-amber-300 hover:underline"
        >
          重置入门引导与界面提示
        </button>
      </div>

      {/* 1. LLM */}
      <section className="ui-card space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-display flex items-center gap-2 text-sm font-semibold text-zinc-100">
            <Cpu className="h-4 w-4 text-amber-500" />
            语言模型（脚本生成）
          </h3>
          <span className="ui-chip ui-chip-success">推荐 Gemini 3.5</span>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label className={fieldLabel}>供应商</label>
            <Select
              value={settings.llm.provider}
              onChange={(e) => handleProviderChange(e.target.value as SystemSettings["llm"]["provider"])}
              className={selectClass}
            >
              <option value="gemini">Google Gemini AI</option>
              <option value="deepseek">DeepSeek API</option>
              <option value="openai">OpenAI GPT-4</option>
            </Select>
          </div>

          <div>
            <label className={fieldLabel}>模型</label>
            <Select
              value={settings.llm.model}
              onChange={(e) => handleFieldChange("llm", "model", e.target.value)}
              className={selectClass}
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
            </Select>
          </div>

          <div className="md:col-span-2">
            <label className={fieldLabel}>API Key</label>
            <div className="relative">
              <input
                type="password"
                placeholder={
                  settings.llm.provider === "gemini"
                    ? "已自动检测系统注入的 GEMINI_API_KEY"
                    : "请输入 API Key"
                }
                value={settings.llm.apiKey}
                onChange={(e) => handleFieldChange("llm", "apiKey", e.target.value)}
                className="ui-input pl-9"
              />
              <Key className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-500" />
            </div>
            {settings.llm.apiKeyMasked && !settings.llm.apiKey && (
              <span className={savedHint}>已保存：{settings.llm.apiKeyMasked}，输入新值可替换</span>
            )}
          </div>

          <div className="md:col-span-2">
            <label className={fieldLabel}>Base URL（API 代理地址）</label>
            <input
              type="text"
              placeholder="https://api.example.com/v1"
              value={settings.llm.baseUrl}
              onChange={(e) => handleFieldChange("llm", "baseUrl", e.target.value)}
              className="ui-input"
            />
          </div>
        </div>

        <div className="flex justify-end pt-1">
          <TestBtn service="llm" label="测试 LLM 连接" onClick={() => testConnection("llm", settings.llm)} />
        </div>
      </section>

      {/* 2. Image generation */}
      <section className="ui-card space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-display flex items-center gap-2 text-sm font-semibold text-zinc-100">
            <Cpu className="h-4 w-4 text-amber-500" />
            图片生成模型
          </h3>
          <span className="ui-chip ui-chip-success">OpenAI Images 兼容</span>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="md:col-span-2">
            <label className={fieldLabel}>Base URL</label>
            <input
              type="text"
              placeholder="https://img-cn.65535.space/v1"
              value={settings.imageGeneration.baseUrl}
              onChange={(e) => handleFieldChange("imageGeneration", "baseUrl", e.target.value)}
              className="ui-input"
            />
          </div>

          <div>
            <label className={fieldLabel}>API Key</label>
            <input
              type="password"
              placeholder="请输入图片生成 API Key"
              value={settings.imageGeneration.apiKey}
              onChange={(e) => handleFieldChange("imageGeneration", "apiKey", e.target.value)}
              className="ui-input"
            />
            {settings.imageGeneration.apiKeyMasked && !settings.imageGeneration.apiKey && (
              <span className={savedHint}>
                已保存：{settings.imageGeneration.apiKeyMasked}，输入新值可替换
              </span>
            )}
          </div>

          <div>
            <label className={fieldLabel}>Model</label>
            <input
              type="text"
              placeholder="gpt-image-2"
              value={settings.imageGeneration.model}
              onChange={(e) => handleFieldChange("imageGeneration", "model", e.target.value)}
              className="ui-input"
            />
          </div>
        </div>

        <div className="flex justify-end pt-1">
          <TestBtn
            service="image_generation"
            label="测试图片生成配置"
            onClick={() => testConnection("image_generation", settings.imageGeneration)}
          />
        </div>
      </section>

      {/* 3. ComfyUI */}
      <section className="ui-card space-y-4">
        <h3 className="font-display flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <Cpu className="h-4 w-4 text-amber-500" />
          ComfyUI 本地服务
        </h3>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label className={fieldLabel}>ComfyUI Web API 地址</label>
            <input
              type="text"
              value={settings.comfy.url}
              onChange={(e) => handleFieldChange("comfy", "url", e.target.value)}
              className="ui-input"
            />
          </div>

          <div>
            <label className={fieldLabel}>ComfyUI API Key（可选）</label>
            <input
              type="password"
              placeholder="请输入 ComfyUI 安全秘钥"
              value={settings.comfy.apiKey}
              onChange={(e) => handleFieldChange("comfy", "apiKey", e.target.value)}
              className="ui-input"
            />
            {settings.comfy.apiKeyMasked && !settings.comfy.apiKey && (
              <span className={savedHint}>已保存：{settings.comfy.apiKeyMasked}，输入新值可替换</span>
            )}
          </div>
        </div>

        <div className="flex justify-end pt-1">
          <TestBtn
            service="comfy"
            label="测试 ComfyUI 本地连接"
            onClick={() => testConnection("comfy", settings.comfy)}
          />
        </div>
      </section>

      {/* 4. Cloud integrations */}
      <section className="ui-card space-y-4">
        <h3 className="font-display flex items-center gap-2 text-sm font-semibold text-zinc-100">
          <Cpu className="h-4 w-4 text-amber-500" />
          云端算力与 TTS 密钥
        </h3>

        <div className="grid grid-cols-1 gap-6 border-t border-[var(--color-border-subtle)] pt-4 md:grid-cols-2">
          <div className="space-y-3">
            <h4 className="text-xs font-semibold text-amber-400">RunningHub 云端 ComfyUI</h4>
            <div>
              <label className={fieldLabel}>RunningHub API Key</label>
              <input
                type="password"
                placeholder="请输入 RunningHub Key"
                value={settings.runninghub.apiKey}
                onChange={(e) => handleFieldChange("runninghub", "apiKey", e.target.value)}
                className="ui-input"
              />
              {settings.runninghub.apiKeyMasked && !settings.runninghub.apiKey && (
                <span className={savedHint}>
                  已保存：{settings.runninghub.apiKeyMasked}，输入新值可替换
                </span>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className={fieldLabel}>并发路数</label>
                <input
                  type="number"
                  min="1"
                  max="10"
                  value={settings.runninghub.concurrency}
                  onChange={(e) =>
                    handleFieldChange("runninghub", "concurrency", parseInt(e.target.value))
                  }
                  className="ui-input"
                />
              </div>
              <div>
                <label className={fieldLabel}>实例规格</label>
                <Select
                  value={settings.runninghub.instanceType}
                  onChange={(e) => handleFieldChange("runninghub", "instanceType", e.target.value)}
                  className={selectClass}
                >
                  <option value="24G">RTX 4090 (24G)</option>
                  <option value="48G">RTX A6000 (48G)</option>
                </Select>
              </div>
            </div>
            <TestBtn
              full
              service="runninghub"
              label="测试 RunningHub 连接"
              onClick={() => testConnection("runninghub", settings.runninghub)}
            />
          </div>

          <div className="space-y-3 md:border-l md:border-[var(--color-border-subtle)] md:pl-4">
            <h4 className="text-xs font-semibold text-amber-400">BizyAir · MiniMax · MiMo · Qwen Audio</h4>
            <div>
              <label className={fieldLabel}>BizyAir API Key</label>
              <input
                type="password"
                placeholder="请输入 BizyAir API Key"
                value={settings.bizyairKey}
                onChange={(e) => handleFieldChange("bizyairKey", "", e.target.value)}
                className="ui-input"
              />
              {settings.bizyairKeyMasked && !settings.bizyairKey && (
                <span className={savedHint}>已保存：{settings.bizyairKeyMasked}，输入新值可替换</span>
              )}
            </div>
            <div>
              <label className={fieldLabel}>MiniMax API Key</label>
              <input
                type="password"
                placeholder="请输入 MiniMax API Key"
                value={settings.minimaxKey}
                onChange={(e) => handleFieldChange("minimaxKey", "", e.target.value)}
                className="ui-input"
              />
              {settings.minimaxKeyMasked && !settings.minimaxKey && (
                <span className={savedHint}>已保存：{settings.minimaxKeyMasked}，输入新值可替换</span>
              )}
            </div>
            <div>
              <label className={fieldLabel}>MiMo API Key（Xiaomi）</label>
              <input
                type="password"
                placeholder="请输入 MiMo API Key"
                value={settings.mimoKey}
                onChange={(e) => handleFieldChange("mimoKey", "", e.target.value)}
                className="ui-input"
              />
              {settings.mimoKeyMasked && !settings.mimoKey && (
                <span className={savedHint}>已保存：{settings.mimoKeyMasked}，输入新值可替换</span>
              )}
            </div>
            <div>
              <label className={fieldLabel}>DashScope API Key（Qwen Audio）</label>
              <input
                type="password"
                placeholder="请输入 DashScope API Key，或使用 DASHSCOPE_API_KEY"
                value={settings.qwenAudioKey}
                onChange={(e) => handleFieldChange("qwenAudioKey", "", e.target.value)}
                className="ui-input"
              />
              {settings.qwenAudioKeyMasked && !settings.qwenAudioKey && (
                <span className={savedHint}>已保存：{settings.qwenAudioKeyMasked}，输入新值可替换</span>
              )}
            </div>
            <div className="grid grid-cols-4 gap-2">
              <TestBtn
                service="bizyair"
                label="BizyAir"
                onClick={() => testConnection("bizyair", { apiKey: settings.bizyairKey })}
              />
              <TestBtn
                service="minimax"
                label="MiniMax"
                onClick={() => testConnection("minimax", { apiKey: settings.minimaxKey })}
              />
              <TestBtn
                service="mimo"
                label="MiMo"
                onClick={() => testConnection("mimo", { apiKey: settings.mimoKey })}
              />
              <TestBtn
                service="qwen_audio"
                label="Qwen Audio"
                onClick={() => testConnection("qwen_audio", { apiKey: settings.qwenAudioKey })}
              />
            </div>
          </div>
        </div>
      </section>

      <div className="flex justify-end gap-3">
        <button type="button" onClick={() => onSaveSettings(settings)} className="ui-btn ui-btn-primary ui-btn-lg">
          保存所有设置
        </button>
      </div>
    </div>
  );
};
