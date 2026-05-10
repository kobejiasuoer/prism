"use client";

import { AlertCircle, Check, ChevronRight, FileDown, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import type { CSSProperties } from "react";

import { Badge } from "@/components/badge";
import {
  useRuns,
  useRefreshStatus,
  useTodayData,
} from "@/lib/hooks";
import type {
  QualityCardData,
  ReadinessIssue,
  ReadinessMode,
  ReadinessPayload,
  RefreshStatus,
  RiskRow,
  RunItem,
  SourceCardData,
  TodayActionItem,
  TodayCommandHeroAction,
  TodayActionDisplayValue,
} from "@/lib/types";
import { asText, cn, stockCodeFromTitle, stockNameFromTitle, toneColor } from "@/lib/utils";

function formatTime(value?: string) {
  if (!value) {
    return "-";
  }
  const timeMatch = value.match(/\d{2}:\d{2}/);
  if (timeMatch) {
    return timeMatch[0];
  }
  if (value.length >= 16 && value[10] === "T") {
    return value.slice(11, 16);
  }
  return value;
}

function sourceIsFresh(source: SourceCardData) {
  return source.available !== false && !source.stale && source.value !== "-";
}

const READINESS_MODE_COPY: Record<ReadinessMode, {
  badge: string;
  title: string;
  tone: string;
  iconColor: string;
  bg: string;
  border: string;
}> = {
  live_ready: {
    badge: "Live Ready",
    title: "数据已对齐当日，可按页面执行",
    tone: "positive",
    iconColor: "var(--positive)",
    bg: "color-mix(in srgb, var(--positive) 8%, transparent)",
    border: "color-mix(in srgb, var(--positive) 30%, transparent)",
  },
  shadow_only: {
    badge: "Shadow Only",
    title: "仅作影子盘观察，不可按页面真钱执行",
    tone: "warning",
    iconColor: "var(--warning)",
    bg: "color-mix(in srgb, var(--warning) 10%, transparent)",
    border: "color-mix(in srgb, var(--warning) 35%, transparent)",
  },
  blocked: {
    badge: "Blocked",
    title: "数据未就绪：请先把核心链路刷到当日",
    tone: "negative",
    iconColor: "var(--negative)",
    bg: "color-mix(in srgb, var(--negative) 10%, transparent)",
    border: "color-mix(in srgb, var(--negative) 40%, transparent)",
  },
};

const TASK_TITLES: Record<string, string> = {
  watchlist_refresh: "自选股全流程刷新",
  aggressive: "进攻型早盘扫描",
  midday_refresh: "午盘新增 + 复核",
  command_brief: "总控简报",
};

const AUTO_REASON_COPY: Record<string, string> = {
  cooldown: "冷却未结束",
  running: "同类任务运行中",
  outside_auto_window: "非自动刷新窗口",
  manifest_not_stale: "manifest 未 stale/expired",
  no_manifest_trigger: "没有 manifest 触发原因",
  provider_failure: "provider 失败",
  fallback_not_allowed: "fallback 不可进 live_small",
  live_small_not_allowed: "不允许 live_small",
  manifest_missing: "manifest 缺失",
  freshness_stale: "manifest stale",
  freshness_expired: "manifest expired",
  trade_date_mismatch: "交易日不匹配",
};

function autoReasonCopy(value: string) {
  return AUTO_REASON_COPY[value] || value;
}

const ACTION_STATE_COPY: Record<TodayActionDisplayValue, {
  label: string;
  button: string;
  tone: string;
  done: boolean;
}> = {
  pending: {
    label: "待处理",
    button: "处理",
    tone: "watch",
    done: false,
  },
  done: {
    label: "已完成",
    button: "查看结果",
    tone: "positive",
    done: true,
  },
  watch: {
    label: "继续观察中",
    button: "查看观察",
    tone: "watch",
    done: true,
  },
  skip: {
    label: "已放弃",
    button: "查看原因",
    tone: "risk",
    done: true,
  },
  no_fill: {
    label: "未成交，已记录",
    button: "查看未成交",
    tone: "hold",
    done: true,
  },
};

function actionStateValue(item: TodayActionItem): TodayActionDisplayValue {
  return item.display_state?.value || item.decision?.value || "pending";
}

function actionStateCopy(item: TodayActionItem) {
  return ACTION_STATE_COPY[actionStateValue(item)] || ACTION_STATE_COPY.pending;
}

function actionItemLink(item: TodayActionItem) {
  const linkFields = item as TodayActionItem & {
    href?: string;
    action_url?: string;
    detail_url?: string;
  };
  return [linkFields.href, linkFields.action_url, linkFields.detail_url, linkFields.url].find(
    (value) => typeof value === "string" && value.trim() && value.trim() !== "#",
  );
}

function actionHref(item: TodayActionItem, options: { portfolioForCompleted?: boolean } = {}) {
  const state = actionStateValue(item);
  const code = stockCodeFromTitle(item.title) || stockCodeFromTitle(item.key);
  if (options.portfolioForCompleted && ["done", "skip", "no_fill"].includes(state)) {
    return `/portfolio?intent_key=${encodeURIComponent(item.key)}#decision-writeback`;
  }
  return code ? `/stock/${code}` : actionItemLink(item) || "#";
}

function firstPendingAction(items: TodayActionItem[]) {
  return items.find((item) => actionStateValue(item) === "pending");
}

function dataLooksStale(readiness?: ReadinessPayload, sourceCards: SourceCardData[] = []) {
  return Boolean(
    readiness?.stale_count ||
      readiness?.blockers?.length ||
      sourceCards.some((source) => source.stale),
  );
}

function ReadinessBanner({ readiness }: { readiness?: ReadinessPayload }) {
  if (!readiness) {
    return null;
  }
  const copy = READINESS_MODE_COPY[readiness.readiness_mode] ?? READINESS_MODE_COPY.blocked;
  const issues: ReadinessIssue[] =
    readiness.readiness_mode === "blocked"
      ? readiness.blockers
      : readiness.readiness_mode === "shadow_only"
        ? [...readiness.warnings, ...readiness.blockers]
        : [];
  const Icon = readiness.readiness_mode === "live_ready" ? ShieldCheck : ShieldAlert;
  const recommendedTaskName = readiness.recommended_tasks?.[0];
  const recommendedTaskTitle = recommendedTaskName
    ? TASK_TITLES[recommendedTaskName] || recommendedTaskName
    : null;

  return (
    <section
      data-od-id="readiness-banner"
      className="rounded-md border px-4 py-3"
      style={{ background: copy.bg, borderColor: copy.border }}
    >
      <div className="flex flex-wrap items-start gap-3">
        <Icon size={20} style={{ color: copy.iconColor, marginTop: 2 }} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={copy.tone}>{copy.badge}</Badge>
            <span className="text-[12px] text-[var(--text-tertiary)]">
              预期交易日 {readiness.expected_trade_date} · 数据交易日 {readiness.data_trade_date || "-"}
              {readiness.session?.label ? ` · ${readiness.session.label}` : null}
            </span>
          </div>
          <div className="mt-1 text-[14px] font-medium text-[var(--text-primary)]">{copy.title}</div>
          {issues.length ? (
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[12px] leading-5 text-[var(--text-secondary)]">
              {issues.slice(0, 4).map((issue) => (
                <li key={`${issue.code}-${issue.label}`}>
                  <span className="font-medium text-[var(--text-primary)]">{issue.label}：</span>
                  {issue.message}
                </li>
              ))}
              {issues.length > 4 ? (
                <li className="text-[var(--text-tertiary)]">…还有 {issues.length - 4} 条，请在质检面板查看完整列表。</li>
              ) : null}
            </ul>
          ) : null}
          {recommendedTaskTitle && readiness.readiness_mode !== "live_ready" ? (
            <div className="mt-2 text-[12px] text-[var(--text-secondary)]">
              建议下一步运行：
              <Link href="/settings" className="ml-1 font-medium underline">{recommendedTaskTitle}</Link>
              （/settings 任务运行）
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function TodayPrimaryCTA({
  readiness,
  items,
  sourceCards,
}: {
  readiness?: ReadinessPayload;
  items: TodayActionItem[];
  sourceCards: SourceCardData[];
}) {
  const pending = firstPendingAction(items);
  const allHandled = items.length > 0 && !pending;
  const stale = dataLooksStale(readiness, sourceCards);
  const blocked = readiness?.readiness_mode === "blocked" || (stale && readiness?.readiness_mode !== "shadow_only");
  const shadowOnly = readiness?.readiness_mode === "shadow_only" || readiness?.session?.is_trading_day === false;
  let title = "今天数据可用，先处理下一条待决策动作";
  let detail = "真钱执行：允许，但必须遵守仓位纪律";
  let button = "处理下一只股票";
  let href = pending ? actionHref(pending) : "#action-queue";
  let tone = "positive";

  if (shadowOnly) {
    title = "今天仅影子盘观察，不可真钱执行";
    detail = "真钱执行：禁止";
    button = pending ? "查看下一条影子盘动作" : "查看今日动作队列";
    href = pending ? actionHref(pending) : "#action-queue";
    tone = "warning";
  } else if (allHandled) {
    title = "今日动作已闭环";
    detail = readiness?.readiness_mode === "live_ready"
      ? "真钱执行：按仓位纪律复核，不新增临时动作"
      : "真钱执行：禁止；今日只查看处理结果";
    button = "查看处理结果";
    href = "/portfolio";
    tone = "positive";
  } else if (blocked) {
    title = "数据未就绪，先恢复数据链路";
    detail = "真钱执行：禁止";
    button = "去刷新数据";
    href = "/settings";
    tone = "negative";
  } else if (!pending) {
    title = "今日动作已闭环";
    detail = "真钱执行：按仓位纪律复核，不新增临时动作";
    button = "查看处理结果";
    href = "/portfolio";
    tone = "positive";
  }

  return (
    <section className="war-inline-note" data-od-id="today-primary-cta">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={tone}>今日第一步</Badge>
            <span className="text-[12px] font-medium text-[var(--text-primary)]">{title}</span>
          </div>
          <div className={cn("mt-1 text-[12px]", tone === "positive" ? "buy-text" : tone === "negative" ? "negative-text" : "watch-text")}>
            {detail}
          </div>
        </div>
        <Link href={href} className="focus-ring war-check is-on shrink-0">
          {button}
          <ChevronRight size={14} />
        </Link>
      </div>
    </section>
  );
}

function AutoRefreshBanner({ status }: { status?: RefreshStatus }) {
  if (!status?.auto_refresh) {
    return null;
  }
  const decision = status.auto_refresh;
  const blocked = decision.blocked_reasons || [];
  const reasons = blocked.length ? blocked : decision.reason_codes || [];
  const tone = decision.triggered ? "positive" : blocked.length ? "warning" : "info";

  return (
    <section className="war-inline-note">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={tone}>{decision.triggered ? "已自动补刷" : "自动刷新状态"}</Badge>
        <span className="text-[12px] text-[var(--text-tertiary)]">
          建议 {status.recommended_task?.title || status.recommended_task?.task_name || "-"} · 冷却 {status.cooldown?.remaining_seconds || 0}s
          {status.cooldown?.next_allowed_at ? ` · 下次 ${status.cooldown.next_allowed_at}` : ""}
        </span>
      </div>
      <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
        {decision.summary || "等待策略判断。"}
      </div>
      {reasons.length ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {reasons.slice(0, 5).map((reason) => (
            <Badge key={reason} tone={blocked.length ? "warning" : "info"}>{autoReasonCopy(reason)}</Badge>
          ))}
        </div>
      ) : null}
      {status.last_auto_refresh ? (
        <div className="mt-2 text-[11px] text-[var(--text-tertiary)]">
          最近自动刷新：{status.last_auto_refresh.ts || "-"} · {status.last_auto_refresh.reason || "-"}
        </div>
      ) : null}
    </section>
  );
}

function HeroSkeleton() {
  return (
    <div className="grid animate-pulse gap-3 xl:grid-cols-[minmax(0,1fr)_260px]">
      <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
        <div className="h-3 w-36 rounded bg-[var(--bg-tertiary)]" />
        <div className="mt-4 h-8 max-w-2xl rounded bg-[var(--bg-tertiary)]" />
        <div className="mt-4 h-4 max-w-3xl rounded bg-[var(--bg-tertiary)]" />
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <div className="h-20 rounded bg-[var(--bg-tertiary)]" />
          <div className="h-20 rounded bg-[var(--bg-tertiary)]" />
          <div className="h-20 rounded bg-[var(--bg-tertiary)]" />
        </div>
      </div>
      <div className="h-64 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]" />
    </div>
  );
}

function fallbackHeroActions(): TodayCommandHeroAction[] {
  return [
    {
      label: "1 · 先做",
      title: "处理旧仓风险",
      detail: "先把优先持仓里的止损与减仓动作完成。",
      tone: "sell",
      tier: "act_now",
    },
    {
      label: "2 · 等触发",
      title: "只盯高一致性候选",
      detail: "没有二次确认前，不把观察池候选升级为新仓。",
      tone: "watch",
      tier: "wait_trigger",
    },
    {
      label: "3 · 禁止",
      title: "不追高不补亏",
      detail: "弱环境未转正，控制总仓位和单笔亏损。",
      tone: "avoid",
      tier: "avoid",
    },
  ];
}

function ToneRail({ tone = "watch" }: { tone?: string }) {
  return <span className="war-tone-rail" style={{ backgroundColor: toneColor(tone) }} />;
}

function BriefAction({ action, index }: { action: TodayCommandHeroAction; index: number }) {
  const tone = action.tone || (index === 0 ? "sell" : index === 1 ? "watch" : "avoid");
  const step = index + 1;

  return (
    <div className="war-brief-action" style={{ "--accent": toneColor(tone) } as CSSProperties}>
      <span className="war-step mono">{String(step).padStart(2, "0")}</span>
      <div className="min-w-0">
        <div className="war-action-label">{action.label || action.tier || "执行"}</div>
        <div className="war-action-title">{action.title}</div>
        <p>{action.detail}</p>
      </div>
    </div>
  );
}

function DecisionBrief({
  title,
  summary,
  status,
  gateLabel,
  cap,
  mainTheme,
  actions,
  sourceOk,
  sourceTotal,
  briefLive,
  readinessMode,
  qualityTimely,
  qualityTotal,
}: {
  title: string;
  summary: string;
  status: string;
  gateLabel: string;
  cap: string;
  mainTheme: string;
  actions: TodayCommandHeroAction[];
  sourceOk: number;
  sourceTotal: number;
  briefLive: boolean;
  readinessMode: ReadinessMode;
  qualityTimely: number;
  qualityTotal: number;
}) {
  const liveTone = readinessMode === "live_ready" ? "positive" : readinessMode === "shadow_only" ? "warning" : "negative";
  const liveLabel =
    readinessMode === "live_ready" ? "允许真钱" : readinessMode === "shadow_only" ? "影子盘" : "禁止";
  const sourceTone = readinessMode === "live_ready" ? "buy-text" : "watch-text";
  const qualityTone = qualityTimely === qualityTotal && qualityTotal > 0 ? "buy-text" : "watch-text";
  const qualityLabel = qualityTotal > 0 ? `${qualityTimely}/${qualityTotal}` : "-";

  return (
    <section className="war-brief" data-od-id="decision-summary">
      <div className="war-brief-main">
        <div className="war-eyebrow-row">
          <span className="war-eyebrow">Trading Decision</span>
          <Badge tone={liveTone}>{status}</Badge>
        </div>
        <h2>{title}</h2>
        <p className="war-brief-summary">{summary}</p>
        <div className="war-brief-actions">
          {actions.map((action, index) => (
            <BriefAction key={`${action.title}-${index}`} action={action} index={index} />
          ))}
        </div>
      </div>

      <aside className="war-gate-card" data-od-id="gate-state">
        <div className="war-gate-top">
          <span>交易阀门</span>
          <Badge tone="watch">{gateLabel}</Badge>
        </div>
        <div className="war-cap mono">{cap}</div>
        <p>弱环境下只做验证，不扩大仓位。主线：{mainTheme}。</p>
        <div className="war-gate-meter">
          <span style={{ width: cap === "0成" ? "8%" : "50%" }} />
        </div>
        <div className="war-mini-grid">
          <div>
            <span>简报</span>
            <strong className={briefLive ? "buy-text" : "watch-text"}>{briefLive ? "当日可用" : "回退"}</strong>
          </div>
          <div>
            <span>数据源</span>
            <strong className={sourceOk === sourceTotal && sourceTotal > 0 ? "buy-text" : "watch-text"}>
              {sourceOk}/{sourceTotal || "-"}
            </strong>
          </div>
          <div>
            <span>质检</span>
            <strong className={qualityTone}>{qualityLabel}</strong>
          </div>
          <div>
            <span>交易可用</span>
            <strong className={readinessMode === "live_ready" ? "buy-text" : readinessMode === "blocked" ? "negative-text" : "watch-text"}>
              {liveLabel}
            </strong>
          </div>
        </div>
      </aside>
    </section>
  );
}

function SignalStrip({
  items,
}: {
  items: Array<{ label: string; value: string; tone?: string }>;
}) {
  return (
    <section className="war-signals" data-od-id="metric-strip">
      {items.map((item) => (
        <div key={item.label} className="war-signal">
          <span>{item.label}</span>
          <strong className="mono" style={{ color: item.tone ? toneColor(item.tone) : undefined }}>
            {item.value}
          </strong>
        </div>
      ))}
    </section>
  );
}

function ActionStack({
  items,
  counts,
  loading,
}: {
  items: TodayActionItem[];
  counts?: {
    total: number;
    pending: number;
    done: number;
    watch: number;
    skip: number;
    no_fill?: number;
    last_updated?: string;
  };
  loading: boolean;
}) {
  const handled = (counts?.done || 0) + (counts?.watch || 0) + (counts?.skip || 0) + (counts?.no_fill || 0);
  return (
    <section id="action-queue" className="war-stack" data-od-id="action-queue">
      <header className="war-section-head">
        <div>
          <span className="war-eyebrow">Action Stack</span>
          <h2>今天只看这几件事</h2>
        </div>
        <div className="war-counts">
          <span>待处理 {counts?.pending ?? items.length}</span>
          <span>已处理 {handled}/{counts?.total ?? items.length}</span>
          {counts?.no_fill ? <span>未成交 {counts.no_fill}</span> : null}
        </div>
      </header>

      {loading && !items.length ? (
        <div className="war-action-list">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="war-action-card war-skeleton">
              <span />
              <div />
              <div />
            </div>
          ))}
        </div>
      ) : items.length ? (
        <div className="war-action-list">
          {items.slice(0, 7).map((item, index) => (
            <WarActionCard
              key={item.key}
              item={item}
              index={index}
            />
          ))}
        </div>
      ) : (
        <div className="war-empty">当前没有必须处理的动作。</div>
      )}
    </section>
  );
}

function WarActionCard({
  item,
  index,
}: {
  item: TodayActionItem;
  index: number;
}) {
  const state = actionStateValue(item);
  const stateCopy = actionStateCopy(item);
  const checked = stateCopy.done;
  const code = stockCodeFromTitle(item.title);
  const name = stockNameFromTitle(item.title);
  const href = actionHref(item);
  const resultHref = actionHref(item, { portfolioForCompleted: true });
  const tone = stateCopy.done ? stateCopy.tone : item.tone || item.decision?.tone || (index === 0 ? "sell" : "watch");
  const freshnessLabel =
    item.display_state?.updated_at ||
    item.freshness?.label ||
    item.freshness?.value ||
    item.freshness?.status ||
    item.confidence?.label ||
    item.group_title ||
    "数据可用";

  return (
    <article className={cn("war-action-card", checked ? "is-done" : "")}>
      <ToneRail tone={tone} />
      <div className="war-action-rank mono">{String(index + 1).padStart(2, "0")}</div>
      <div className="war-action-body">
        <Link href={href} className="war-stock-link">
          <span>{name}</span>
          {code ? <em>{code}</em> : null}
        </Link>
        <p>{item.detail || item.foot || item.status || "等待系统给出下一步。"}</p>
        <div className="war-action-meta">
          <Badge tone={stateCopy.tone}>{item.display_state?.label || stateCopy.label}</Badge>
          <span>{item.source || item.group_title || freshnessLabel}</span>
          {state === "no_fill" && item.display_state?.reason ? <span>{item.display_state.reason}</span> : null}
        </div>
      </div>
      <div className="war-action-control">
        {state === "pending" ? (
          href !== "#" ? (
            <Link href={href} className="focus-ring war-check">
              {stateCopy.button}
              <ChevronRight size={14} />
            </Link>
          ) : (
            <button type="button" className="focus-ring war-check" disabled>
              暂无详情
            </button>
          )
        ) : (
          <Link href={resultHref} className="focus-ring war-check is-on">
            <Check size={14} />
            {stateCopy.button}
          </Link>
        )}
        <Link href={href} className="war-action-time">
          <span>{freshnessLabel}</span>
          <ChevronRight size={14} />
        </Link>
      </div>
    </article>
  );
}

function IntelligenceRail({
  risks,
  sources,
  runs,
  runsLoading,
  readiness,
  qualityCards,
  actionTotal,
  riskTotal,
  staleTotal,
  watchlistTotal,
  candidateTotal,
  freshCandidates,
  confirmed,
}: {
  risks: RiskRow[];
  sources: SourceCardData[];
  runs: RunItem[];
  runsLoading: boolean;
  readiness?: ReadinessPayload;
  qualityCards?: QualityCardData[];
  actionTotal: number;
  riskTotal: number;
  staleTotal: number;
  watchlistTotal?: number;
  candidateTotal?: number;
  freshCandidates?: number;
  confirmed?: number;
}) {
  const fresh = sources.filter(sourceIsFresh).length;
  const links = [
    { label: "持仓", href: "/portfolio", count: watchlistTotal },
    { label: "观察池", href: "/discovery", count: candidateTotal },
    { label: "午盘", href: "/discovery", count: freshCandidates },
    { label: "复盘", href: "/review", count: confirmed },
  ];

  const qualityList = qualityCards ?? [];
  const qualityTimely = qualityList.filter((card) => card.timely === true).length;
  const qualityStatusLabel =
    qualityList.length === 0
      ? "loading"
      : qualityTimely === qualityList.length
        ? "ready"
        : `${qualityTimely}/${qualityList.length}`;
  const qualityStatusClass =
    qualityList.length > 0 && qualityTimely === qualityList.length ? "buy-text" : "watch-text";

  return (
    <aside className="war-rail" data-od-id="risk-alerts">
      <section className="war-rail-card">
        <div className="war-rail-head">
          <span>风险雷达</span>
          <Badge tone="sell">先看</Badge>
        </div>
        {risks.length ? (
          risks.slice(0, 3).map((risk, index) => (
            <div key={`${risk.title}-${index}`} className="war-rail-row">
              <ToneRail tone={risk.tone || (index === 0 ? "sell" : "watch")} />
              <div>
                <strong>{risk.title}</strong>
                <p>{risk.reason || risk.trigger || risk.risk || "继续复核链路状态。"}</p>
              </div>
            </div>
          ))
        ) : (
          <p className="war-muted">风险链路等待同步。</p>
        )}
      </section>

      <section className="war-rail-card">
        <div className="war-rail-head">
          <span>数据新鲜度</span>
          <strong className={fresh === sources.length && sources.length > 0 ? "buy-text" : "watch-text"}>{fresh}/{sources.length || "-"}</strong>
        </div>
        {sources.length ? (
          sources.slice(0, 4).map((source) => (
            <div key={source.key || source.label} className="war-source-line">
              <span>{source.label}</span>
              <strong className={sourceIsFresh(source) ? "buy-text" : "watch-text"}>
                {source.age_label || source.value || "-"}
              </strong>
            </div>
          ))
        ) : (
          <p className="war-muted">暂无数据源状态。</p>
        )}
      </section>

      <section className="war-rail-card">
        <div className="war-rail-head">
          <span>质检</span>
          <strong className={qualityStatusClass}>{qualityStatusLabel}</strong>
        </div>
        {qualityList.length ? (
          qualityList.slice(0, 3).map((card) => (
            <div key={card.key || card.title} className="war-source-line">
              <span>{card.title}</span>
              <strong className={card.timely === true ? "buy-text" : "watch-text"}>
                {card.timely === true ? "timely" : card.stale_reasons?.[0] || card.status || "stale"}
              </strong>
            </div>
          ))
        ) : (
          <>
            <div className="war-source-line"><span>actions</span><strong>{actionTotal}</strong></div>
            <div className="war-source-line"><span>risks</span><strong>{riskTotal}</strong></div>
            <div className="war-source-line"><span>stale</span><strong>{staleTotal ? "visible" : "clear"}</strong></div>
          </>
        )}
        {readiness ? (
          <div className="war-source-line">
            <span>readiness</span>
            <strong className={readiness.ready ? "buy-text" : readiness.readiness_mode === "blocked" ? "negative-text" : "watch-text"}>
              {readiness.readiness_mode}
            </strong>
          </div>
        ) : null}
      </section>

      <section className="war-rail-card">
        <div className="war-rail-head">
          <span>运行记录</span>
          <strong>{runs.length || 0}</strong>
        </div>
        {runsLoading && !runs.length ? (
          <p className="war-muted">读取中...</p>
        ) : runs.length ? (
          runs.slice(0, 3).map((run) => (
            <div key={run.run_id || `${run.task_name}-${run.started_at}`} className="war-run-line">
              <span>{run.title || run.task_name || "任务"}</span>
              <strong>{formatTime(run.finished_at || run.started_at)}</strong>
            </div>
          ))
        ) : (
          <p className="war-muted">暂无运行记录。</p>
        )}
      </section>

      <section className="war-link-grid">
        {links.map((item) => (
          <Link key={`${item.label}-${item.href}`} href={item.href} className="focus-ring">
            <span>{item.label}</span>
            <strong>{item.count ?? "-"}</strong>
          </Link>
        ))}
      </section>
    </aside>
  );
}

export default function CommandCenterPage() {
  const today = useTodayData();
  const runsQuery = useRuns();
  const refreshStatus = useRefreshStatus("today", true, { auto: true });
  const data = today.data;
  const hero = data?.command_hero;
  const readiness = data?.readiness;
  const readinessMode: ReadinessMode = readiness?.readiness_mode ?? "blocked";
  const displayDate =
    readiness?.expected_trade_date ||
    data?.display_date ||
    data?.generated_at?.slice(0, 10) ||
    data?.trade_date ||
    hero?.trade_date;
  const sourceCards = data?.source_cards ?? [];
  const freshSourceCount = sourceCards.filter(sourceIsFresh).length;
  const staleSourceCount = sourceCards.filter((source) => !sourceIsFresh(source)).length;
  const qualityCards = data?.quality_cards ?? [];
  const qualityTimely = readiness
    ? readiness.quality_freshness.filter((item) => item.timely).length
    : qualityCards.filter((card) => card.timely === true).length;
  const qualityTotal = readiness ? readiness.quality_freshness.length : qualityCards.length;
  const summaryCards = data?.summary_cards?.length ? data.summary_cards : data?.radar_cards ?? [];
  const metricCards =
    summaryCards.length
      ? summaryCards.slice(0, 4)
      : [
          { label: "持仓优先", value: data?.counts?.watchlist_priority ?? "-", detail: "优先处理持仓", tone: "sell" },
          { label: "观察候选", value: data?.counts?.candidate_total ?? "-", detail: "观察池候选", tone: "watch" },
          { label: "午盘新增", value: data?.counts?.fresh_candidates ?? "-", detail: "午盘新增观察", tone: "positive" },
          {
            label: "质检状态",
            value: qualityTotal ? `${qualityTimely}/${qualityTotal}` : "-",
            detail: "数据源可用",
            tone: qualityTimely === qualityTotal && qualityTotal > 0 ? "positive" : "warning",
          },
        ];
  const actionItems = data?.action_queue?.items ?? [];
  const counts = data?.action_queue?.counts;
  const riskRows: RiskRow[] =
    data?.risk_rows?.length
      ? data.risk_rows
      : data?.hero?.context_note
        ? [
            {
              title: data.brief_is_live ? "总控已同步" : "实时链路判断",
              action: data.hero.gate_label,
              reason: data.hero.context_note,
              tone: data.brief_is_live ? "positive" : "warning",
            },
          ]
        : [];
  const actions = hero?.actions?.length ? hero.actions.slice(0, 3) : fallbackHeroActions();
  const tradeDateLabel = readiness?.expected_trade_date
    ? `${readiness.expected_trade_date}${readiness.data_trade_date && readiness.data_trade_date !== readiness.expected_trade_date ? ` ←→ ${readiness.data_trade_date}` : ""}`
    : asText(displayDate, "待同步");
  const tapeItems = [
    {
      label: "持仓优先",
      value: asText(data?.counts?.watchlist_priority ?? metricCards[0]?.value),
      tone: "sell",
    },
    {
      label: "观察候选",
      value: asText(data?.counts?.candidate_total ?? metricCards[1]?.value),
      tone: "watch",
    },
    {
      label: "午盘新增",
      value: asText(data?.counts?.fresh_candidates ?? metricCards[2]?.value),
      tone: "positive",
    },
    {
      label: "已确认",
      value: asText(data?.counts?.confirmed ?? counts?.done),
      tone: "hold",
    },
    {
      label: "交易日",
      value: tradeDateLabel,
    },
  ];

  // status copy in the hero card: NEVER show "live" wording when readiness is
  // not green, even if the user has stale data sitting in the brief.
  const briefLiveSafe = Boolean(data?.brief_is_live && readiness?.ready);
  const heroStatus = readiness
    ? readinessMode === "live_ready"
      ? hero?.source_state || "总控已同步"
      : readinessMode === "shadow_only"
        ? "影子盘观察"
        : "数据未就绪"
    : hero?.source_state || data?.hero?.gate_label || "实时链路";

  return (
    <main className="war-room">
      <div className="war-room-inner">
        <header className="war-topbar" data-od-id="topbar">
          <div>
            <div className="war-eyebrow">Command Center</div>
            <h1>指挥中心</h1>
          </div>
          <div className="war-top-actions">
            <div className="war-command" role="search" aria-label="命令栏提示">
              <span>搜索股票 / 跳转页面 / 执行快捷动作</span>
              <kbd className="prism-kbd">⌘K</kbd>
            </div>
            <button
              type="button"
              className="focus-ring war-tool-btn"
              onClick={() => void today.refetch()}
            >
              <RefreshCw size={14} className={today.isFetching ? "animate-spin" : ""} />
              刷新
            </button>
            <button
              type="button"
              className="focus-ring war-tool-btn"
              onClick={() => window.print()}
            >
              <FileDown size={14} />
              导出简报
            </button>
          </div>
        </header>

        {today.isError ? (
          <div className="war-error">
            <AlertCircle size={17} className="mt-0.5 shrink-0 text-[var(--warning)]" />
            <div className="min-w-0 flex-1">
              <div className="font-medium text-[var(--text-primary)]">后端数据暂不可用</div>
              <div className="mt-1">指挥中心骨架已加载，FastAPI 启动后会自动重新获取 `/api/today`。</div>
            </div>
            <button
              type="button"
              className="focus-ring rounded-md border border-[var(--border-subtle)] px-2.5 py-1 text-[12px] text-[var(--text-primary)]"
              onClick={() => void today.refetch()}
            >
              重试
            </button>
          </div>
        ) : null}

        {readiness ? <ReadinessBanner readiness={readiness} /> : null}
        <TodayPrimaryCTA readiness={readiness} items={actionItems} sourceCards={sourceCards} />

        <div className="war-layout" data-od-id="command-center-v1">
          <div className="war-primary">
            {today.isLoading && !data ? (
              <HeroSkeleton />
            ) : (
              <DecisionBrief
                title={hero?.title || data?.hero?.title || "先把旧仓风险降下来，新仓只等一个确认触发"}
                summary={hero?.summary || data?.hero?.summary || "今天不是找更多机会，而是按纪律先处理旧仓风险。"}
                status={heroStatus}
                gateLabel={data?.hero?.gate_label || hero?.source_state || "防守试错"}
                cap={asText(data?.hero?.position_cap, "0成")}
                mainTheme={asText(data?.hero?.main_theme, "AI + 机器人")}
                actions={actions}
                sourceOk={freshSourceCount}
                sourceTotal={sourceCards.length}
                briefLive={briefLiveSafe}
                readinessMode={readinessMode}
                qualityTimely={qualityTimely}
                qualityTotal={qualityTotal}
              />
            )}

            <SignalStrip items={tapeItems} />

            <ActionStack
              items={actionItems}
              counts={counts}
              loading={today.isLoading}
            />
          </div>

          <IntelligenceRail
            risks={riskRows}
            sources={sourceCards}
            runs={runsQuery.data?.runs ?? []}
            runsLoading={runsQuery.isLoading}
            readiness={readiness}
            qualityCards={qualityCards}
            actionTotal={counts?.total ?? actionItems.length}
            riskTotal={riskRows.length}
            staleTotal={staleSourceCount}
            watchlistTotal={data?.counts?.watchlist_total}
            candidateTotal={data?.counts?.candidate_total}
            freshCandidates={data?.counts?.fresh_candidates}
            confirmed={data?.counts?.confirmed}
          />
        </div>
        <details className="war-inline-note">
          <summary className="cursor-pointer text-[12px] font-medium text-[var(--text-primary)]">
            数据健康 / 工程状态
          </summary>
          <div className="mt-3">
            <AutoRefreshBanner status={refreshStatus.data} />
          </div>
        </details>
      </div>
    </main>
  );
}
