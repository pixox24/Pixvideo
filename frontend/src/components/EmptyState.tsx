import React from "react";

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  className = "",
}) => (
  <div
    className={`flex flex-col items-center justify-center rounded-xl border border-dashed border-zinc-800 bg-[var(--color-surface-2)] px-6 py-12 text-center animate-fade-in ${className}`}
  >
    {icon && <div className="mb-3 text-zinc-600">{icon}</div>}
    <h3 className="text-sm font-semibold text-zinc-200 font-display">{title}</h3>
    {description && <p className="mt-1.5 max-w-sm text-xs leading-relaxed text-zinc-500">{description}</p>}
    {action && <div className="mt-4 flex flex-wrap justify-center gap-2">{action}</div>}
  </div>
);
