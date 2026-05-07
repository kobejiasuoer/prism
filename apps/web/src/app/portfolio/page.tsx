"use client";

import { useMemo, useState } from "react";
import { AlertTriangle, RefreshCw, ShieldCheck, WalletCards } from "lucide-react";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import { MetricCard, MetricSkeleton } from "@/components/metric-card";
import { PageTitle } from "@/components/page-title";
import { StockCard } from "@/components/stock-card";
import { WatchlistManagerPanel } from "@/components/watchlist-manager-panel";
import {
  usePortfolioAccount,
  useRecordPortfolioCash,
  useRecordPortfolioFill,
  useRecordPortfolioReconcile,
  useSetPortfolioMode,
  useWatchlist,
} from "@/lib/hooks";
import type { AccountMode, AccountReadinessState, PortfolioAccountResponse } from "@/lib/types";
import { ApiError } from "@/lib/api";

const MODE_OPTIONS: Array<{ value: AccountMode; label: string; hint: string }> = [
  { value: "research", label: "研究态", hint: "仅研究 / 复盘，无真钱" },
  { value: "shadow", label: "影子盘", hint: "记录意图但不入金" },
  { value: "live_small", label: "小额实盘", hint: "已入金、需对账" },
];

const SIDE_OPTIONS: Array<{ value: "buy" | "sell"; label: string }> = [
  { value: "buy", label: "买入" },
  { value: "sell", label: "卖出" },
];

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `¥${Number(value).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function todayStr(): string {
  const d = new Date();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function readinessTone(mode: string | undefined): "buy" | "watch" | "risk" {
  if (mode === "live_ready") return "buy";
  if (mode === "shadow_only") return "watch";
  return "risk";
}

function ReadinessBanner({ data }: { data: PortfolioAccountResponse }) {
  const r = data.readiness;
  const accountState = r.account_state;
  const blockers = r.blockers || [];
  const warnings = r.warnings || [];
  const tone = readinessTone(r.readiness_mode);

  return (
    <div className="surface-card mb-6 flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={tone}>
          {r.readiness_mode === "live_ready"
            ? "Live Ready"
            : r.readiness_mode === "shadow_only"
            ? "Shadow Only"
            : "Blocked"}
        </Badge>
        <Badge tone={accountState?.mode_tone === "risk" ? "risk" : accountState?.mode_tone === "watch" ? "watch" : "info"}>
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
              <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[var(--tone-risk)]" />
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
              <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[var(--tone-watch)]" />
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
          数据态与账户态均通过 readiness 闸口。
        </div>
      ) : null}
    </div>
  );
}

function PositionsTable({ positions }: { positions: PortfolioAccountResponse["account"]["open_positions"] }) {
  if (!positions.length) {
    return <EmptyState>当前没有真持仓。研究态下可继续观察自选股，但不要把它当作真账户。</EmptyState>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead className="text-[var(--text-tertiary)]">
          <tr>
            <th className="px-2 py-1 text-left">代码</th>
            <th className="px-2 py-1 text-left">名称</th>
            <th className="px-2 py-1 text-right">持仓</th>
            <th className="px-2 py-1 text-right">均价</th>
            <th className="px-2 py-1 text-right">成本</th>
            <th className="px-2 py-1 text-right">已实现</th>
            <th className="px-2 py-1 text-left">最近成交</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((pos) => (
            <tr key={pos.code} className="border-t border-[var(--border-subtle)]">
              <td className="px-2 py-1 font-mono">{pos.code}</td>
              <td className="px-2 py-1">{pos.name}</td>
              <td className="px-2 py-1 text-right">{pos.qty}</td>
              <td className="px-2 py-1 text-right">{formatMoney(pos.avg_cost)}</td>
              <td className="px-2 py-1 text-right">{formatMoney(pos.cost_basis)}</td>
              <td className={`px-2 py-1 text-right ${pos.realized_pnl >= 0 ? "text-[var(--tone-positive)]" : "text-[var(--tone-risk)]"}`}>
                {formatMoney(pos.realized_pnl)}
              </td>
              <td className="px-2 py-1 text-[var(--text-tertiary)]">{pos.last_fill_at || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function FillsTable({ fills }: { fills: PortfolioAccountResponse["recent_fills"] }) {
  if (!fills.length) {
    return <EmptyState>尚无成交记录。</EmptyState>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead className="text-[var(--text-tertiary)]">
          <tr>
            <th className="px-2 py-1 text-left">时间</th>
            <th className="px-2 py-1 text-left">交易日</th>
            <th className="px-2 py-1 text-left">代码</th>
            <th className="px-2 py-1 text-left">方向</th>
            <th className="px-2 py-1 text-right">数量</th>
            <th className="px-2 py-1 text-right">价格</th>
            <th className="px-2 py-1 text-right">现金变动</th>
            <th className="px-2 py-1 text-left">关联意图</th>
          </tr>
        </thead>
        <tbody>
          {fills.map((f) => (
            <tr key={f.fill_id} className="border-t border-[var(--border-subtle)]">
              <td className="px-2 py-1 text-[var(--text-tertiary)]">{f.ts}</td>
              <td className="px-2 py-1">{f.trade_date}</td>
              <td className="px-2 py-1 font-mono">{f.code}</td>
              <td className="px-2 py-1">
                <Badge tone={f.side === "buy" ? "buy" : "sell"}>{f.side === "buy" ? "买" : "卖"}</Badge>
              </td>
              <td className="px-2 py-1 text-right">{f.qty}</td>
              <td className="px-2 py-1 text-right">{formatMoney(f.price)}</td>
              <td className={`px-2 py-1 text-right ${f.cash_delta >= 0 ? "text-[var(--tone-positive)]" : "text-[var(--tone-risk)]"}`}>
                {formatMoney(f.cash_delta)}
              </td>
              <td className="px-2 py-1 text-[var(--text-tertiary)]">{f.intent_key || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UnreconciledList({ items }: { items: AccountReadinessState["unreconciled_intents"] }) {
  if (!items.length) {
    return <EmptyState>没有未对账的历史动作。</EmptyState>;
  }
  return (
    <ul className="flex flex-col gap-1 text-[12px]">
      {items.map((it) => (
        <li key={`${it.trade_date}-${it.intent_key}`} className="flex gap-2">
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-[var(--tone-watch)]" />
          <span>
            {it.trade_date} <code className="font-mono text-[11px]">{it.intent_key}</code>
            {it.decision_updated_at ? ` · 标记于 ${it.decision_updated_at}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ModeSwitch({ data }: { data: PortfolioAccountResponse }) {
  const mutation = useSetPortfolioMode();
  const [startingCash, setStartingCash] = useState<string>(String(data.account.starting_cash || ""));
  const [allowUnsafe, setAllowUnsafe] = useState(false);

  const handle = (mode: AccountMode) => {
    mutation.mutate({
      mode,
      starting_cash: startingCash ? Number(startingCash) : undefined,
      allow_unsafe: allowUnsafe,
    });
  };

  const errorMsg = mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {MODE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            disabled={mutation.isPending}
            onClick={() => handle(opt.value)}
            className={`focus-ring rounded-md border px-3 py-1.5 text-[12px] ${
              data.account.mode === opt.value
                ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "border-[var(--border-subtle)] text-[var(--text-secondary)]"
            }`}
          >
            {opt.label}
            <span className="ml-1 text-[10px] text-[var(--text-tertiary)]">{opt.hint}</span>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
          初始现金（首次设置或重设）
          <input
            type="number"
            step="0.01"
            min="0"
            value={startingCash}
            onChange={(e) => setStartingCash(e.target.value)}
            className="mt-1 w-44 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
          />
        </label>
        <label className="flex items-center gap-1 text-[11px] text-[var(--text-tertiary)]">
          <input type="checkbox" checked={allowUnsafe} onChange={(e) => setAllowUnsafe(e.target.checked)} />
          allow_unsafe（跳过 live_small 前置校验，仅紧急修复用）
        </label>
      </div>
      {errorMsg ? <div className="text-[12px] text-[var(--tone-risk)]">{errorMsg}</div> : null}
    </div>
  );
}

