"use client";

import dynamic from "next/dynamic";
import { Settings } from "lucide-react";

import { SkeletonBlock } from "@/components/data-card";
import { PageTitle } from "@/components/page-title";

const SettingsWorkspace = dynamic(
  () =>
    import("./settings-workspace").then((module) => module.SettingsWorkspace),
  {
    ssr: false,
    loading: () => <SettingsPageFallback />,
  },
);

function SettingsPageFallback() {
  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow="Settings"
          title="设置"
          summary="读取今日数据状态与安全刷新入口。"
          icon={Settings}
          badge="加载中"
        />
        <section className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="flex flex-col gap-6">
            <SkeletonBlock className="h-64 w-full" />
            <SkeletonBlock className="h-80 w-full" />
          </div>
          <div className="flex flex-col gap-6">
            <SkeletonBlock className="h-36 w-full" />
            <SkeletonBlock className="h-48 w-full" />
          </div>
        </section>
      </div>
    </main>
  );
}

export default function SettingsPage() {
  return <SettingsWorkspace />;
}
