import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";

type SelectProps = Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "onChange" | "size" | "multiple"> & {
  onChange?: (event: React.ChangeEvent<HTMLSelectElement>) => void;
};

type SelectOption = {
  disabled: boolean;
  label: React.ReactNode;
  value: string;
};

const collectOptions = (children: React.ReactNode, options: SelectOption[] = []): SelectOption[] => {
  React.Children.forEach(children, (child) => {
    if (!React.isValidElement(child)) return;

    if (child.type === React.Fragment) {
      collectOptions(child.props.children, options);
      return;
    }

    if (child.type === "option") {
      const option = child.props as React.OptionHTMLAttributes<HTMLOptionElement>;
      options.push({
        disabled: Boolean(option.disabled),
        label: option.children,
        value: String(option.value ?? ""),
      });
    }
  });

  return options;
};

export const Select: React.FC<SelectProps> = ({
  children,
  className = "",
  disabled = false,
  onChange,
  value,
  defaultValue,
  id,
  name,
  "aria-label": ariaLabel,
  "aria-labelledby": ariaLabelledBy,
}) => {
  const generatedId = useId();
  const triggerId = id ?? generatedId;
  const listboxId = `${triggerId}-options`;
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const options = useMemo(() => collectOptions(children), [children]);
  const currentValue = String(value ?? defaultValue ?? "");
  const selectedIndex = Math.max(0, options.findIndex((option) => option.value === currentValue));
  const [activeIndex, setActiveIndex] = useState(selectedIndex);
  const selectedOption = options.find((option) => option.value === currentValue);

  useEffect(() => {
    setActiveIndex(selectedIndex);
  }, [selectedIndex]);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const selectOption = (option: SelectOption) => {
    if (option.disabled) return;
    onChange?.({ target: { value: option.value } } as React.ChangeEvent<HTMLSelectElement>);
    close();
  };

  const firstEnabledFrom = (startIndex: number, direction: 1 | -1) => {
    if (!options.length) return startIndex;

    let index = startIndex;
    for (let count = 0; count < options.length; count += 1) {
      index = (index + direction + options.length) % options.length;
      if (!options[index].disabled) return index;
    }
    return startIndex;
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;

    if (event.key === "Escape" && open) {
      event.preventDefault();
      close();
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen((isOpen) => !isOpen);
      return;
    }

    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;

    event.preventDefault();
    const nextIndex = firstEnabledFrom(activeIndex, event.key === "ArrowDown" ? 1 : -1);
    if (open) {
      setActiveIndex(nextIndex);
    } else {
      selectOption(options[nextIndex]);
    }
  };

  return (
    <div ref={rootRef} className="relative w-full">
      <input type="hidden" name={name} value={currentValue} />
      <button
        ref={triggerRef}
        id={triggerId}
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledBy}
        aria-haspopup="listbox"
        aria-controls={listboxId}
        aria-expanded={open}
        onClick={() => !disabled && setOpen((isOpen) => !isOpen)}
        onKeyDown={handleKeyDown}
        className={`flex h-10 w-full items-center justify-between gap-2 rounded-[var(--radius-md)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-3)] px-3 text-left text-sm text-[var(--color-text-primary)] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] transition duration-150 hover:border-[var(--color-border-default)] focus:outline-none focus-visible:border-amber-500/60 focus-visible:ring-2 focus-visible:ring-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      >
        <span className="min-w-0 flex-1 truncate">{selectedOption?.label ?? "请选择"}</span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-zinc-500 transition-transform duration-150 ${open ? "rotate-180 text-amber-400" : ""}`} />
      </button>

      {open && (
        <div
          id={listboxId}
          role="listbox"
          aria-labelledby={triggerId}
          className="absolute left-0 top-[calc(100%+0.375rem)] z-50 max-h-64 w-full overflow-y-auto rounded-[var(--radius-lg)] border border-[var(--color-border-subtle)] bg-[var(--color-surface-2)] p-1.5 shadow-[var(--shadow-soft)]"
        >
          {options.map((option, index) => {
            const selected = option.value === currentValue;
            const active = index === activeIndex;

            return (
              <button
                key={`${option.value}-${index}`}
                type="button"
                role="option"
                aria-selected={selected}
                disabled={option.disabled}
                onMouseEnter={() => !option.disabled && setActiveIndex(index)}
                onClick={() => selectOption(option)}
                className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors ${
                  option.disabled
                    ? "cursor-not-allowed text-zinc-600"
                    : selected
                      ? "bg-amber-500/12 text-amber-100"
                      : active
                        ? "bg-[var(--color-surface-4)] text-[var(--color-text-primary)]"
                        : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-4)] hover:text-[var(--color-text-primary)]"
                }`}
              >
                <span className="min-w-0 flex-1 truncate">{option.label}</span>
                {selected && <Check className="h-3.5 w-3.5 shrink-0 text-amber-400" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};
