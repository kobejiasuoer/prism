"use client";

import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import {
  ClipboardCheck,
  RefreshCw,
  ShieldCheck,
  WalletCards,
} from "lucide-react";

import { Badge } from "@/components/badge";
import {
  EmptyState,
  ErrorState,
  Panel,
  SkeletonBlock,
} from "@/components/data-card";
import { DeferredTrustBanner } from "@/components/deferred-trust-banner";
import { PageTitle } from "@/components/page-title";
import {
  queryKeys,
  usePortfolioAccount,
  usePortfolioAccountHistory,
  usePortfolioHoldingReviews,
  useRefreshPortfolioQuotes,
} from "@/lib/hooks";
import { api } from "@/lib/api";
import type {
  FillDraft,
  FillFormProps,
  IdentityCorrectionFormProps,
  IdentityDraft,
} from "./portfolio-manual-write-tools";
import type { DecisionWritebackPanelProps } from "./portfolio-decision-writeback";
import { type NoFillItem } from "./portfolio-writeback-utils";
import type {
  PortfolioAccountAction,
  PortfolioAccountActivityTablesProps,
  PortfolioAccountPositionTablesProps,
  PortfolioAccountSummaryProps,
} from "./portfolio-account-overview";
import { numericValue, suggestedSellQty } from "./portfolio-utils";

const PortfolioAccountSummary = dynamic<PortfolioAccountSummaryProps>(
  () =>
    import("./portfolio-account-overview").then(
      (module) => module.PortfolioAccountSummary,
    ),
  {
    ssr: false,
    loading: () => (
      <>
        <SkeletonBlock className="mb-6 h-28 w-full" />
        <SkeletonBlock className="mb-7 h-36 w-full" />
        <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <SkeletonBlock key={index} className="h-24 w-full" />
          ))}
        </section>
      </>
    ),
  },
);

const PortfolioAccountPositionTables =
  dynamic<PortfolioAccountPositionTablesProps>(
    () =>
      import("./portfolio-account-overview").then(
        (module) => module.PortfolioAccountPositionTables,
      ),
    {
      ssr: false,
      loading: () => <SkeletonBlock className="mb-7 h-48 w-full" />,
    },
  );

const PortfolioAccountActivityTables =
  dynamic<PortfolioAccountActivityTablesProps>(
    () =>
      import("./portfolio-account-overview").then(
        (module) => module.PortfolioAccountActivityTables,
      ),
    {
      ssr: false,
      loading: () => (
        <>
          <SkeletonBlock className="mb-7 h-36 w-full" />
          <SkeletonBlock className="mb-7 h-36 w-full" />
        </>
      ),
    },
  );

const PortfolioResearchUniverse = dynamic(
  () =>
    import("./portfolio-research-universe").then(
      (module) => module.PortfolioResearchUniverse,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <SkeletonBlock key={index} className="h-48 w-full" />
        ))}
      </div>
    ),
  },
);

const PortfolioLatestDecisions = dynamic(
  () =>
    import("./portfolio-latest-decisions").then(
      (module) => module.PortfolioLatestDecisions,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-40 w-full" />,
  },
);

const PortfolioHoldingWorkbench = dynamic(
  () =>
    import("./portfolio-holding-workbench").then(
      (module) => module.PortfolioHoldingWorkbench,
    ),
  {
    ssr: false,
    loading: () => (
      <Panel
        title="今日持仓动作"
        eyebrow="Holding script desk"
        className="surface-card p-4"
        action={<Badge tone="info">加载中</Badge>}
      >
        <div className="grid gap-3">
          <SkeletonBlock className="h-24 w-full" />
          <SkeletonBlock className="h-44 w-full" />
        </div>
      </Panel>
    ),
  },
);

const PortfolioLedgerTools = dynamic(
  () =>
    import("./portfolio-ledger-tools").then(
      (module) => module.PortfolioLedgerTools,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="mb-7 h-40 w-full" />,
  },
);

const PortfolioFillForm = dynamic<FillFormProps>(
  () =>
    import("./portfolio-manual-write-tools").then((module) => module.FillForm),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-40 w-full" />,
  },
);

