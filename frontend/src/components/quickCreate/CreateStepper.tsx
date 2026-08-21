import React from "react";
import {
  WIZARD_STEPS,
  WIZARD_STEP_HINT,
  type WizardStepId,
} from "./wizard";

export interface CreateStepperProps {
  wizardStep: WizardStepId;
  expertMode: boolean;
  contentReady: boolean;
  styleReady: boolean;
  voiceReady: boolean;
  reviewConfirmed: boolean;
  draftSavedAt: string | null;
  presetSlot?: React.ReactNode;
  onGoStep: (step: WizardStepId) => void;
  onRequestNext: () => void;
  onToggleExpert: () => void;
}

export const CreateStepper: React.FC<CreateStepperProps> = ({
  wizardStep,
  expertMode,
  contentReady,
  styleReady,
  voiceReady,
  reviewConfirmed,
  draftSavedAt,
  presetSlot,
  onGoStep,
  onRequestNext,
  onToggleExpert,
}) => {
  const completedOf = (id: WizardStepId) => {
    if (id === "content") return contentReady;
    if (id === "style") return styleReady;
    if (id === "voice") return voiceReady;
    return reviewConfirmed;
  };

  const stepIndex = WIZARD_STEPS.findIndex((s) => s.id === wizardStep);

  return (
    <nav
      className="sticky top-0 z-20 -mx-1 space-y-2 rounded-[var(--radius-lg)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-1)]/95 p-2 backdrop-blur-md"
      aria-label="快捷创作步骤"
    >
      <ol className="grid grid-cols-2 gap-1 sm:grid-cols-4">
        {WIZARD_STEPS.map((step, index) => {
          const completed = completedOf(step.id);
          const current = !expertMode && wizardStep === step.id;
          return (
            <li key={step.id}>
              <button
                type="button"
                aria-current={current ? "step" : undefined}
                onClick={() => {
                  if (expertMode) {
                    onGoStep(step.id);
                    return;
                  }
                  // Forward navigation gated by readiness
                  if (step.id === "style" && !contentReady && wizardStep === "content") {
                    onRequestNext();
                    return;
                  }
                  if (step.id === "voice" && wizardStep === "content" && !contentReady) {
                    onRequestNext();
                    return;
                  }
                  if (step.id === "voice" && wizardStep === "style" && !styleReady) {
                    onRequestNext();
                    return;
                  }
                  if (step.id === "review") {
                    if (!contentReady) {
                      onRequestNext();
                      return;
                    }
                    if (!styleReady) {
                      onGoStep("style");
                      return;
                    }
                    if (!voiceReady) {
                      onGoStep("voice");
                      return;
                    }
                  }
                  onGoStep(step.id);
                }}
                className={`flex min-h-11 w-full items-center justify-center gap-1.5 rounded-[var(--radius-md)] px-1.5 py-1.5 text-xs transition-colors ${
                  current
                    ? "bg-amber-500/10 text-amber-300 ring-1 ring-amber-500/25"
                    : completed
                      ? "bg-[var(--color-surface-3)] text-zinc-300 hover:text-zinc-100"
                      : "bg-[var(--color-surface-2)] text-zinc-500 hover:text-zinc-300"
                }`}
              >
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-caption font-semibold ${
                    current
                      ? "bg-amber-500 text-black"
                      : completed
                        ? "bg-amber-500/20 text-amber-300"
                        : "bg-white/5 text-zinc-500"
                  }`}
                >
                  {completed && !current ? "✓" : index + 1}
                </span>
                <span className="hidden sm:inline font-medium">{step.label}</span>
                <span className="sm:hidden font-medium">{step.short}</span>
              </button>
            </li>
          );
        })}
      </ol>
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <p className="text-caption" aria-live="polite">
          {expertMode
            ? "专家模式：一次显示全部步骤"
            : `步骤 ${stepIndex + 1}/${WIZARD_STEPS.length} · ${WIZARD_STEP_HINT[wizardStep]}`}
          {draftSavedAt ? ` · 草稿 ${new Date(draftSavedAt).toLocaleTimeString()}` : ""}
        </p>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {presetSlot}
          <button
            type="button"
            onClick={onToggleExpert}
            className="text-xs text-zinc-400 underline-offset-2 hover:text-amber-300 hover:underline"
          >
            {expertMode ? "退出专家模式" : "专家模式（展开全部）"}
          </button>
        </div>
      </div>
    </nav>
  );
};
