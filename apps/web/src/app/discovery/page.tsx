"use client";

import dynamic from "next/dynamic";
import { Telescope } from "lucide-react";

import { SkeletonBlock } from "@/components/data-card";
import { PageTitle } from "@/components/page-title";

const DiscoveryWorkspace = dynamic(
  () =>
    import("./discovery-workspace").then((module) => module.DiscoveryWorkspace),
  {
    ssr: false,
    loading: () => <DiscoveryPageFallback />,
  },
);

function DiscoveryPageFallback() {
  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow="Discovery"
          title="观察池"
          summary="读取候选 Pipeline、阀门状态、质检和主线热力。"
          icon={Telescope}
          badge="加载中"
        />
        <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <SkeletonBlock key={index} className="h-24 w-full" />
          ))}
        </section>
        <SkeletonBlock className="h-72 w-full" />
      </div>
    </main>
  );
}

export default function DiscoveryPage() {
  return <DiscoveryWorkspace />;
}
