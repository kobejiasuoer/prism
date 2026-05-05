"use client";

import { AlertCircle, Check, ChevronRight, FileDown, LoaderCircle, RefreshCw } from "lucide-react";
import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import { Badge } from "@/components/badge";
import {
  useRuns,
  useTodayData,
  useUpdateTodayActionDecision,
} from "@/lib/hooks";
import type {
  DecisionValue,
  RiskRow,
  RunItem,
  SourceCardData,
  TodayActionItem,
  TodayCommandHeroAction,
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
}) {
  return (
    <section className="war-brief" data-od-id="decision-summary">
      <div className="war-brief-main">
        <div className="war-eyebrow-row">
          <span className="war-eyebrow">Live Decision</span>
          <Badge tone={briefLive ? "positive" : "watch"}>{status}</Badge>
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
            <strong className={briefLive ? "buy-text" : "watch-text"}>{briefLive ? "live" : "fallback"}</strong>
          </div>
          <div>
            <span>数据源</span>
            <strong className={sourceOk === sourceTotal ? "buy-text" : "watch-text"}>
              {sourceOk}/{sourceTotal || "-"}
            </strong>
          </div>
          <div>
            <span>质检</span>
            <strong className="buy-text">ready</strong>
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
  disabled,
  onDecision,
}: {
  items: TodayActionItem[];
  counts?: {
    total: number;
    pending: number;
    done: number;
    watch: number;
    skip: number;
    last_updated?: string;
  };
  loading: boolean;
  disabled?: boolean;
  onDecision: (key: string, decision: DecisionValue) => void;
}) {
  return (
    <section className="war-stack" data-od-id="action-queue">
      <header className="war-section-head">
        <div>
          <span className="war-eyebrow">Action Stack</span>
          <h2>今天只看这几件事</h2>
        </div>
        <div className="war-counts">
          <span>P0 {counts?.pending ?? items.length}</span>
          <span>已处理 {counts?.done ?? 0}/{counts?.total ?? items.length}</span>
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
              disabled={disabled}
              onDecision={onDecision}
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
  disabled,
  onDecision,
}: {
  item: TodayActionItem;
  index: number;
  disabled?: boolean;
  onDecision: (key: string, decision: DecisionValue) => void;
}) {
  const checked = item.decision?.value === "done";
  const code = stockCodeFromTitle(item.title);
  const name = stockNameFromTitle(item.title);
  const href = code ? `/stock/${code}` : item.url || "#";
  const tone = item.tone || item.decision?.tone || (index === 0 ? "sell" : "watch");
  const nextDecision: DecisionValue = checked ? "pending" : "done";
  const freshnessLabel =
    item.freshness?.label || item.freshness?.value || item.freshness?.status || item.confidence?.label || item.group_title || "live";

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
          <Badge tone={tone}>{item.status || item.group_title || item.decision?.label || "待处理"}</Badge>
          <span>{item.source || item.group_title || freshnessLabel}</span>
        </div>
      </div>
      <div className="war-action-control">
        <button
          type="button"
          className={cn("focus-ring war-check", checked ? "is-on" : "")}
          disabled={disabled}
          onClick={() => onDecision(item.key, nextDecision)}
        >
          {disabled ? <LoaderCircle size={14} className="animate-spin" /> : <Check size={14} />}
          {checked ? "已处理" : "处理"}
        </button>
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
  dataReady,
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
  dataReady: boolean;
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
          <strong className={fresh === sources.length ? "buy-text" : "watch-text"}>{fresh}/{sources.length || "-"}</strong>
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
          <strong className={dataReady ? "buy-text" : "watch-text"}>{dataReady ? "pass" : "loading"}</strong>
        </div>
        <div className="war-source-line"><span>actions</span><strong>{actionTotal}</strong></div>
        <div className="war-source-line"><span>risks</span><strong>{riskTotal}</strong></div>
        <div className="war-source-line"><span>stale</span><strong>{staleTotal ? "visible" : "clear"}</strong></div>
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
  const updateDecision = useUpdateTodayActionDecision();
  const data = today.data;
  const hero = data?.command_hero;
  const displayDate = data?.display_date || data?.generated_at?.slice(0, 10) || data?.trade_date || hero?.trade_date;
  const sourceCards = data?.source_cards ?? [];
  const freshSourceCount = sourceCards.filter(sourceIsFresh).length;
  const staleSourceCount = sourceCards.filter((source) => !sourceIsFresh(source)).length;
  const summaryCards = data?.summary_cards?.length ? data.summary_cards : data?.radar_cards ?? [];
  const metricCards =
    summaryCards.length
      ? summaryCards.slice(0, 4)
      : [
          { label: "持仓优先", value: data?.counts?.watchlist_priority ?? "-", detail: "优先处理持仓", tone: "sell" },
          { label: "观察候选", value: data?.counts?.candidate_total ?? "-", detail: "观察池候选", tone: "watch" },
          { label: "午盘新增", value: data?.counts?.fresh_candidates ?? "-", detail: "午盘新增观察", tone: "positive" },
          { label: "质检状态", value: `${freshSourceCount}/${sourceCards.length || "-"}`, detail: "数据源可用", tone: "positive" },
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
      value: asText(displayDate, "待同步"),
    },
  ];

  function handleDecision(key: string, decision: DecisionValue) {
    if (!data) {
      return;
    }
    updateDecision.mutate({
      trade_date: data.trade_date,
      key,
      decision,
    });
  }

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

        <div className="war-layout" data-od-id="command-center-v1">
          <div className="war-primary">
            {today.isLoading && !data ? (
              <HeroSkeleton />
            ) : (
              <DecisionBrief
                title={hero?.title || data?.hero?.title || "先把旧仓风险降下来，新仓只等一个确认触发"}
                summary={hero?.summary || data?.hero?.summary || "今天不是找更多机会，而是按纪律先处理旧仓风险。"}
                status={hero?.source_state || data?.hero?.gate_label || "实时链路"}
                gateLabel={data?.hero?.gate_label || hero?.source_state || "防守试错"}
                cap={asText(data?.hero?.position_cap, "0成")}
                mainTheme={asText(data?.hero?.main_theme, "AI + 机器人")}
                actions={actions}
                sourceOk={freshSourceCount}
                sourceTotal={sourceCards.length}
                briefLive={Boolean(data?.brief_is_live)}
              />
            )}

            <SignalStrip items={tapeItems} />

            <ActionStack
              items={actionItems}
              counts={counts}
              loading={today.isLoading}
              disabled={updateDecision.isPending}
              onDecision={handleDecision}
            />

            {updateDecision.isError ? (
              <div className="war-inline-note negative-text">
                动作状态更新失败：{updateDecision.error?.message || "请确认后端服务可用后重试。"}
              </div>
            ) : null}
            {updateDecision.isSuccess ? (
              <div className="war-inline-note buy-text">
                动作状态已同步。
              </div>
            ) : null}
          </div>

          <IntelligenceRail
            risks={riskRows}
            sources={sourceCards}
            runs={runsQuery.data?.runs ?? []}
            runsLoading={runsQuery.isLoading}
            dataReady={Boolean(data)}
            actionTotal={counts?.total ?? actionItems.length}
            riskTotal={riskRows.length}
            staleTotal={staleSourceCount}
            watchlistTotal={data?.counts?.watchlist_total}
            candidateTotal={data?.counts?.candidate_total}
            freshCandidates={data?.counts?.fresh_candidates}
            confirmed={data?.counts?.confirmed}
          />
        </div>
      </div>
    </main>
  );
}
