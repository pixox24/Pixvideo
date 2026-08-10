import React, { useEffect, useRef } from "react";
import { AlertTriangle, X } from "lucide-react";

interface ConfirmModalProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
}

export const ConfirmModal: React.FC<ConfirmModalProps> = ({
  open,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  danger = false,
  busy = false,
  onConfirm,
  onCancel,
}) => {
  const confirmRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    confirmRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, busy, onCancel]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4">
      <button
        type="button"
        className="absolute inset-0 cursor-default"
        aria-label="关闭对话框"
        disabled={busy}
        onClick={() => {
          if (!busy) onCancel();
        }}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        className="relative w-full max-w-md rounded-xl border border-zinc-700 bg-[var(--color-surface-2)] p-5 shadow-2xl animate-soft-scale-in"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            {danger && (
              <div className="mt-0.5 rounded-full bg-rose-500/10 p-2 text-rose-400">
                <AlertTriangle className="h-4 w-4" />
              </div>
            )}
            <div>
              <h2 id="confirm-modal-title" className="text-sm font-semibold text-zinc-100">
                {title}
              </h2>
              {description && (
                <p className="mt-1.5 text-xs leading-relaxed text-zinc-400">{description}</p>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="p-1 text-zinc-500 hover:text-zinc-200 disabled:opacity-40"
            aria-label="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-zinc-500 disabled:opacity-40"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={() => void onConfirm()}
            disabled={busy}
            className={`rounded px-3 py-2 text-xs font-semibold disabled:opacity-40 ${
              danger
                ? "bg-rose-500 text-white hover:bg-rose-400"
                : "bg-amber-500 text-black hover:bg-amber-400"
            }`}
          >
            {busy ? "处理中…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
};
