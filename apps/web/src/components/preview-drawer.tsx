"use client";

import { LoaderCircle, X } from "lucide-react";

import { cn } from "@/lib/utils";

export interface PreviewDrawerState {
  open: boolean;
  title: string;
  subtitle?: string;
  text?: string;
  kind?: string;
  loading?: boolean;
  error?: string;
  truncated?: boolean;
}

export function PreviewDrawer({
  state,
  onClose,
}: {
  state: PreviewDrawerState;
  onClose: () => void;
}) {
  if (!state.open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/55" onMouseDown={onClose}>
      <aside
        className="flex h-full w-full max-w-[760px] flex-col border-l border-[var(--border-default)] bg-[var(--bg-primary)] shadow-2xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] px-4 py-4 sm:px-5">
          <div className="min-w-0">
            <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
              {state.kind || "Preview"}
            </div>
            <h2 className="mt-1 truncate text-base font-semibold text-[var(--text-primary)]">{state.title}</h2>
            {state.subtitle ? (
              <div className="mono mt-1 truncate text-[11px] text-[var(--text-tertiary)]">{state.subtitle}</div>
            ) : null}
          </div>
          <button
            type="button"
            className="focus-ring flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
            onClick={onClose}
            aria-label="关闭预览"
          >
            <X size={16} />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-5">
          {state.loading ? (
            <div className="flex h-40 items-center justify-center gap-2 text-[13px] text-[var(--text-secondary)]">
              <LoaderCircle size={16} className="animate-spin" />
              加载预览
            </div>
          ) : state.error ? (
            <div className="rounded-md border border-[color-mix(in_srgb,var(--negative)_20%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] px-4 py-3 text-[13px] text-[var(--text-secondary)]">
              {state.error}
            </div>
          ) : (
            <pre
              className={cn(
                "mono min-h-full whitespace-pre-wrap break-words rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4 text-[12px] leading-6 text-[var(--text-secondary)]",
                !state.text && "text-[var(--text-tertiary)]",
              )}
            >
              {state.text || "该文件没有可预览文本，可能是二进制文件。"}
            </pre>
          )}
        </div>

        {state.truncated ? (
          <div className="border-t border-[var(--border-subtle)] px-5 py-3 text-[12px] text-[var(--text-tertiary)]">
            预览内容已截断，完整文件可从 artifacts 入口打开。
          </div>
        ) : null}
      </aside>
    </div>
  );
}
