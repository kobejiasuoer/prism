"use client";

import { useTheme } from "@/components/theme-provider";
import { resolvedThemeLabel, THEME_OPTIONS } from "@/components/theme-options";
import { cn } from "@/lib/utils";

export function ThemeToggle({ className }: { className?: string }) {
  const { mode, resolvedTheme, setMode } = useTheme();

  return (
    <div className={cn("min-w-0", className)}>
      <div className="mb-2 flex items-center justify-between gap-2 px-1">
        <span className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">主题</span>
        <span className="text-[11px] text-[var(--text-tertiary)]">
          {resolvedThemeLabel(mode, resolvedTheme)}
        </span>
      </div>
      <div
        className="grid grid-cols-3 gap-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-1"
        role="group"
        aria-label="主题切换"
      >
        {THEME_OPTIONS.map((option) => {
          const Icon = option.icon;
          const active = option.mode === mode;
          return (
            <button
              key={option.mode}
              type="button"
              className={cn(
                "focus-ring inline-flex min-h-11 min-w-0 flex-col items-center justify-center gap-1 rounded-[6px] px-1.5 text-center text-[11px] font-medium leading-none transition-colors",
                active
                  ? "bg-[var(--bg-elevated)] text-[var(--text-primary)] shadow-sm"
                  : "text-[var(--text-tertiary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-secondary)]",
              )}
              aria-pressed={active}
              title={option.title}
              onClick={() => setMode(option.mode)}
            >
              <Icon size={14} aria-hidden="true" />
              <span className="truncate">{option.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
