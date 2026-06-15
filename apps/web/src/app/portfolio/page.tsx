"use client";

import dynamic from "next/dynamic";
import { WalletCards } from "lucide-react";

import { SkeletonBlock } from "@/components/data-card";
import { PageTitle } from "@/components/page-title";

const PortfolioWorkspace = dynamic(
  () =>
    import("./portfolio-workspace").then((module) => module.PortfolioWorkspace),
  {
    ssr: false,
    loading: () => <PortfolioPageFallback />,
  },
);

function PortfolioPageFallback() {
  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow="Portfolio"
          title="账户控制台"
          summary="读取真实账户执行区、决策回写和研究自选股。"
          icon={WalletCards}
          badge="加载中"
        />
        <section className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <SkeletonBlock className="h-72 w-full" />
          <SkeletonBlock className="h-56 w-full" />
        </section>
      </div>
    </main>
  );
}

export default function PortfolioPage() {
  return <PortfolioWorkspace />;
}
