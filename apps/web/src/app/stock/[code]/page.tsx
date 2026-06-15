"use client";

import dynamic from "next/dynamic";

import { SkeletonBlock } from "@/components/data-card";

const StockProfileWorkspace = dynamic(
  () =>
    import("./stock-profile-workspace").then(
      (module) => module.StockProfileWorkspace,
    ),
  {
    ssr: false,
    loading: () => <StockProfilePageFallback />,
  },
);

function StockProfilePageFallback() {
  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <SkeletonBlock className="h-72 w-full" />
      </div>
    </main>
  );
}

export default function StockProfilePage() {
  return <StockProfileWorkspace />;
}
