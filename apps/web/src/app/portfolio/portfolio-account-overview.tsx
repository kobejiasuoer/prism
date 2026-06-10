"use client";

import Link from "next/link";
import { AlertTriangle, CheckCircle2, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/badge";
import { EmptyState, Panel, SkeletonBlock } from "@/components/data-card";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import type {
  AccountReadinessState,
  PortfolioAccountResponse,
} from "@/lib/types";
import {
  formatMoney,
  formatPercent,
  pnlTone,
  stockDetailHref,
} from "./portfolio-utils";

export type PortfolioAccountAction = "cash" | "reconcile" | "mode" | "review";

export type PortfolioAccountSummaryProps = {
  data?: PortfolioAccountResponse;
  loading: boolean;
  onSelectAction: (action: PortfolioAccountAction, targetId: string) => void;
};

export type PortfolioAccountPositionTablesProps = {
  data?: PortfolioAccountResponse;
};

export type PortfolioAccountActivityTablesProps = {
  data?: PortfolioAccountResponse;
  noFillItems: PortfolioAccountResponse["account"]["no_fill_intents"];
};

function readinessTone(mode: string | undefined): "buy" | "watch" | "risk" {
  if (mode === "live_ready") return "buy";
  if (mode === "shadow_only") return "watch";
  return "risk";
}

function readinessLabel(mode: string | undefined): string {
  if (mode === "live_ready") return "数据源就绪";
  if (mode === "shadow_only") return "仅观察";
  return "已阻断";
}

function accountGateLabel(data: PortfolioAccountResponse): {
  label: string;
  tone: "buy" | "watch" | "risk" | "info";
} {
  const accountState = data.readiness.account_state;
  if (!accountState) return { label: "账户未接入", tone: "watch" };
  if (accountState.ready_for_live_small)
    return { label: "账户可实盘", tone: "buy" };
  if (accountState.cash_balance < 0) return { label: "现金为负", tone: "risk" };
  if (accountState.mode !== "live_small")
    return { label: "账户非实盘", tone: "watch" };
  return { label: "账户未就绪", tone: "risk" };
}

function buildAccountNextStep(data: PortfolioAccountResponse): {
  title: string;
  detail: string;
  tone: "buy" | "watch" | "risk" | "info";
  action: PortfolioAccountAction;
} {
  const account = data.account;
  const state = data.readiness.account_state;
  if (state?.cash_balance && state.cash_balance < 0) {
    return {
      title: "先补录入金",
      detail: `账本现金为 ${formatMoney(state.cash_balance)}。如果券商账户真实有现金，请在现金调整里补录入金；补完再对账。`,
      tone: "risk",
      action: "cash",
    };
  }
  if (account.fills_count > 0 && !data.reconciliation?.fresh) {
    return {
      title: "录完成交后对账",
      detail:
        "已有成交记录，但还没有近期券商对账。请把券商现金和持仓市值填进对账区。",
      tone: "watch",
      action: "reconcile",
    };
  }
  if (state?.ready_for_live_small) {
    return {
      title: "账户账本可实盘",
      detail: "现金、成交和对账已通过账户闸口。需要真钱执行时再切到小额实盘。",
      tone: "buy",
      action: "mode",
    };
  }
  return {
    title: "先保持研究态",
    detail:
      "这页当前适合补录券商事实、复核持仓和对账；不要把研究态当成自动下单。",
    tone: "info",
    action: "review",
  };
}

function ReadinessBanner({ data }: { data: PortfolioAccountResponse }) {
  const r = data.readiness;
  const accountState = r.account_state;
  const blockers = r.blockers || [];
  const warnings = r.warnings || [];
  const tone = readinessTone(r.readiness_mode);
  const accountGate = accountGateLabel(data);

  return (
    <div className="surface-card mb-6 flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={tone}>{readinessLabel(r.readiness_mode)}</Badge>
        <Badge tone={accountGate.tone}>{accountGate.label}</Badge>
        <Badge
          tone={
            accountState?.mode_tone === "risk"
              ? "risk"
              : accountState?.mode_tone === "watch"
                ? "watch"
                : "info"
          }
        >
          {accountState?.mode_label || "研究态"}
        </Badge>
        <span className="text-[12px] text-[var(--text-tertiary)]">
          预期交易日 {r.expected_trade_date}
          {r.session?.calendar_status === "holiday" ? "（交易所休市）" : ""}
          {r.session?.calendar_status === "unknown" ? "（日历未覆盖）" : ""}
          ｜会话 {r.session?.label || "-"}
        </span>
      </div>
      {blockers.length ? (
        <ul className="flex flex-col gap-1 text-[12px] text-[var(--text-secondary)]">
          {blockers.map((b) => (
            <li key={b.code} className="flex gap-2">
              <AlertTriangle
                size={14}
                className="mt-0.5 shrink-0 text-[var(--tone-risk)]"
              />
              <span>
                <strong>{b.label}</strong>：{b.message}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {warnings.length ? (
        <ul className="flex flex-col gap-1 text-[12px] text-[var(--text-tertiary)]">
          {warnings.map((w) => (
            <li key={w.code} className="flex gap-2">
              <AlertTriangle
                size={14}
                className="mt-0.5 shrink-0 text-[var(--tone-watch)]"
              />
              <span>
                <strong>{w.label}</strong>：{w.message}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {!blockers.length && !warnings.length ? (
        <div className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
          <ShieldCheck size={14} className="text-[var(--tone-positive)]" />
          数据源通过新鲜度闸口；账户是否可实盘以上方账户标签为准。
        </div>
      ) : null}
      {accountState && accountState.cash_balance < 0 ? (
        <div className="rounded-md border border-[color-mix(in_srgb,var(--tone-risk)_30%,transparent)] bg-[color-mix(in_srgb,var(--tone-risk)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
          <strong className="text-[var(--tone-risk)]">本地现金为负：</strong>
          已录入成交会扣减本地账本现金。现在现金是{" "}
          {formatMoney(accountState.cash_balance)}， 说明还没有补录入金 /
          初始现金；请在“现金调整”里记录入金，或把这笔记录仅当研究账本。
        </div>
      ) : null}
    </div>
  );
}

function AccountWorkflowCard({
  data,
  onSelectAction,
}: {
  data: PortfolioAccountResponse;
  onSelectAction: (action: PortfolioAccountAction, targetId: string) => void;
}) {
  const step = buildAccountNextStep(data);
  const actionTarget: Record<PortfolioAccountAction, string> = {
    cash: "cash-adjust",
    reconcile: "reconcile-form",
    mode: "mode-switch",
    review: "positions",
  };
  const actionLabel: Record<PortfolioAccountAction, string> = {
    cash: "去补录现金",
    reconcile: "去对账",
    mode: "查看模式",
    review: "查看账本",
  };

  return (
    <section className="mb-7 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
      <div className="surface-card p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge tone={step.tone}>账户下一步</Badge>
          <span className="text-[12px] text-[var(--text-tertiary)]">
            这页只记录券商事实，不会自动下单。
          </span>
        </div>
        <div className="text-xl font-semibold text-[var(--text-primary)]">
          {step.title}
        </div>
        <p className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
          {step.detail}
        </p>
        <button
          type="button"
          onClick={() => onSelectAction(step.action, actionTarget[step.action])}
          className="focus-ring mt-4 rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-1.5 text-[12px] text-[var(--accent)]"
        >
          {actionLabel[step.action]}
        </button>
      </div>
      <div className="surface-card p-4">
        <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
          Record Flow
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 text-[12px]">
          {(
            [
              {
                index: "1",
                label: "录入券商成交",
                done: data.account.fills_count > 0,
              },
              {
                index: "2",
                label: "补录入金 / 出金",
                done: data.account.cash_balance >= 0,
              },
              {
                index: "3",
                label: "按券商 App 对账",
                done: Boolean(data.reconciliation?.fresh),
              },
            ] as const
          ).map(({ index, label, done }) => (
            <div
              key={String(index)}
              className="flex items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2"
            >
              {done ? (
                <CheckCircle2
                  size={15}
                  className="text-[var(--tone-positive)]"
                />
              ) : (
                <span className="flex h-4 w-4 items-center justify-center rounded-full border border-[var(--border-subtle)] text-[10px] text-[var(--text-tertiary)]">
                  {index}
                </span>
              )}
              <span
                className={
                  done
                    ? "text-[var(--text-secondary)]"
                    : "text-[var(--text-primary)]"
                }
              >
                {label}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function PositionsTable({
  positions,
}: {
  positions: PortfolioAccountResponse["account"]["open_positions"];
}) {
  if (!positions.length) {
    return (
      <EmptyState>
        当前没有真持仓。研究态下可继续观察自选股，但不要把它当作真账户。
      </EmptyState>
    );
  }
  return (
    <>
      <div className="flex flex-col gap-2 md:hidden">
        {positions.map((pos) => (
          <article
            key={`${pos.code}-position-mobile`}
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3"
          >
            <div className="flex items-start justify-between gap-3">
              <Link
                href={stockDetailHref(pos.code)}
                className="focus-ring min-w-0 rounded-[6px]"
              >
                <div className="truncate text-[13px] font-semibold text-[var(--text-primary)]">
                  {pos.name || pos.code}
                </div>
                <div className="mono mt-0.5 text-[11px] text-[var(--text-tertiary)]">
                  {pos.code}
                </div>
              </Link>
              <div
                className={`shrink-0 text-right text-[13px] font-semibold ${pnlTone(pos.total_pnl)}`}
              >
                {formatMoney(pos.total_pnl)}
                <div className="mt-0.5 text-[10px] font-normal text-[var(--text-tertiary)]">
                  总盈亏
                </div>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-[12px]">
              <div>
                <div className="text-[11px] text-[var(--text-tertiary)]">
                  持仓 / 均价
                </div>
                <div className="mt-1 text-[var(--text-primary)]">
                  {pos.qty} / {formatMoney(pos.avg_cost)}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-[var(--text-tertiary)]">
                  现价
                </div>
                <div className="mt-1 text-[var(--text-primary)]">
                  {formatMoney(pos.current_price)}
                  {pos.quote_change_pct !== null &&
                  pos.quote_change_pct !== undefined ? (
                    <span
                      className={`ml-1 text-[11px] ${pnlTone(pos.quote_change_pct)}`}
                    >
                      {formatPercent(pos.quote_change_pct)}
                    </span>
                  ) : null}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-[var(--text-tertiary)]">
                  市值 / 成本
                </div>
                <div className="mt-1 text-[var(--text-primary)]">
                  {formatMoney(pos.market_value)} /{" "}
                  {formatMoney(pos.cost_basis)}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-[var(--text-tertiary)]">
                  浮盈亏
                </div>
                <div className={`mt-1 ${pnlTone(pos.unrealized_pnl)}`}>
                  {formatMoney(pos.unrealized_pnl)}
                  <span className="ml-1 text-[11px]">
                    {formatPercent(pos.unrealized_pnl_pct)}
                  </span>
                </div>
              </div>
              <div>
                <div className="text-[11px] text-[var(--text-tertiary)]">
                  已实现
                </div>
                <div className={`mt-1 ${pnlTone(pos.realized_pnl)}`}>
                  {formatMoney(pos.realized_pnl)}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-[var(--text-tertiary)]">
                  最近成交
                </div>
                <div className="mt-1 text-[var(--text-primary)]">
                  {pos.last_fill_at || "-"}
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-[12px]">
          <thead className="text-[var(--text-tertiary)]">
            <tr>
              <th className="px-2 py-1 text-left">代码</th>
              <th className="px-2 py-1 text-left">名称</th>
              <th className="px-2 py-1 text-right">持仓</th>
              <th className="px-2 py-1 text-right">均价</th>
              <th className="px-2 py-1 text-right">成本</th>
              <th className="px-2 py-1 text-right">现价</th>
              <th className="px-2 py-1 text-right">市值</th>
              <th className="px-2 py-1 text-right">浮盈亏</th>
              <th className="px-2 py-1 text-right">已实现</th>
              <th className="px-2 py-1 text-right">总盈亏</th>
              <th className="px-2 py-1 text-left">最近成交</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos) => (
              <tr
                key={pos.code}
                className="border-t border-[var(--border-subtle)]"
              >
                <td className="px-2 py-1 font-mono">{pos.code}</td>
                <td className="px-2 py-1">{pos.name}</td>
                <td className="px-2 py-1 text-right">{pos.qty}</td>
                <td className="px-2 py-1 text-right">
                  {formatMoney(pos.avg_cost)}
                </td>
                <td className="px-2 py-1 text-right">
                  {formatMoney(pos.cost_basis)}
                </td>
                <td className="px-2 py-1 text-right">
                  <div>{formatMoney(pos.current_price)}</div>
                  {pos.quote_change_pct !== null &&
                  pos.quote_change_pct !== undefined ? (
                    <div
                      className={`text-[10px] ${pnlTone(pos.quote_change_pct)}`}
                    >
                      {formatPercent(pos.quote_change_pct)}
                    </div>
                  ) : null}
                </td>
                <td className="px-2 py-1 text-right">
                  {formatMoney(pos.market_value)}
                </td>
                <td
                  className={`px-2 py-1 text-right ${pnlTone(pos.unrealized_pnl)}`}
                >
                  <div>{formatMoney(pos.unrealized_pnl)}</div>
                  <div className="text-[10px]">
                    {formatPercent(pos.unrealized_pnl_pct)}
                  </div>
                </td>
                <td
                  className={`px-2 py-1 text-right ${pnlTone(pos.realized_pnl)}`}
                >
                  {formatMoney(pos.realized_pnl)}
                </td>
                <td
                  className={`px-2 py-1 text-right ${pnlTone(pos.total_pnl)}`}
                >
                  {formatMoney(pos.total_pnl)}
                </td>
                <td className="px-2 py-1 text-[var(--text-tertiary)]">
                  {pos.last_fill_at || "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function FillsTable({
  fills,
}: {
  fills: PortfolioAccountResponse["recent_fills"];
}) {
  if (!fills.length) {
    return <EmptyState>尚无成交记录。</EmptyState>;
  }
  return (
    <>
      <div className="flex flex-col gap-2 md:hidden">
        {fills.map((f) => (
          <article
            key={`${f.fill_id}-mobile`}
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3"
          >
            <div className="flex items-start justify-between gap-3">
              <Link
                href={stockDetailHref(f.code)}
                className="focus-ring min-w-0 rounded-[6px]"
              >
                <div className="truncate text-[13px] font-semibold text-[var(--text-primary)]">
                  {f.name || f.code}
                </div>
                <div className="mono mt-0.5 text-[11px] text-[var(--text-tertiary)]">
                  {f.code}
                </div>
              </Link>
              <Badge tone={f.side === "buy" ? "buy" : "sell"}>
                {f.side === "buy" ? "买" : "卖"}
              </Badge>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-[12px]">
              <div>
                <div className="text-[11px] text-[var(--text-tertiary)]">
                  时间
                </div>
                <div className="mt-1 text-[var(--text-primary)]">{f.ts}</div>
              </div>
              <div>
                <div className="text-[11px] text-[var(--text-tertiary)]">
                  交易日
                </div>
                <div className="mt-1 text-[var(--text-primary)]">
                  {f.trade_date}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-[var(--text-tertiary)]">
                  数量 / 价格
                </div>
                <div className="mt-1 text-[var(--text-primary)]">
                  {f.qty} / {formatMoney(f.price)}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-[var(--text-tertiary)]">
                  现金变动
                </div>
                <div
                  className={`mt-1 font-medium ${f.cash_delta >= 0 ? "text-[var(--tone-positive)]" : "text-[var(--tone-risk)]"}`}
                >
                  {formatMoney(f.cash_delta)}
                </div>
              </div>
            </div>
            {f.intent_key ? (
              <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2.5 py-2 text-[11px] text-[var(--text-tertiary)]">
                关联意图：<span className="mono break-all">{f.intent_key}</span>
              </div>
            ) : null}
          </article>
        ))}
      </div>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-[12px]">
          <thead className="text-[var(--text-tertiary)]">
            <tr>
              <th className="px-2 py-1 text-left">时间</th>
              <th className="px-2 py-1 text-left">交易日</th>
              <th className="px-2 py-1 text-left">代码</th>
              <th className="px-2 py-1 text-left">名称</th>
              <th className="px-2 py-1 text-left">方向</th>
              <th className="px-2 py-1 text-right">数量</th>
              <th className="px-2 py-1 text-right">价格</th>
              <th className="px-2 py-1 text-right">现金变动</th>
              <th className="px-2 py-1 text-left">关联意图</th>
            </tr>
          </thead>
          <tbody>
            {fills.map((f) => (
              <tr
                key={f.fill_id}
                className="border-t border-[var(--border-subtle)]"
              >
                <td className="px-2 py-1 text-[var(--text-tertiary)]">
                  {f.ts}
                </td>
                <td className="px-2 py-1">{f.trade_date}</td>
                <td className="px-2 py-1 font-mono">{f.code}</td>
                <td className="px-2 py-1">{f.name || "-"}</td>
                <td className="px-2 py-1">
                  <Badge tone={f.side === "buy" ? "buy" : "sell"}>
                    {f.side === "buy" ? "买" : "卖"}
                  </Badge>
                </td>
                <td className="px-2 py-1 text-right">{f.qty}</td>
                <td className="px-2 py-1 text-right">{formatMoney(f.price)}</td>
                <td
                  className={`px-2 py-1 text-right ${f.cash_delta >= 0 ? "text-[var(--tone-positive)]" : "text-[var(--tone-risk)]"}`}
                >
                  {formatMoney(f.cash_delta)}
                </td>
                <td className="px-2 py-1 text-[var(--text-tertiary)]">
                  {f.intent_key || "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function NoFillTable({
  items,
}: {
  items: PortfolioAccountResponse["account"]["no_fill_intents"];
}) {
  if (!items.length) {
    return <EmptyState>尚无未成交记录。</EmptyState>;
  }

  return (
    <>
      <div className="flex flex-col gap-2 md:hidden">
        {[...items].reverse().map((item) => (
          <article
            key={`${item.ts}-${item.intent_key}-mobile`}
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-[13px] font-semibold text-[var(--text-primary)]">
                  {item.trade_date || "未成交记录"}
                </div>
                <div className="mt-0.5 text-[11px] text-[var(--text-tertiary)]">
                  {item.ts}
                </div>
              </div>
              <Badge tone="watch">未成交</Badge>
            </div>
            <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2.5 py-2">
              <div className="text-[11px] text-[var(--text-tertiary)]">
                关联意图
              </div>
              <div className="mono mt-1 break-all text-[11px] text-[var(--text-primary)]">
                {item.intent_key || "-"}
              </div>
            </div>
            <div className="mt-3 text-[12px] leading-5 text-[var(--text-secondary)]">
              <span className="text-[var(--text-tertiary)]">原因：</span>
              {item.reason || "-"}
            </div>
          </article>
        ))}
      </div>
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-[12px]">
          <thead className="text-[var(--text-tertiary)]">
            <tr>
              <th className="px-2 py-1 text-left">时间</th>
              <th className="px-2 py-1 text-left">交易日</th>
              <th className="px-2 py-1 text-left">关联意图</th>
              <th className="px-2 py-1 text-left">原因</th>
            </tr>
          </thead>
          <tbody>
            {[...items].reverse().map((item) => (
              <tr
                key={`${item.ts}-${item.intent_key}`}
                className="border-t border-[var(--border-subtle)]"
              >
                <td className="px-2 py-1 text-[var(--text-tertiary)]">
                  {item.ts}
                </td>
                <td className="px-2 py-1">{item.trade_date}</td>
                <td className="px-2 py-1 font-mono text-[11px]">
                  {item.intent_key}
                </td>
                <td className="px-2 py-1 text-[var(--text-secondary)]">
                  {item.reason}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function UnreconciledList({
  items,
}: {
  items: AccountReadinessState["unreconciled_intents"];
}) {
  if (!items.length) {
    return <EmptyState>没有未对账的历史动作。</EmptyState>;
  }
  return (
    <ul className="flex flex-col gap-1 text-[12px]">
      {items.map((it) => (
        <li key={`${it.trade_date}-${it.intent_key}`} className="flex gap-2">
          <AlertTriangle
            size={14}
            className="mt-0.5 shrink-0 text-[var(--tone-watch)]"
          />
          <span>
            {it.trade_date}{" "}
            <code className="font-mono text-[11px]">{it.intent_key}</code>
            {it.decision_updated_at
              ? ` · 标记于 ${it.decision_updated_at}`
              : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function PortfolioAccountSummary({
  data,
  loading,
  onSelectAction,
}: PortfolioAccountSummaryProps) {
  return (
    <>
      {data ? <ReadinessBanner data={data} /> : null}

      {data ? (
        <AccountWorkflowCard data={data} onSelectAction={onSelectAction} />
      ) : (
        <SkeletonBlock className="mb-7 h-36 w-full" />
      )}

      <section className="mb-3">
        <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
          真实账户执行区
        </div>
      </section>

      <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {loading
          ? Array.from({ length: 4 }).map((_, index) => (
              <MetricSkeleton key={index} />
            ))
          : (data?.summary_cards || []).map((card, index) => (
              <MetricCard key={`${card.label}-${index}`} {...card} />
            ))}
      </section>
    </>
  );
}

export function PortfolioAccountPositionTables({
  data,
}: PortfolioAccountPositionTablesProps) {
  return (
    <section
      id="positions"
      className="mb-7 grid grid-cols-1 gap-4 scroll-mt-6 xl:grid-cols-2"
    >
      <Panel title="持仓" eyebrow="Open positions" className="surface-card p-4">
        {data ? (
          <PositionsTable positions={data.account.open_positions} />
        ) : (
          <SkeletonBlock className="h-24 w-full" />
        )}
      </Panel>
      <Panel
        title="未对账动作"
        eyebrow="Unreconciled intents"
        className="surface-card p-4"
      >
        {data ? (
          <UnreconciledList items={data.unreconciled_intents} />
        ) : (
          <SkeletonBlock className="h-16 w-full" />
        )}
      </Panel>
    </section>
  );
}

export function PortfolioAccountActivityTables({
  data,
  noFillItems,
}: PortfolioAccountActivityTablesProps) {
  return (
    <>
      <section className="mb-7">
        <Panel
          title="近期成交"
          eyebrow="Recent fills"
          className="surface-card p-4"
        >
          {data ? (
            <FillsTable fills={data.recent_fills} />
          ) : (
            <SkeletonBlock className="h-24 w-full" />
          )}
        </Panel>
      </section>

      <section className="mb-7">
        <Panel
          title="未成交记录"
          eyebrow="No fill intents"
          className="surface-card p-4"
        >
          {data ? (
            <NoFillTable items={noFillItems} />
          ) : (
            <SkeletonBlock className="h-24 w-full" />
          )}
        </Panel>
      </section>
    </>
  );
}
