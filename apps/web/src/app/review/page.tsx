"use client";

import { BookOpenCheck } from "lucide-react";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { SkeletonBlock } from "@/components/data-card";
import { PageTitle } from "@/components/page-title";

const ReviewDecisionWorkspace = dynamic(
  () =>
    import("./review-decision-workspace").then(
      (module) => module.ReviewDecisionWorkspace,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-72 w-full" />,
  },
);

const ReviewCaseWorkspace = dynamic(
  () =>
    import("./review-case-workspace").then(
      (module) => module.ReviewCaseWorkspace,
    ),
  {
    ssr: false,
    loading: () => (
      <section className="mb-7">
        <SkeletonBlock className="h-[520px] w-full" />
      </section>
    ),
  },
);

function cleanParam(value: string | null) {
  return value?.trim() || undefined;
}

function ReviewPageContent() {
  const searchParams = useSearchParams();
  const selectedDecisionId = cleanParam(searchParams.get("case"));

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        {selectedDecisionId ? (
          <>
            <PageTitle
              eyebrow="Review"
              title="Review Case 归因工作台"
              summary="围绕一条 Decision Ledger 样本完成归因、备注、结论动作与后续验证。"
              icon={BookOpenCheck}
              badge="Review Case"
              actions={
                <Link
                  href="/review"
                  className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  回到队列
                </Link>
              }
            />
            <ReviewCaseWorkspace decisionId={selectedDecisionId} />
          </>
        ) : (
          <ReviewDecisionWorkspace />
        )}
      </div>
    </main>
  );
}

export default function ReviewPage() {
  return (
    <Suspense
      fallback={
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
          <div className="mx-auto max-w-7xl">
            <SkeletonBlock className="h-72 w-full" />
          </div>
        </main>
      }
    >
      <ReviewPageContent />
    </Suspense>
  );
}
