import React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

export type AdvancedFoldProps = {
  title: string;
  open: boolean;
  onToggle: (next: boolean) => void;
  badge?: React.ReactNode;
  children?: React.ReactNode;
};

/** Controlled accordion. Do not use a native details element — it fights React `open`. */
export const AdvancedFold: React.FC<AdvancedFoldProps> = ({
  title,
  open,
  onToggle,
  badge,
  children,
}) => (
  <div>
    <button
      type="button"
      aria-expanded={open}
      onClick={() => onToggle(!open)}
      className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200"
    >
      {open ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      <span>{title}</span>
      {badge}
    </button>
    {children != null && (
      <div hidden={!open} className={open ? "mt-3 space-y-3" : undefined}>
        {children}
      </div>
    )}
  </div>
);
