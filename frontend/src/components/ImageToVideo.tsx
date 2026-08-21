import React, { useMemo, useState } from "react";
import { ArrowLeft, Clapperboard, Upload } from "lucide-react";
import { WorkflowOption } from "../types";
import { submitImageToVideoTask, uploadImageToVideoFile } from "../lib/api";

interface Props {
  workflows: WorkflowOption[];
  addToast: (text: unknown, type?: "success" | "error" | "info") => void;
  onSubmitted: (taskId: string, title: string) => void;
  onOpenConsole: () => void;
  onBackToCreate?: () => void;
}

const DEFAULT_WORKFLOW = "runninghub/i2v_LTX2.json";

export const ImageToVideo: React.FC<Props> = ({
  workflows,
  addToast,
  onSubmitted,
  onOpenConsole,
  onBackToCreate,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [title, setTitle] = useState("");
  const [workflowKey, setWorkflowKey] = useState(DEFAULT_WORKFLOW);
  const [busy, setBusy] = useState(false);

  const i2vWorkflows = useMemo(() => {
    const listed = workflows.filter((item) => /i2v|video_/i.test(item.id || item.name || ""));
    return listed.length > 0 ? listed : workflows;
  }, [workflows]);

  const onPickFile = (next: File | null) => {
    setFile(next);
    setPreviewUrl((current) => {
      if (current) URL.revokeObjectURL(current);
      return next ? URL.createObjectURL(next) : null;
    });
  };

  const submit = async () => {
    if (!file) {
      addToast("请先上传一张参考图", "error");
      return;
    }
    if (!prompt.trim()) {
      addToast("请填写运动提示词", "error");
      return;
    }
    setBusy(true);
    try {
      const uploaded = await uploadImageToVideoFile(file);
      const taskTitle = title.trim() || file.name.replace(/\.[^.]+$/, "") || "图生视频";
      const result = await submitImageToVideoTask({
        imageFileKey: uploaded.file_key,
        prompt: prompt.trim(),
        workflowKey: workflowKey || DEFAULT_WORKFLOW,
        title: taskTitle,
      });
      onSubmitted(result.task_id, taskTitle);
      onOpenConsole();
      addToast("已提交图生视频任务", "success");
    } catch (error) {
      addToast(error, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="ui-card space-y-3 p-5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Clapperboard className="h-4 w-4 text-amber-400" />
            <h2 className="font-display text-base font-semibold">图生视频</h2>
          </div>
          {onBackToCreate && (
            <button type="button" className="ui-btn ui-btn-ghost ui-btn-sm" onClick={onBackToCreate}>
              <ArrowLeft className="h-3.5 w-3.5" />
              返回口播创作
            </button>
          )}
        </div>
        <p className="text-sm text-zinc-400">
          上传一张参考图并描述镜头运动，使用图生视频工作流生成短片。完成后会出现在作品库。
        </p>
      </div>

      <div className="ui-card space-y-4 p-5">
        <label className="block space-y-2">
          <span className="text-xs font-semibold text-zinc-300">参考图</span>
          <div className="flex flex-col gap-3 sm:flex-row">
            <label className="flex min-h-36 flex-1 cursor-pointer flex-col items-center justify-center rounded-[var(--radius-md)] border border-dashed border-[var(--color-border-strong)] bg-[var(--color-surface-3)] px-4 py-6 text-center hover:border-amber-500/50">
              <Upload className="mb-2 h-5 w-5 text-zinc-500" />
              <span className="text-xs text-zinc-400">{file ? file.name : "点击选择 jpg / png / webp"}</span>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                onChange={(event) => onPickFile(event.target.files?.[0] || null)}
              />
            </label>
            {previewUrl && (
              <img
                src={previewUrl}
                alt="参考图预览"
                className="h-36 w-36 rounded-[var(--radius-md)] object-cover"
              />
            )}
          </div>
        </label>

        <label className="block space-y-1.5">
          <span className="text-xs font-semibold text-zinc-300">任务标题</span>
          <input
            className="ui-input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="可选，默认使用文件名"
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-xs font-semibold text-zinc-300">运动提示词</span>
          <textarea
            className="ui-input min-h-28"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="例如：镜头缓慢前推，阳光从左侧洒入，轻微风吹动衣角"
          />
        </label>

        <label className="block space-y-1.5">
          <span className="text-xs font-semibold text-zinc-300">工作流</span>
          <select
            className="ui-input"
            value={workflowKey}
            onChange={(event) => setWorkflowKey(event.target.value)}
          >
            {!i2vWorkflows.some((item) => item.id === DEFAULT_WORKFLOW) && (
              <option value={DEFAULT_WORKFLOW}>{DEFAULT_WORKFLOW}</option>
            )}
            {i2vWorkflows.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name || item.id}
              </option>
            ))}
          </select>
        </label>

        <div className="flex justify-end">
          <button type="button" className="ui-btn ui-btn-primary" disabled={busy} onClick={() => void submit()}>
            {busy ? "提交中…" : "生成视频"}
          </button>
        </div>
      </div>
    </div>
  );
};