function CashAdjustForm() {
  const mutation = useRecordPortfolioCash();
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!delta || !reason) return;
    mutation.mutate(
      { delta: Number(delta), reason },
      {
        onSuccess: () => {
          setDelta("");
          setReason("");
        },
      },
    );
  };

  const errorMsg = mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        现金变动（正=入金，负=出金）
        <input
          type="number"
          step="0.01"
          required
          value={delta}
          onChange={(e) => setDelta(e.target.value)}
          className="mt-1 w-36 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        原因
        <input
          required
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="deposit / withdraw / dividend"
          className="mt-1 w-56 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <button
        type="submit"
        disabled={mutation.isPending}
        className="focus-ring rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-1.5 text-[12px] text-[var(--accent)]"
      >
        记录现金调整
      </button>
      {errorMsg ? <div className="basis-full text-[12px] text-[var(--tone-risk)]">{errorMsg}</div> : null}
    </form>
  );
}

function FillForm({ defaultTradeDate }: { defaultTradeDate: string }) {
  const mutation = useRecordPortfolioFill();
  const [trade_date, setTradeDate] = useState(defaultTradeDate);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [fees, setFees] = useState("");
  const [intent_key, setIntent] = useState("");
  const [broker_ref, setBroker] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate(
      {
        trade_date,
        code,
        side,
        qty: Number(qty),
        price: Number(price),
        fees: fees ? Number(fees) : undefined,
        name: name || undefined,
        intent_key: intent_key || undefined,
        broker_ref: broker_ref || undefined,
      },
      {
        onSuccess: () => {
          setQty("");
          setPrice("");
          setFees("");
        },
      },
    );
  };

  const errorMsg = mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        交易日
        <input
          required
          value={trade_date}
          onChange={(e) => setTradeDate(e.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        代码（如 sh600690）
        <input
          required
          value={code}
          onChange={(e) => setCode(e.target.value.toLowerCase())}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px] font-mono"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        名称（可空，自动取 watchlist）
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        方向
        <select
          value={side}
          onChange={(e) => setSide(e.target.value as "buy" | "sell")}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        >
          {SIDE_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        数量
        <input
          required
          type="number"
          min="1"
          step="1"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        成交价
        <input
          required
          type="number"
          step="0.01"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        费用（可空）
        <input
          type="number"
          step="0.01"
          value={fees}
          onChange={(e) => setFees(e.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        关联意图 key（可空）
        <input
          value={intent_key}
          onChange={(e) => setIntent(e.target.value)}
          placeholder="如 wl-priority-sh600690"
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px] font-mono"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)] sm:col-span-2">
        券商订单号 / 备注（可空）
        <input
          value={broker_ref}
          onChange={(e) => setBroker(e.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <div className="flex items-end sm:col-span-2">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="focus-ring rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-1.5 text-[12px] text-[var(--accent)]"
        >
          录入成交
        </button>
      </div>
      {errorMsg ? <div className="col-span-full text-[12px] text-[var(--tone-risk)]">{errorMsg}</div> : null}
    </form>
  );
}

function ReconcileForm({ defaultTradeDate }: { defaultTradeDate: string }) {
  const mutation = useRecordPortfolioReconcile();
  const [trade_date, setTradeDate] = useState(defaultTradeDate);
  const [broker_cash, setBrokerCash] = useState("");
  const [broker_equity, setBrokerEquity] = useState("");
  const [note, setNote] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    mutation.mutate(
      {
        trade_date,
        broker_cash: Number(broker_cash),
        broker_equity: Number(broker_equity),
        note: note || undefined,
      },
      {
        onSuccess: () => {
          setBrokerCash("");
          setBrokerEquity("");
          setNote("");
        },
      },
    );
  };

  const errorMsg = mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        对账日
        <input
          required
          value={trade_date}
          onChange={(e) => setTradeDate(e.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        券商现金（从券商 App 复制）
        <input
          required
          type="number"
          step="0.01"
          value={broker_cash}
          onChange={(e) => setBrokerCash(e.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        券商持仓市值
        <input
          required
          type="number"
          step="0.01"
          value={broker_equity}
          onChange={(e) => setBrokerEquity(e.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        备注
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <div className="flex items-end sm:col-span-4">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="focus-ring rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-1.5 text-[12px] text-[var(--accent)]"
        >
          记录对账
        </button>
      </div>
      {errorMsg ? <div className="col-span-full text-[12px] text-[var(--tone-risk)]">{errorMsg}</div> : null}
    </form>
  );
}

export default function PortfolioPage() {
  const portfolio = usePortfolioAccount();
  const watchlist = useWatchlist();
  const data = portfolio.data;
  const defaultTradeDate = useMemo(
    () => data?.expected_trade_date || data?.trade_date || todayStr(),
    [data?.expected_trade_date, data?.trade_date],
  );

  return (
    <main className="flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-7xl">
        <PageTitle
          eyebrow={data?.expected_trade_date || todayStr()}
          title="账户控制台"
          summary="实盘账本、对账闸口与研究自选股都在这里集中管理。下面所有数据都是真账户态，不是 watchlist 视角。"
          icon={WalletCards}
          badge={data?.account.mode_label || "研究态"}
          actions={
            <button
              type="button"
              className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]"
              onClick={() => void portfolio.refetch()}
            >
              <RefreshCw size={14} className={portfolio.isFetching ? "animate-spin" : ""} />
              刷新
            </button>
          }
        />

        {portfolio.isError ? (
          <ErrorState message="账户数据暂不可用" onRetry={() => void portfolio.refetch()} />
        ) : null}

        {data ? <ReadinessBanner data={data} /> : null}

        <section className="mb-7 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {portfolio.isLoading && !data
            ? Array.from({ length: 4 }).map((_, index) => <MetricSkeleton key={index} />)
            : (data?.summary_cards || []).map((card, index) => (
                <MetricCard key={`${card.label}-${index}`} {...card} />
              ))}
        </section>

        <section className="mb-7 grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Panel title="持仓" eyebrow="Open positions" className="surface-card p-4">
            {data ? <PositionsTable positions={data.account.open_positions} /> : <SkeletonBlock className="h-24 w-full" />}
          </Panel>
          <Panel title="未对账动作" eyebrow="Unreconciled intents" className="surface-card p-4">
            {data ? <UnreconciledList items={data.unreconciled_intents} /> : <SkeletonBlock className="h-16 w-full" />}
          </Panel>
        </section>

        <section className="mb-7">
          <Panel title="近期成交" eyebrow="Recent fills" className="surface-card p-4">
            {data ? <FillsTable fills={data.recent_fills} /> : <SkeletonBlock className="h-24 w-full" />}
          </Panel>
        </section>

        <section className="mb-7 grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Panel title="切换运行模式" eyebrow="Mode" className="surface-card p-4">
            {data ? <ModeSwitch data={data} /> : <SkeletonBlock className="h-16 w-full" />}
          </Panel>
          <Panel title="现金调整" eyebrow="Cash" className="surface-card p-4">
            <CashAdjustForm />
          </Panel>
          <Panel title="对账（按券商真实数据）" eyebrow="Reconcile" className="surface-card p-4">
            <ReconcileForm defaultTradeDate={defaultTradeDate} />
          </Panel>
        </section>

        <section className="mb-7">
          <Panel title="录入成交" eyebrow="Record fill" className="surface-card p-4">
            <FillForm defaultTradeDate={defaultTradeDate} />
          </Panel>
        </section>

        <section className="mb-7">
          <Panel
            title="研究自选股"
            eyebrow="Research universe"
            className="surface-card p-4"
            action={<Badge tone="info">仅研究</Badge>}
          >
            <p className="mb-3 text-[12px] text-[var(--text-tertiary)]">
              下方为研究态的自选股（watchlist），不是真持仓。真账户视角请看上方 &ldquo;持仓&rdquo; 区块。
            </p>
            <div className="grid grid-cols-1 gap-3 xl:grid-cols-3">
              {(watchlist.data?.groups || []).map((group) => (
                <div key={group.key || group.title}>
                  <div className="mb-2 flex items-center gap-2">
                    <span className="text-[13px] font-medium">{group.title}</span>
                    <Badge tone={group.key === "priority" ? "risk" : group.key === "follow" ? "info" : "watch"}>
                      {group.count || 0}
                    </Badge>
                  </div>
                  <div className="flex flex-col gap-2">
                    {group.cards?.length ? (
                      group.cards.map((stock) => <StockCard key={stock.code} stock={stock} />)
                    ) : (
                      <EmptyState>{group.empty || "当前没有股票。"}</EmptyState>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
        </section>

        <section id="watchlist-manager" className="mb-7">
          <WatchlistManagerPanel />
        </section>
      </div>
    </main>
  );
}
