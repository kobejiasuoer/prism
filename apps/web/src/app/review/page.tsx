"use client";

import { ArrowRight, BarChart3, BookOpenCheck, ExternalLink, LineChart, RefreshCw, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Badge } from "@/components/badge";
import { DataCard, EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { EvidencePanel } from "@/components/evidence-panel";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { RiskAlert } from "@/components/risk-alert";
import { useReview, useReviewDetail } from "@/lib/hooks";
import type {
  BasicCard,
  MetricCardData,
  ReviewComparisonPanel,
  ReviewData,
  ReviewDetailData,
  ReviewResearchPanel,
  ReviewSelectorGroup,
  RiskRow,
  SourceCardData,
  Tone,
} from "@/lib/types";
import { cn } from "@/lib/utils";

function cleanParam(value: string | null) {
  return value?.trim() || undefined;
}

function valueTone(value?: string | number, fallback: Tone | string = "positive") {
  return String(value ?? "").trim().startsWith("-") ? "risk" : fallback;
}

function reviewHref(url?: string | null) {
  if (!url) {
    return "";
  }
  return url.startsWith("/api/review/detail") ? url.replace("/api/review/detail", "/review") : url;
}

function metricTone(card: MetricCardData, index: number) {
  return card.tone || valueTone(card.value, index === 0 ? "info" : "positive");
}

function sourceCardsFromMetrics(cards?: MetricCardData[]): SourceCardData[] {
  return (cards || []).map((card) => ({
    label: card.label,
    value: String(card.value ?? "-"),
    detail: card.detail || card.note,
    available: card.value !== undefined && card.value !== "-",
  }));
}

function MetricGrid({
  cards,
  limit,
  empty,
}: {
  cards?: MetricCardData[];
  limit?: number;
  empty?: string;
}) {
  const visible = (cards || []).slice(0, limit || cards?.length || 0);
  if (!visible.length) {
    return empty ? <EmptyState>{empty}</EmptyState> : null;
  }
  return (
    <>
      {visible.map((card, index) => {
        const body = <MetricCard {...card} tone={metricTone(card, index)} />;
        const href = reviewHref(card.detail_url);
        return href ? (
          <Link key={`${card.label}-${index}`} href={href} className="focus-ring block h-full">
            {body}
          </Link>
        ) : (
          <div key={`${card.label}-${index}`}>{body}</div>
        );
      })}
    </>
  );
}

function DetailCta({ href, label = "查看明细" }: { href?: string | null; label?: string }) {
  const normalized = reviewHref(href);
  if (!normalized) {
    return null;
  }
  return (
    <Link
      href={normalized}
      className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 py-1.5 text-[12px] text-[var(--text-secondary)] hover:border-[var(--border-default)] hover:text-[var(--text-primary)]"
    >
      {label}
      <ArrowRight size={13} />
    </Link>
  );
}

function ToplineActions({ links }: { links?: Array<{ label?: string; href?: string }> }) {
  const items = (links || []).filter((link) => link.label && link.href).slice(0, 3);
  if (!items.length) {
    return null;
  }
  return (
    <div className="mt-4 flex flex-wrap gap-2">
      {items.map((link) => (
        <a
          key={`${link.label}-${link.href}`}
          href={link.href}
          className="focus-ring inline-flex min-h-9 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)] transition-colors hover:border-[var(--border-default)] hover:text-[var(--text-primary)]"
        >
          {link.label}
          <ArrowRight size={13} />
        </a>
      ))}
    </div>
  );
}

function ReadingCompass({ data }: { data?: ReviewData }) {
  const compass = data?.reading_compass || [];
  const miniCompare = data?.mini_compare || [];
  const ctaLinks = data?.topline?.cta_links;
  if (!compass.length && !miniCompare.length) {
    return null;
  }

  const primary = compass[0];
  const rest = compass.slice(1, 4);

  return (
    <section className="mb-7 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)]">
      <div className="surface-card p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Badge tone="info">阅读顺序</Badge>
          <Badge tone="warning">先结论后拆解</Badge>
        </div>
        <div className="flex items-start gap-3">
          <BookOpenCheck size={18} className="mt-1 shrink-0 text-[var(--info)]" />
          <div className="min-w-0">
            <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
              {primary?.label || "当前结论"}
            </div>
            <h2 className="mt-1 text-[clamp(18px,2vw,24px)] font-semibold leading-tight text-[var(--text-primary)]">
              {primary?.value || data?.topline?.verdict_title || "先看复盘结论"}
            </h2>
            <p className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
              {primary?.detail || data?.topline?.verdict_summary || "先判断环境是否支持行动，再下钻到分组和证据。"}
            </p>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-3">
          {rest.map((item) => (
            <div
              key={item.label}
              className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2"
            >
              <div className="text-[11px] text-[var(--text-tertiary)]">{item.label}</div>
              <div className="mt-1 line-clamp-2 text-[13px] font-medium text-[var(--text-primary)]">{item.value}</div>
              <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
                {item.detail || item.note || "-"}
              </div>
            </div>
          ))}
        </div>
        <ToplineActions links={ctaLinks} />
      </div>

      <Panel title="窗口快照" eyebrow="Window Snapshot">
        <div className="surface-card p-4">
          <div className="mb-3 flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
            <LineChart size={15} className="text-[var(--text-tertiary)]" />
            <span>{data?.comparison_note || "只看同一口径的窗口变化，不直接等同可执行收益。"}</span>
          </div>
          <div className="grid grid-cols-1 gap-2">
            {miniCompare.slice(0, 3).map((card, index) => {
              const metric = {
                label: card.label || card.title || "指标",
                value: card.value ?? "-",
                detail: card.detail || card.note,
                tone: card.tone,
              };
              return <MetricCard key={`${metric.label}-${index}`} {...metric} tone={metricTone(metric, index)} />;
            })}
          </div>
        </div>
      </Panel>
    </section>
  );
}

function SelectorGroups({ groups }: { groups?: ReviewSelectorGroup[] }) {
  if (!groups?.length) {
    return null;
  }
  return (
    <Panel title="研究窗口切换" eyebrow="Windows">
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {groups.map((group) => (
          <div key={group.title} className="surface-card p-4">
            <div className="mb-3">
              <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">窗口</div>
              <h3 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{group.title}</h3>
              {group.subtitle ? (
                <p className="mt-2 text-[12px] leading-5 text-[var(--text-tertiary)]">{group.subtitle}</p>
              ) : null}
            </div>
            <div className="flex flex-wrap gap-2">
              {group.options.map((option) => (
                <Link
                  key={`${group.title}-${option.label}-${option.url}`}
                  href={reviewHref(option.url)}
                  className={cn(
                    "focus-ring rounded-full border px-3 py-1.5 text-[12px] transition-colors",
                    option.active
                      ? "border-[var(--info)] bg-[color-mix(in_srgb,var(--info)_12%,transparent)] text-[var(--text-primary)]"
                      : "border-[var(--border-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-default)] hover:text-[var(--text-primary)]",
                  )}
                >
                  {option.label}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function MethodologyNotice({ data }: { data?: ReviewData }) {
  return (
    <section className="mb-7 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_7%,transparent)] p-4">
      <div className="flex items-start gap-3">
        <ShieldAlert size={17} className="mt-0.5 shrink-0 text-[var(--warning)]" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <strong className="text-[13px] text-[var(--text-primary)]">研究回看口径，不是实盘撮合回测</strong>
            <Badge tone="warning">research-only</Badge>
            <Badge tone="risk">execution-realistic: false</Badge>
          </div>
          <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
            当前复盘读取本地 research backfill 报告，统计 AI/Scan 历史样本的次日、3日、5日原始收益与扣摩擦后净收益。它不处理停牌、涨跌停不可成交、滑点、废单、部分成交或真实订单队列；只能用于校准环境和规则，不能直接当成可执行收益。
          </p>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-[var(--text-tertiary)]">
            <span>生成：{data?.generated_at || "-"}</span>
            <span>基准：{data?.source_cards?.find((card) => card.label === "基准研究")?.detail || "-"}</span>
            <span>对比：{data?.source_cards?.find((card) => card.label === "对比窗口")?.detail || "-"}</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function ReviewDetailSection({
  detail,
  loading,
  error,
  onRetry,
}: {
  detail?: ReviewDetailData;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
}) {
  if (error) {
    return (
      <section className="mb-7">
        <ErrorState message="复盘明细暂不可用" onRetry={onRetry} />
      </section>
    );
  }
  if (loading && !detail) {
    return (
      <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <MetricSkeleton key={index} />
        ))}
      </section>
    );
  }
  if (!detail) {
    return null;
  }

  return (
    <section className="mb-7 space-y-6">
      <div className="surface-card p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {detail.hero?.eyebrow ? <Badge tone="info">{detail.hero.eyebrow}</Badge> : null}
          <Badge tone="watch">{detail.label}</Badge>
        </div>
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">{detail.hero?.title || "复盘明细"}</h2>
        {detail.hero?.summary ? (
          <p className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">{detail.hero.summary}</p>
        ) : null}
        {detail.comparison_note || detail.missing_note ? (
          <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-tertiary)]">
            {detail.missing_note || detail.comparison_note}
          </div>
        ) : null}
      </div>

      <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {(detail.summary_cards || []).map((card, index) => (
          <MetricCard key={`${card.label}-${index}`} {...card} tone={metricTone(card, index)} />
        ))}
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {(detail.comparison_panels || []).map((panel) => (
          <ComparisonPanel key={panel.title} panel={panel} />
        ))}
      </section>

      <SelectorGroups groups={detail.selector_groups} />
    </section>
  );
}

function ComparisonPanel({ panel }: { panel: ReviewComparisonPanel }) {
  const artifactCard: BasicCard | undefined = panel.artifact_path
    ? {
        title: `${panel.title}原始报告`,
        path: panel.artifact_path,
        url: panel.artifact_url,
      }
    : undefined;

  return (
    <Panel
      title={panel.title}
      eyebrow={panel.subtitle}
      action={
        panel.artifact_url ? (
          <a
            href={panel.artifact_url}
            target="_blank"
            rel="noreferrer"
            className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            原始报告
            <ExternalLink size={13} />
          </a>
        ) : null
      }
    >
      <div className="surface-card p-4">
        {panel.cards?.length ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {panel.cards.map((card, index) => (
              <MetricCard key={`${panel.title}-${card.label}-${index}`} {...card} tone={metricTone(card, index)} />
            ))}
          </div>
        ) : (
          <EmptyState>{panel.empty || "当前窗口没有这条分组。"}</EmptyState>
        )}
        {artifactCard ? (
          <div className="mt-3 text-[11px] text-[var(--text-tertiary)]">
            来源：{artifactCard.path}
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

function ResearchPanelCard({ panel }: { panel: ReviewResearchPanel }) {
  return (
    <div className="surface-card p-4">
      <div className="mb-3">
        {panel.eyebrow ? <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">{panel.eyebrow}</div> : null}
        <h3 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{panel.title}</h3>
        {panel.summary ? <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">{panel.summary}</p> : null}
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {(panel.metric_cards || []).slice(0, 6).map((card, index) => (
          <MetricCard key={`${panel.title}-${card.label}-${index}`} {...card} tone={metricTone(card, index)} />
        ))}
      </div>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {(panel.groups || []).slice(0, 4).map((group) => (
          <div key={`${panel.title}-${group.title}`} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <strong className="truncate text-[12px] text-[var(--text-primary)]">{group.title}</strong>
              <Badge tone="info">{group.entries?.length || 0}</Badge>
            </div>
            <div className="flex flex-col gap-2">
              {(group.entries || []).slice(0, 3).map((entry) => (
                <div key={`${group.title}-${entry.label}`} className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-[12px] text-[var(--text-secondary)]">{entry.label}</div>
                    {entry.summary ? <div className="mt-0.5 line-clamp-2 text-[11px] text-[var(--text-tertiary)]">{entry.summary}</div> : null}
                  </div>
                  <DetailCta href={entry.detail_url} label="看" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      {panel.artifact_url ? (
        <a
          href={panel.artifact_url}
          target="_blank"
          rel="noreferrer"
          className="focus-ring mt-4 inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          打开原始报告
          <ExternalLink size={13} />
        </a>
      ) : null}
    </div>
  );
}

function LifecycleGroups({ data }: { data?: ReviewData }) {
  const groups = data?.lifecycle_groups || [];
  if (!groups.length) {
    return null;
  }
  return (
    <Panel title="变化样本" eyebrow="Lifecycle Detail">
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {groups.map((group) => (
          <div key={group.key} className="surface-card p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="truncate text-sm font-semibold text-[var(--text-primary)]">{group.title}</h3>
                {group.subtitle ? <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">{group.subtitle}</p> : null}
              </div>
              <Badge tone={group.key === "exited" ? "risk" : "positive"}>{group.count}</Badge>
            </div>
            <div className="grid grid-cols-1 gap-2">
              {(group.cards || []).slice(0, 4).map((card) => (
                <div key={`${group.key}-${card.code}-${card.name}`} className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-[12px] font-medium text-[var(--text-primary)]">
                        {card.name} {card.code ? <span className="mono text-[var(--text-tertiary)]">{card.code}</span> : null}
                      </div>
                      {card.copy ? <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--text-secondary)]">{card.copy}</div> : null}
                    </div>
                    {card.status ? <Badge tone={card.tone}>{card.status}</Badge> : null}
                  </div>
                  {card.metrics?.length ? (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {card.metrics.slice(0, 3).map((metric) => (
                        <span key={metric} className="mono rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[10px] text-[var(--text-tertiary)]">
                          {metric}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))}
              {!group.cards?.length ? <EmptyState>{group.empty || "暂无样本。"}</EmptyState> : null}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function RulesPanel({ rows }: { rows?: RiskRow[] }) {
  return (
    <Panel title="校准规则" eyebrow="Rules">
      <div className="flex flex-col gap-2">
        {(rows || []).length ? (
          rows?.slice(0, 5).map((row, index) => (
            <div key={`${row.title}-${index}`} className="flex flex-col gap-2">
              <RiskAlert row={row} />
              <DetailCta href={row.url} />
            </div>
          ))
        ) : (
          <EmptyState>暂无校准规则。</EmptyState>
        )}
      </div>
    </Panel>
  );
}

function ChangeLogPanel({ data }: { data?: ReviewData }) {
  const log = data?.change_log;
  const entries = log?.entries || [];
  if (!entries.length) {
    return (
      <Panel title="变化日志" eyebrow="Change Log">
        <EmptyState>{log?.empty || "暂无可比变化。"}</EmptyState>
      </Panel>
    );
  }

  return (
    <Panel title="变化日志" eyebrow="Change Log">
      <div className="surface-card p-4">
        {log?.note ? <p className="mb-3 text-[12px] leading-5 text-[var(--text-secondary)]">{log.note}</p> : null}
        <div className="flex flex-col gap-2">
          {entries.map((entry) => {
            const row = (
              <div className="flex min-h-[58px] items-center gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 transition-colors hover:border-[var(--border-default)]">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[12px] font-medium text-[var(--text-primary)]">{entry.title}</div>
                  <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">{entry.detail}</div>
                </div>
                <Badge tone={entry.tone}>{entry.change}</Badge>
                {entry.url ? <ArrowRight size={14} className="shrink-0 text-[var(--text-tertiary)]" /> : null}
              </div>
            );
            const href = reviewHref(entry.url);
            return href ? (
              <Link key={entry.title} href={href} className="focus-ring block">
                {row}
              </Link>
            ) : (
              <div key={entry.title}>{row}</div>
            );
          })}
        </div>
      </div>
    </Panel>
  );
}

function ReviewPageContent() {
  const searchParams = useSearchParams();
  const baseline = cleanParam(searchParams.get("baseline"));
  const windowId = cleanParam(searchParams.get("window"));
  const section = cleanParam(searchParams.get("section"));
  const label = cleanParam(searchParams.get("label"));
  const review = useReview({ baseline, window: windowId });
  const detail = useReviewDetail({ section, label, baseline, window: windowId });
  const data = review.data;
  const detailData = detail.data;
  const showingDetail = Boolean(section && label);

  const detailSources = sourceCardsFromMetrics(detailData?.source_cards);
  const pageSources = showingDetail && detailSources.length ? detailSources : data?.source_cards;
  const pageArtifacts = showingDetail && detailData?.artifacts?.length ? detailData.artifacts : data?.artifacts;

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow="Review"
          title={showingDetail ? detailData?.hero?.title || "复盘明细" : data?.topline?.verdict_title || data?.hero?.title || "复盘"}
          summary={
            showingDetail
              ? detailData?.hero?.summary || "同一分组下对比基准窗口和对比窗口。"
              : data?.topline?.verdict_summary || data?.hero?.summary || "环境仪表、校准规则、基准对比和变化回放。"
          }
          icon={BarChart3}
          badge={showingDetail ? detailData?.hero?.eyebrow || "分组明细" : data?.topline?.verdict_badge || "环境结论"}
          actions={
            <div className="flex flex-wrap gap-2">
              {showingDetail ? (
                <Link
                  href={data?.links?.self || "/review"}
                  className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                >
                  回到摘要
                </Link>
              ) : null}
              <button
                type="button"
                className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
                onClick={() => {
                  void review.refetch();
                  if (showingDetail) {
                    void detail.refetch();
                  }
                }}
              >
                <RefreshCw size={14} className={review.isFetching || detail.isFetching ? "animate-spin" : ""} />
                刷新
              </button>
            </div>
          }
        />

        {review.isError ? <ErrorState message="复盘数据暂不可用" onRetry={() => void review.refetch()} /> : null}
        <MethodologyNotice data={data} />
        {!showingDetail ? <ReadingCompass data={data} /> : null}

        {showingDetail ? (
          <ReviewDetailSection
            detail={detailData}
            loading={detail.isLoading}
            error={detail.isError}
            onRetry={() => void detail.refetch()}
          />
        ) : null}

        {!showingDetail && data?.topline?.meta_pills?.length ? (
          <section className="mb-7 flex flex-wrap gap-2">
            {data.topline.meta_pills.map((pill) => (
              <Badge key={`${pill.label}-${pill.value}`} tone={valueTone(pill.value)}>
                {pill.label} {pill.value}
              </Badge>
            ))}
          </section>
        ) : null}

        {!showingDetail ? (
          <>
            <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {review.isLoading && !data
                ? Array.from({ length: 4 }).map((_, index) => <MetricSkeleton key={index} />)
                : <MetricGrid cards={data?.summary_cards} limit={4} />}
            </section>

            <section className="mb-7 grid grid-cols-1 gap-3 xl:grid-cols-4">
              {review.isLoading && !data
                ? Array.from({ length: 4 }).map((_, index) => <SkeletonBlock key={index} className="h-44 w-full" />)
                : (data?.verdict_cards || []).slice(0, 4).map((card, index) => (
                    <DataCard key={`${card.title}-${index}`} card={card} href={reviewHref(card.detail_url)} />
                  ))}
            </section>
          </>
        ) : null}

        {!showingDetail ? (
          <section id="review-control" className="mb-7 scroll-mt-6">
            <SelectorGroups groups={data?.selector_groups} />
          </section>
        ) : null}

        {!showingDetail ? (
          <section id="review-changes" className="mb-7 grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
            <RulesPanel rows={data?.action_rules} />
            <ChangeLogPanel data={data} />
          </section>
        ) : null}

        {!showingDetail ? (
          <section className="mb-7 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Panel title="基准 vs 对比窗口" eyebrow="Compare">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <MetricGrid cards={data?.comparison_cards} limit={4} empty="暂无对比数据。" />
              </div>
            </Panel>

            <Panel title="可信度总开关" eyebrow="Confidence">
              <div className="surface-card p-4">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Badge tone={data?.confidence_switch?.tone}>{data?.confidence_switch?.label || data?.confidence_switch?.status || "等待校验"}</Badge>
                </div>
                <p className="text-[12px] leading-5 text-[var(--text-secondary)]">
                  {data?.confidence_switch?.summary || data?.confidence_switch?.note || "暂无可信度摘要。"}
                </p>
                <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {(data?.confidence_switch?.metrics || []).slice(0, 4).map((card, index) => (
                    <MetricCard key={`${card.label}-${index}`} {...card} tone="info" />
                  ))}
                </div>
              </div>
            </Panel>
          </section>
        ) : null}

        {!showingDetail && data?.research_panels?.length ? (
          <section className="mb-7">
            <Panel title="研究拆解" eyebrow="Research">
              <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                {data.research_panels.map((panel) => (
                  <ResearchPanelCard key={`${panel.eyebrow}-${panel.title}`} panel={panel} />
                ))}
              </div>
            </Panel>
          </section>
        ) : null}

        {!showingDetail ? (
          <section className="mb-7 grid grid-cols-1 gap-6 xl:grid-cols-[400px_minmax(0,1fr)]">
            <Panel title="变化回放" eyebrow="Lifecycle">
              <div className="surface-card p-4">
                {data?.lifecycle_note ? <p className="mb-4 text-[12px] leading-5 text-[var(--text-secondary)]">{data.lifecycle_note}</p> : null}
                <div className="grid grid-cols-1 gap-2">
                  <MetricGrid cards={data?.lifecycle_cards} limit={4} empty="暂无变化回放。" />
                </div>
              </div>
            </Panel>
            <LifecycleGroups data={data} />
          </section>
        ) : null}

        <section id="review-evidence" className="grid grid-cols-1 gap-6">
          <EvidencePanel
            page="review"
            mode="readonly"
            sources={pageSources}
            artifacts={pageArtifacts}
            title="来源校验"
            eyebrow="Freshness"
          />
        </section>
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
            <SkeletonBlock className="mb-7 h-28 w-full" />
            <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {Array.from({ length: 4 }).map((_, index) => (
                <MetricSkeleton key={index} />
              ))}
            </section>
          </div>
        </main>
      }
    >
      <ReviewPageContent />
    </Suspense>
  );
}