const PortfolioIdentityCorrectionForm = dynamic<IdentityCorrectionFormProps>(
  () =>
    import("./portfolio-manual-write-tools").then(
      (module) => module.IdentityCorrectionForm,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-32 w-full" />,
  },
);

const PortfolioDecisionWritebackPanel = dynamic<DecisionWritebackPanelProps>(
  () =>
    import("./portfolio-decision-writeback").then(
      (module) => module.DecisionWritebackPanel,
    ),
  {
    ssr: false,
    loading: () => <SkeletonBlock className="h-56 w-full" />,
  },
);

type NextStepAction = PortfolioAccountAction;

function todayStr(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function scrollToSection(id: string) {
  if (typeof document === "undefined") return;
  document
    .getElementById(id)
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function isLedgerToolTarget(value: string) {
  return ["mode-switch", "cash-adjust", "reconcile-form"].includes(value);
}

function PortfolioPageContent() {
  const queryClient = useQueryClient();
  const portfolio = usePortfolioAccount();
  const refreshQuotes = useRefreshPortfolioQuotes();
  const [accountRefreshing, setAccountRefreshing] = useState(false);
  const data = portfolio.data;
  const quoteStatus = data?.market_quotes;
  const [holdingReviewsEnabled, setHoldingReviewsEnabled] = useState(false);
  const hasOpenPositions = Boolean(data?.account.open_positions.length);
  const holdingReviews = usePortfolioHoldingReviews({
    enabled: Boolean(hasOpenPositions && holdingReviewsEnabled),
  });
  const [researchUniverseOpened, setResearchUniverseOpened] = useState(false);
  const [latestDecisionsOpened, setLatestDecisionsOpened] = useState(false);
  const [ledgerToolsOpened, setLedgerToolsOpened] = useState(false);
  const accountHistory = usePortfolioAccountHistory({
    enabled: Boolean(ledgerToolsOpened),
  });
  const [manualWriteToolsOpened, setManualWriteToolsOpened] = useState(false);
  const [decisionWritebackOpened, setDecisionWritebackOpened] = useState(false);
  const [pendingLedgerTarget, setPendingLedgerTarget] = useState("");
  const [optimisticNoFill, setOptimisticNoFill] = useState<NoFillItem | null>(
    null,
  );
  const [fillDraft, setFillDraft] = useState<FillDraft | null>(null);
  const [identityDraft, setIdentityDraft] = useState<IdentityDraft | null>(
    null,
  );
  const defaultTradeDate = useMemo(
    () => data?.expected_trade_date || data?.trade_date || todayStr(),
    [data?.expected_trade_date, data?.trade_date],
  );
  const ledgerHistoryPending = Boolean(
    ledgerToolsOpened &&
      data?.account_history_deferred &&
      !accountHistory.data &&
      (accountHistory.isLoading || accountHistory.isFetching),
  );
  const noFillItems = useMemo(() => {
    const serverItems = data?.account.no_fill_intents || [];
    if (!optimisticNoFill) {
      return serverItems;
    }

    const exists = serverItems.some(
      (item) =>
        item.trade_date === optimisticNoFill.trade_date &&
        item.intent_key === optimisticNoFill.intent_key &&
        item.reason === optimisticNoFill.reason &&
        item.ts === optimisticNoFill.ts,
    );
    return exists ? serverItems : [...serverItems, optimisticNoFill];
  }, [data?.account.no_fill_intents, optimisticNoFill]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return undefined;
    }

    const syncLocationState = () => {
      const hashTarget = window.location.hash.replace(/^#/, "");
      if (isLedgerToolTarget(hashTarget)) {
        setLedgerToolsOpened(true);
        setPendingLedgerTarget(hashTarget);
      }
      if (hashTarget === "manual-fill" || hashTarget === "holding-correction") {
        setManualWriteToolsOpened(true);
      }
      if (hashTarget === "decision-writeback") {
        setDecisionWritebackOpened(true);
      }
    };
    syncLocationState();
    window.addEventListener("popstate", syncLocationState);
    window.addEventListener("hashchange", syncLocationState);
    return () => {
      window.removeEventListener("popstate", syncLocationState);
      window.removeEventListener("hashchange", syncLocationState);
    };
  }, []);

  useEffect(() => {
    if (!ledgerToolsOpened || !pendingLedgerTarget) {
      return undefined;
    }

    let cancelled = false;
    let attempts = 0;
    function tryScroll() {
      if (cancelled) {
        return;
      }
      const target = document.getElementById(pendingLedgerTarget);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        setPendingLedgerTarget("");
        return;
      }
      attempts += 1;
      if (attempts < 20) {
        window.setTimeout(tryScroll, 100);
      }
    }

    window.setTimeout(tryScroll, 0);
    return () => {
      cancelled = true;
    };
  }, [ledgerToolsOpened, pendingLedgerTarget]);

  useEffect(() => {
    if (!optimisticNoFill || !data?.account.no_fill_intents?.length) {
      return;
    }

    const exists = data.account.no_fill_intents.some(
      (item) =>
        item.trade_date === optimisticNoFill.trade_date &&
        item.intent_key === optimisticNoFill.intent_key &&
        item.reason === optimisticNoFill.reason &&
        item.ts === optimisticNoFill.ts,
    );

    if (exists) {
      setOptimisticNoFill(null);
    }
  }, [data?.account.no_fill_intents, optimisticNoFill]);

  function handleAccountWorkflowAction(
    action: NextStepAction,
    targetId: string,
  ) {
    if (action === "review") {
      scrollToSection(targetId);
      return;
    }
    setLedgerToolsOpened(true);
    setPendingLedgerTarget(targetId);
  }

  async function refreshAccountBook() {
    setAccountRefreshing(true);
    try {
      const refreshTasks: Array<Promise<unknown>> = [
        queryClient.fetchQuery({
          queryKey: queryKeys.portfolioAccount,
          queryFn: () => api.getPortfolioAccount({ fresh: true }),
        }),
      ];

      if (ledgerToolsOpened) {
        refreshTasks.push(
          queryClient.fetchQuery({
            queryKey: queryKeys.portfolioAccountHistory,
            queryFn: () =>
              api.getPortfolioAccount({
                fresh: true,
                history: true,
              }),
          }),
        );
      }
      if (hasOpenPositions && holdingReviewsEnabled) {
        refreshTasks.push(
          queryClient.fetchQuery({
            queryKey: queryKeys.portfolioHoldingReviews,
            queryFn: () => api.getPortfolioHoldingReviews({ fresh: true }),
          }),
        );
      }

      await Promise.allSettled(refreshTasks);
    } finally {
      setAccountRefreshing(false);
    }
  }

  const accountBookRefreshing =
    accountRefreshing ||
    portfolio.isFetching ||
    accountHistory.isFetching ||
    holdingReviews.isFetching;

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow={data?.expected_trade_date || todayStr()}
          title="账户控制台"
          summary="这里分为真实账户执行区、决策执行回写区和研究自选股区。研究名单仅供跟踪，不代表真实持仓。"
          icon={WalletCards}
          badge={data?.account.mode_label || "研究态"}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-2 text-[12px] text-[var(--accent)]"
                onClick={() => refreshQuotes.mutate()}
                disabled={refreshQuotes.isPending}
              >
                <RefreshCw
                  size={14}
                  className={refreshQuotes.isPending ? "animate-spin" : ""}
                />
                刷新行情
              </button>
              <button
                type="button"
                className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
                onClick={() => void refreshAccountBook()}
                disabled={accountBookRefreshing}
              >
                <RefreshCw
                  size={14}
                  className={accountBookRefreshing ? "animate-spin" : ""}
                />
                刷新账本
              </button>
            </div>
          }
        />

        {quoteStatus?.enabled ? (
          <div className="mb-4 flex flex-wrap items-center gap-2 text-[12px] text-[var(--text-tertiary)]">
            <Badge
              tone={
                quoteStatus.status === "ok"
                  ? "buy"
                  : quoteStatus.status === "partial"
                    ? "watch"
                    : "risk"
              }
            >
              {quoteStatus.status === "ok"
                ? "行情已更新"
                : quoteStatus.status === "partial"
                  ? "行情部分更新"
                  : "行情未更新"}
            </Badge>
            <span>
              {quoteStatus.message ? `${quoteStatus.message} ｜ ` : ""}
              {quoteStatus.provider || "-"} ｜ {quoteStatus.updated_at || "-"}
              {quoteStatus.missing_codes?.length
                ? ` ｜缺 ${quoteStatus.missing_codes.join("、")}`
                : ""}
            </span>
          </div>
        ) : null}
        {refreshQuotes.isError ? (
          <div className="mb-4 text-[12px] text-[var(--tone-risk)]">
            {refreshQuotes.error instanceof Error
              ? refreshQuotes.error.message
              : "行情刷新失败"}
          </div>
        ) : null}

        {portfolio.isError ? (
          <ErrorState
            message="账户数据暂不可用"
            onRetry={() => void portfolio.refetch()}
          />
        ) : null}

        {data?.readiness?.trust_level ? (
          <DeferredTrustBanner
            trust={data.readiness.trust_level}
            readiness={data.readiness}
            className="mb-4"
          />
        ) : null}

        <PortfolioAccountSummary
          data={data}
          loading={portfolio.isLoading && !data}
          onSelectAction={handleAccountWorkflowAction}
        />

        <section className="mb-7">
          {data && (!hasOpenPositions || holdingReviewsEnabled) ? (
            <PortfolioHoldingWorkbench
              data={data}
              holdingData={holdingReviews.data}
              isLoading={holdingReviews.isLoading || holdingReviews.isFetching}
              isError={holdingReviews.isError}
              onRetry={() => void holdingReviews.refetch()}
              onRefreshQuotes={() => refreshQuotes.mutate()}
              isRefreshingQuotes={refreshQuotes.isPending}
              onRecordSell={(review) => {
                const targetQty = suggestedSellQty(review);
                const targetPrice = numericValue(review.current_price);
                setFillDraft({
                  code: String(review.code || ""),
                  name: String(review.name || ""),
                  side: "sell",
                  tradeDate: defaultTradeDate,
                  brokerRef: `持仓动作：${review.action_label || "退出动作"}`,
                  qty: targetQty || undefined,
                  price: targetPrice !== null ? targetPrice : undefined,
                });
                setManualWriteToolsOpened(true);
                window.setTimeout(() => scrollToSection("manual-fill"), 0);
              }}
              onAmendIdentity={(review) => {
                const reviewName = String(review.name || "");
                const reviewCode = String(review.code || "");
                setIdentityDraft({
                  fromCode: reviewCode,
                  toCode: reviewCode,
                  name:
                    reviewName &&
                    reviewName.toLowerCase() !== reviewCode.toLowerCase()
                      ? reviewName
                      : "",
                  reason: "录入代码修正",
                });
                setManualWriteToolsOpened(true);
                window.setTimeout(
                  () => scrollToSection("holding-correction"),
                  0,
                );
              }}
            />
          ) : data ? (
            <Panel
              title="今日持仓动作"
              eyebrow="Holding script desk"
              className="surface-card p-4"
              action={
                <Badge tone={hasOpenPositions ? "watch" : "info"}>
                  {hasOpenPositions ? "按需加载" : "暂无持仓"}
                </Badge>
              }
            >
              {hasOpenPositions ? (
                <div
                  data-testid="portfolio-holding-reviews-gate"
                  className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-[var(--text-primary)]">
                        持仓复核按需加载
                      </div>
                      <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                        首屏先展示账户、持仓和账本入口；需要 AI
                        持仓动作、卖出建议和证据归因时再读取完整复核。
                      </p>
                    </div>
                    <button
                      type="button"
                      className="focus-ring inline-flex h-9 items-center gap-1.5 rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 text-[12px] text-[var(--accent)]"
                      onClick={() => setHoldingReviewsEnabled(true)}
                    >
                      <ClipboardCheck size={13} />
                      加载持仓复核
                    </button>
                  </div>
                </div>
              ) : (
                <EmptyState>
                  当前没有真实持仓。买入成交写入账本后，这里会生成持仓动作。
                </EmptyState>
              )}
            </Panel>
          ) : (
            <SkeletonBlock className="h-52 w-full" />
          )}
        </section>

        <section id="holding-correction" className="mb-7 scroll-mt-6">
          <Panel
            title="持仓更正"
            eyebrow="Correction"
            className="surface-card p-4"
            action={
              identityDraft ? (
                <Badge tone="warning">{identityDraft.fromCode}</Badge>
              ) : (
                <Badge tone="info">待选择</Badge>
              )
            }
          >
            {manualWriteToolsOpened ? (
              <PortfolioIdentityCorrectionForm
                draft={identityDraft}
                onSaved={() => {
                  void portfolio.refetch();
                  if (hasOpenPositions && holdingReviewsEnabled) {
                    void holdingReviews.refetch();
                  }
                }}
              />
            ) : (
              <div
                data-testid="portfolio-manual-write-tools-gate"
                className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-[var(--text-primary)]">
                      手动写入工具按需加载
                    </div>
                    <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                      普通打开持仓页时先不加载成交补录和代码更正表单；需要写账本或修正持仓身份时再展开。
                    </p>
                  </div>
                  <button
                    type="button"
                    className="focus-ring inline-flex h-9 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-3 text-[12px] text-[var(--text-primary)]"
                    onClick={() => setManualWriteToolsOpened(true)}
                  >
                    <ClipboardCheck size={13} />
                    加载手动写入
                  </button>
                </div>
              </div>
            )}
          </Panel>
        </section>

        <PortfolioAccountPositionTables data={data} />

        {data?.account.open_positions.length ? (
          <section className="mb-7">
            <Panel
              title="持仓最近 Prism 决策"
              eyebrow="Decision Ledger"
              className="surface-card p-4"
            >
              <details
                data-testid="portfolio-latest-decisions-gate"
                open={latestDecisionsOpened}
                className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)]"
                onToggle={(event) =>
                  setLatestDecisionsOpened(event.currentTarget.open)
                }
              >
                <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
                  <div className="min-w-0">
                    <div className="text-[13px] font-medium text-[var(--text-primary)]">
                      按需核对持仓最近决策
                    </div>
                    <div className="mt-1 line-clamp-1 text-[11px] text-[var(--text-tertiary)]">
                      默认不读取 Decision Ledger
                      recent；展开后按持仓代码匹配最近一次 Prism 判断。
                    </div>
                  </div>
                  <Badge tone={latestDecisionsOpened ? "positive" : "watch"}>
                    {latestDecisionsOpened ? "已加载" : "按需加载"}
                  </Badge>
                </summary>
                <div className="border-t border-[var(--border-subtle)] p-4">
                  {latestDecisionsOpened ? (
                    <PortfolioLatestDecisions
                      positions={data.account.open_positions}
                    />
                  ) : (
                    <EmptyState>展开后读取持仓最近 Prism 决策。</EmptyState>
                  )}
                </div>
              </details>
            </Panel>
          </section>
        ) : null}

        <PortfolioAccountActivityTables data={data} noFillItems={noFillItems} />

        <section className="mb-7">
          {data && ledgerToolsOpened ? (
            <>
              {ledgerHistoryPending ? (
                <div className="mb-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                  正在补齐模式切换和对账历史...
                </div>
              ) : null}
              {accountHistory.isError && !accountHistory.data ? (
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-md border border-[color-mix(in_srgb,var(--tone-risk)_30%,transparent)] bg-[color-mix(in_srgb,var(--tone-risk)_6%,transparent)] px-3 py-2 text-[12px] text-[var(--tone-risk)]">
                  <span>账本历史暂不可用，工具区先使用当前账户状态。</span>
                  <button
                    type="button"
                    className="focus-ring rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[11px] text-[var(--text-primary)]"
                    onClick={() => void accountHistory.refetch()}
                  >
                    重试
                  </button>
                </div>
              ) : null}
              <PortfolioLedgerTools
                data={accountHistory.data || data}
                defaultTradeDate={defaultTradeDate}
              />
            </>
          ) : data ? (
            <Panel
              title="账本工具"
              eyebrow="Ledger tools"
              className="surface-card p-4"
              action={<Badge tone="watch">按需加载</Badge>}
            >
              <div
                data-testid="portfolio-ledger-tools-gate"
                className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-[var(--text-primary)]">
                      账本写入工具按需加载
                    </div>
                    <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                      默认先看账户状态、持仓、成交和未成交记录；需要切换模式、现金调整或券商对账时再打开工具区。
                    </p>
                  </div>
                  <button
                    type="button"
                    className="focus-ring inline-flex h-9 items-center gap-1.5 rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 text-[12px] text-[var(--accent)]"
                    onClick={() => setLedgerToolsOpened(true)}
                  >
                    <ShieldCheck size={13} />
                    加载账本工具
                  </button>
                </div>
              </div>
            </Panel>
          ) : (
            <SkeletonBlock className="mb-7 h-40 w-full" />
          )}
        </section>

        <section id="manual-fill" className="mb-7 scroll-mt-6">
          <Panel
            title="补录券商成交"
            eyebrow="Write to ledger"
            className="surface-card p-4"
          >
            {manualWriteToolsOpened ? (
              <PortfolioFillForm
                defaultTradeDate={defaultTradeDate}
                draft={fillDraft}
              />
            ) : (
              <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4 text-[12px] leading-5 text-[var(--text-secondary)]">
                手动成交补录已按需加载。需要录入券商成交时，请在上方“持仓更正”区点击加载手动写入，或从持仓复核里的卖出建议进入。
              </div>
            )}
          </Panel>
        </section>

        <section id="decision-writeback" className="mb-3 scroll-mt-6">
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
            决策执行回写区
          </div>
        </section>

        <section className="mb-7">
          <Panel
            title="单票决策执行回写"
            eyebrow="Decision writeback"
            className="surface-card p-4"
            action={
              decisionWritebackOpened ? (
                <Badge tone="warning">已加载</Badge>
              ) : (
                <Badge tone="info">等待上下文</Badge>
              )
            }
          >
            {decisionWritebackOpened ? (
              <PortfolioDecisionWritebackPanel
                defaultTradeDate={defaultTradeDate}
                noFillIntents={noFillItems}
                onWritebackSuccess={({ noFillItem }) => {
                  if (noFillItem) {
                    setOptimisticNoFill(noFillItem);
                  }
                  void portfolio.refetch();
                  if (hasOpenPositions && holdingReviewsEnabled) {
                    void holdingReviews.refetch();
                  }
                }}
              />
            ) : (
              <div
                data-testid="portfolio-decision-writeback-gate"
                className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-[var(--text-primary)]">
                      决策执行回写按需加载
                    </div>
                    <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                      普通持仓查看先不加载单票回写表单；从个股页记录执行结果，或需要补写未成交/继续观察/放弃时再展开。
                    </p>
                  </div>
                  <button
                    type="button"
                    className="focus-ring inline-flex h-9 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-3 text-[12px] text-[var(--text-primary)]"
                    onClick={() => setDecisionWritebackOpened(true)}
                  >
                    <ClipboardCheck size={13} />
                    加载回写
                  </button>
                </div>
              </div>
            )}
          </Panel>
        </section>

        <section className="mb-7">
          <details
            className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)]"
            open={researchUniverseOpened}
            onToggle={(event) =>
              setResearchUniverseOpened(event.currentTarget.open)
            }
          >
            <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
                  Research universe
                </div>
                <div className="mt-1 text-lg font-semibold text-[var(--text-primary)]">
                  研究自选股（不是真持仓）
                </div>
              </div>
              <Badge tone="info">按需加载</Badge>
            </summary>
            <div className="border-t border-[var(--border-subtle)] p-4">
              <p className="mb-3 text-[12px] text-[var(--text-tertiary)]">
                下方为研究态的自选股（watchlist），不是真持仓。真账户视角请看上方
                &ldquo;持仓&rdquo; 区块。
              </p>
              {researchUniverseOpened ? (
                <PortfolioResearchUniverse />
              ) : (
                <EmptyState>展开后加载研究自选股。</EmptyState>
              )}
            </div>
          </details>
        </section>
      </div>
    </main>
  );
}

export function PortfolioWorkspace() {
  return <PortfolioPageContent />;
}
