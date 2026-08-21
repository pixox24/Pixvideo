import React from "react";
import { FileVideo, FolderOpen, Loader, Sparkles } from "lucide-react";
import type { WizardStepId } from "./wizard";

export interface CreateStickyFooterProps {
  expertMode: boolean;
  wizardStep: WizardStepId;
  mode: "ai" | "manual" | "batch";
  isSubmitting: boolean;
  contentReady: boolean;
  styleReady: boolean;
  voiceReady: boolean;
  reviewConfirmed: boolean;
  reviewVideoCount: number;
  canCreateProject: boolean;
  onBack: () => void;
  onNext: () => void;
  onSubmitWorkbench: () => void;
  onSubmitDirect: () => void;
}

export const CreateStickyFooter: React.FC<CreateStickyFooterProps> = ({
  expertMode,
  wizardStep,
  mode,
  isSubmitting,
  contentReady,
  styleReady,
  voiceReady,
  reviewConfirmed,
  reviewVideoCount,
  canCreateProject,
  onBack,
  onNext,
  onSubmitWorkbench,
  onSubmitDirect,
}) => {
  const hint = (() => {
    if (isSubmitting) return "正在提交…";
    if (expertMode) {
      return mode === "batch"
        ? `将提交 ${reviewVideoCount} 个独立视频任务`
        : "核对后提交；推荐进入精修工作台";
    }
    if (wizardStep === "content") {
      return contentReady ? "内容已就绪，可进入风格设定" : "请生成或填写文案后再继续";
    }
    if (wizardStep === "style") {
      return styleReady ? "风格已就绪，可进入声音设定" : "请选择画面工作流";
    }
    if (wizardStep === "voice") {
      return voiceReady ? "声音已就绪，可进入确认" : "请选择配音音色";
    }
    if (!reviewConfirmed) return "请先勾选「生成前核对」中的确认项";
    if (mode === "batch") {
      return `将提交 ${reviewVideoCount} 个独立视频任务，进度在右侧任务面板`;
    }
    return "推荐：生成初稿并进入精修；也可直接渲染成片";
  })();

  const showSubmit = expertMode || wizardStep === "review";

  return (
    <div className="ui-sticky-footer fixed bottom-0 left-0 right-0 z-30 lg:left-60">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 text-xs text-zinc-500">{hint}</div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {!expertMode && wizardStep !== "content" && (
            <button type="button" onClick={onBack} className="ui-btn ui-btn-secondary">
              上一步
            </button>
          )}
          {!expertMode && wizardStep !== "review" && (
            <button
              type="button"
              onClick={onNext}
              className={`ui-btn ${
                wizardStep === "content"
                  ? contentReady
                    ? "ui-btn-primary"
                    : "ui-btn-secondary"
                  : "ui-btn-primary"
              }`}
            >
              下一步
            </button>
          )}
          {showSubmit && (
            <>
              {mode !== "batch" && canCreateProject && (
                <div className="flex flex-col items-end gap-0.5">
                  <button
                    type="button"
                    onClick={onSubmitDirect}
                    disabled={isSubmitting}
                    className="ui-btn ui-btn-secondary"
                  >
                    <FileVideo className="h-4 w-4" />
                    仅生成成片
                  </button>
                  <span className="text-caption hidden sm:block">直接渲染 MP4，不进入编辑</span>
                </div>
              )}
              <div className="flex flex-col items-end gap-0.5">
                <button
                  type="button"
                  onClick={onSubmitWorkbench}
                  disabled={isSubmitting}
                  className="ui-btn ui-btn-primary ui-btn-lg"
                >
                  {isSubmitting ? (
                    <Loader className="h-4 w-4 animate-spin" />
                  ) : mode === "batch" ? (
                    <Sparkles className="h-4 w-4 text-black" />
                  ) : (
                    <FolderOpen className="h-4 w-4 text-black" />
                  )}
                  {isSubmitting
                    ? "正在提交任务…"
                    : mode === "batch"
                      ? `提交 ${reviewVideoCount} 个视频任务`
                      : "生成初稿并打开工作台"}
                </button>
                {mode !== "batch" && (
                  <span className="text-caption hidden sm:block">创建项目并开始生成配音与画面</span>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
