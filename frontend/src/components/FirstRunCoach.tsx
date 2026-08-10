import React from "react";
import { ArrowRight, Settings2, Sparkles, X } from "lucide-react";

export type CoachNeed = {
  key: string;
  label: string;
  detail: string;
  required: boolean;
};

interface FirstRunCoachProps {
  open: boolean;
  needs: CoachNeed[];
  onOpenSettings: () => void;
  onStartCreate: () => void;
  onDismiss: () => void;
}

export const FirstRunCoach: React.FC<FirstRunCoachProps> = ({
  open,
  needs,
  onOpenSettings,
  onStartCreate,
  onDismiss,
}) => {
  if (!open) return null;
  const requiredMissing = needs.filter((item) => item.required);
  const optionalMissing = needs.filter((item) => !item.required);

  return (
    <div className="fixed inset-0 z-[55] flex items-center justify-center bg-black/70 p-4 animate-fade-in">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="first-run-coach-title"
        className="relative w-full max-w-lg overflow-hidden rounded-xl border border-zinc-700 bg-[var(--color-surface-2)] shadow-2xl shadow-black/50"
      >
        <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-amber-500/15 to-transparent" />
        <div className="relative p-5 sm:p-6">
          <button
            type="button"
            onClick={onDismiss}
            className="absolute right-3 top-3 rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
            aria-label="关闭引导"
          >
            <X className="h-4 w-4" />
          </button>

          <div className="mb-4 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500 text-black shadow-lg shadow-amber-500/20">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h2 id="first-run-coach-title" className="text-base font-semibold text-zinc-100 font-display">
                欢迎使用 PixVideo
              </h2>
              <p className="mt-0.5 text-xs text-zinc-400">完成下面几项即可开始创作短视频</p>
            </div>
          </div>

          <ol className="space-y-2">
            {needs.map((item, index) => (
              <li
                key={item.key}
                className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-[var(--color-surface-3)] px-3 py-2.5"
              >
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-[11px] font-mono text-amber-400">
                  {index + 1}
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-zinc-200">{item.label}</span>
                    {item.required ? (
                      <span className="rounded bg-rose-500/10 px-1.5 py-0.5 text-caption text-rose-300">建议配置</span>
                    ) : (
                      <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-caption text-zinc-500">可选</span>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-zinc-500">{item.detail}</p>
                </div>
              </li>
            ))}
          </ol>

          {requiredMissing.length === 0 && optionalMissing.length === 0 && (
            <p className="mt-3 text-xs text-emerald-300">关键服务看起来已就绪，可以直接创作。</p>
          )}

          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <button
              type="button"
              onClick={onDismiss}
              className="rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
            >
              稍后配置
            </button>
            <button
              type="button"
              onClick={() => {
                onDismiss();
                onOpenSettings();
              }}
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-600 px-3 py-2 text-xs font-medium text-zinc-200 hover:border-amber-500/40"
            >
              <Settings2 className="h-3.5 w-3.5" />
              打开系统设置
            </button>
            <button
              type="button"
              onClick={() => {
                onDismiss();
                onStartCreate();
              }}
              className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500 px-3 py-2 text-xs font-semibold text-black hover:bg-amber-400"
            >
              开始创作
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
