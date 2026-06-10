"use client";

import dynamic from "next/dynamic";
import { FileDown, RefreshCw } from "lucide-react";

import { SkeletonBlock } from "@/components/data-card";

const CommandCenterWorkspace = dynamic(
  () =>
    import("./command-center-workspace").then(
      (module) => module.CommandCenterWorkspace,
    ),
  {
    ssr: false,
    loading: () => <CommandCenterPageFallback />,
  },
);

function CommandCenterPageFallback() {
  return (
    <main className="war-room">
      <div className="war-room-inner">
        <header className="war-topbar">
          <div>
            <div className="war-eyebrow">Daily Command Brief</div>
            <h1>每日交易命令台</h1>
          </div>
          <div className="war-top-actions">
            <button
              type="button"
              className="focus-ring war-tool-btn"
              disabled
            >
              <RefreshCw size={14} className="animate-spin" />
              刷新
            </button>
            <button
              type="button"
              className="focus-ring war-tool-btn"
              disabled
            >
              <FileDown size={14} />
              导出简报
            </button>
          </div>
        </header>
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
          <div className="mb-3 flex items-center gap-2 text-[13px] text-[var(--text-secondary)]">
            <RefreshCw size={14} className="animate-spin" />
            正在读取今日命令台和数据可信度
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {Array.from({ length: 4 }).map((_, index) => (
              <SkeletonBlock key={index} className="h-28 w-full" />
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}

export default function CommandCenterPage() {
  return <CommandCenterWorkspace />;
}
