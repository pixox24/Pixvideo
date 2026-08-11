import React from "react";
import { CheckCircle2, AlertCircle, Info, X, Copy } from "lucide-react";

export interface ToastMessage {
  id: string;
  type: "success" | "error" | "info";
  text: string;
  sticky?: boolean;
}

interface ToastProps {
  toasts: ToastMessage[];
  onClose: (id: string) => void;
}

export const Toast: React.FC<ToastProps> = ({ toasts, onClose }) => {
  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      /* ignore clipboard failures */
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 flex w-full max-w-sm flex-col gap-2 pointer-events-none">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto flex items-start gap-3 rounded-[var(--radius-lg)] border bg-[var(--color-surface-3)] p-4 shadow-[var(--shadow-soft)] animate-fade-in-up ${
            toast.type === "error"
              ? "border-rose-500/30"
              : toast.type === "success"
              ? "border-emerald-500/20"
              : "border-[var(--color-border-subtle)]"
          }`}
        >
          <div className="mt-0.5 shrink-0">
            {toast.type === "success" && <CheckCircle2 className="h-5 w-5 text-emerald-500" />}
            {toast.type === "error" && <AlertCircle className="h-5 w-5 text-rose-500" />}
            {toast.type === "info" && <Info className="h-5 w-5 text-amber-500" />}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium leading-relaxed text-zinc-200 break-words">{toast.text}</p>
            {toast.type === "error" && (
              <button
                type="button"
                onClick={() => void copyText(toast.text)}
                className="mt-2 inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300"
              >
                <Copy className="h-3 w-3" />
                复制错误信息
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={() => onClose(toast.id)}
            className="shrink-0 text-zinc-500 transition-colors hover:text-zinc-300"
            aria-label="关闭通知"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
};
