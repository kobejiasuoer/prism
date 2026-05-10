"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
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
  useRecordPortfolioNoFill,
  useRecordPortfolioReconcile,
  useSetPortfolioMode,
  useTodayData,
  useUpdateTodayActionDecision,
  useWatchlist,
} from "@/lib/hooks";
import type { AccountMode, AccountReadinessState, DecisionValue, PortfolioAccountResponse } from "@/lib/types";
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

type WritebackMode = "fill" | "no_fill" | "watch" | "skip";

type WritebackContext = {
  code: string;
  name: string;
  source: string;
  sourceLabel: string;
  tradeDate: string;
  intentKey: string;
  conclusion: string;
  position: string;
  continueCondition: string;
  stopCondition: string;
};

type NoFillItem = PortfolioAccountResponse["account"]["no_fill_intents"][number];

type WritebackOutcome = {
  intentKey: string;
  tradeDate: string;
  code: string;
  name: string;
  resultLabel: string;
  statusValue: "watch" | "skip" | "no_fill";
  processedAt: string;
  note?: string;
};

const WRITEBACK_ACTIONS: Array<{ value: WritebackMode; label: string }> = [
  { value: "fill", label: "记录已成交" },
  { value: "no_fill", label: "记录未成交" },
  { value: "watch", label: "继续观察" },
  { value: "skip", label: "放弃" },
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

function NoFillTable({ items }: { items: PortfolioAccountResponse["account"]["no_fill_intents"] }) {
  if (!items.length) {
    return <EmptyState>尚无未成交记录。</EmptyState>;
  }

  return (
    <div className="overflow-x-auto">
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
            <tr key={`${item.ts}-${item.intent_key}`} className="border-t border-[var(--border-subtle)]">
              <td className="px-2 py-1 text-[var(--text-tertiary)]">{item.ts}</td>
              <td className="px-2 py-1">{item.trade_date}</td>
              <td className="px-2 py-1 font-mono text-[11px]">{item.intent_key}</td>
              <td className="px-2 py-1 text-[var(--text-secondary)]">{item.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatOutcomeTime(value: string): string {
  if (!value) return "-";
  const parsed = new Date(value.replace(" ", "T"));
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("zh-CN", { hour12: false });
}

function decisionLabel(value: WritebackOutcome["statusValue"]): string {
  if (value === "watch") return "继续观察";
  if (value === "skip") return "放弃";
  return "未成交";
}

function decisionStatusText(value: WritebackOutcome["statusValue"]): string {
  if (value === "watch") return "watch";
  if (value === "skip") return "skip";
  return "no_fill";
}

function outcomeStorageKey(intentKey: string, tradeDate: string): string {
  return `portfolio-writeback-outcome:${tradeDate}:${intentKey}`;
}

function WritebackOutcomeCard({ outcome }: { outcome: WritebackOutcome }) {
  const noteLabel =
    outcome.statusValue === "no_fill" ? "原因" : outcome.statusValue === "skip" ? "放弃原因" : "备注";

  return (
    <div className="rounded-md border border-[var(--tone-positive)]/30 bg-[var(--tone-positive)]/10 px-4 py-3 text-[12px] text-[var(--text-secondary)]">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="buy">已处理</Badge>
        <Badge tone={outcome.statusValue === "skip" ? "risk" : "watch"}>{outcome.resultLabel}</Badge>
        <span className="font-medium text-[var(--text-primary)]">
          {outcome.code} {outcome.name || "未命名标的"}
        </span>
      </div>
      <div className="mt-2 text-[var(--text-secondary)]">
        已处理：{outcome.code} {outcome.name || "未命名标的"}，本次结果为「{outcome.resultLabel}」。
      </div>
      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div>
          <div className="text-[11px] text-[var(--text-tertiary)]">处理时间</div>
          <div>{formatOutcomeTime(outcome.processedAt)}</div>
        </div>
        <div>
          <div className="text-[11px] text-[var(--text-tertiary)]">当前状态</div>
          <div>{decisionStatusText(outcome.statusValue)}</div>
        </div>
        {outcome.note ? (
          <div className="sm:col-span-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">{noteLabel}</div>
            <div>{outcome.note}</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function FillRiskNotice({
  confirmed,
  onConfirmedChange,
  checkboxLabel = "我确认这笔成交已在外部券商真实发生。",
}: {
  confirmed: boolean;
  onConfirmedChange: (checked: boolean) => void;
  checkboxLabel?: string;
}) {
  return (
    <div className="rounded-md border border-[var(--tone-risk)]/30 bg-[var(--tone-risk)]/5 p-3 text-[12px] text-[var(--text-secondary)]">
      <div className="font-medium text-[var(--tone-risk)]">注意：这里会写入真实账户账本。</div>
      <div className="mt-1">
        请仅在你已经通过外部券商实际成交后填写。如果本次没有成交，请使用“记录未成交”；如果只是继续观察，请使用“继续观察”；如果放弃，请使用“放弃”。
      </div>
      <label className="mt-3 flex items-start gap-2 text-[12px] text-[var(--text-secondary)]">
        <input type="checkbox" checked={confirmed} onChange={(e) => onConfirmedChange(e.target.checked)} />
        <span>{checkboxLabel}</span>
      </label>
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
  const [showUnsafeControls, setShowUnsafeControls] = useState(false);
  const [allowUnsafe, setAllowUnsafe] = useState(false);
  const [unsafeNote, setUnsafeNote] = useState("");
  const [unsafeConfirmText, setUnsafeConfirmText] = useState("");

  const handle = (mode: AccountMode) => {
    const useUnsafeBypass = mode === "live_small" && allowUnsafe;
    mutation.mutate({
      mode,
      starting_cash: startingCash ? Number(startingCash) : undefined,
      allow_unsafe: useUnsafeBypass,
      note: useUnsafeBypass ? unsafeNote : undefined,
    });
  };

  const errorMsg = mutation.error instanceof ApiError ? mutation.error.message : null;
  const unsafeConfirmReady = unsafeConfirmText.trim() === "LIVE_SMALL";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {MODE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            disabled={mutation.isPending || (opt.value === "live_small" && allowUnsafe && (!unsafeNote.trim() || !unsafeConfirmReady))}
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
        <button
          type="button"
          onClick={() => setShowUnsafeControls((value) => !value)}
          className="focus-ring rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[11px] text-[var(--text-secondary)]"
        >
          {showUnsafeControls ? "隐藏紧急 bypass" : "显示紧急 bypass"}
        </button>
      </div>
      {showUnsafeControls ? (
        <div className="rounded-md border border-[var(--tone-risk)]/30 bg-[var(--tone-risk)]/5 p-3 text-[11px] text-[var(--text-secondary)]">
          <div className="mb-2 font-medium text-[var(--tone-risk)]">仅在紧急修账时使用 allow_unsafe</div>
          <div className="mb-3">
            这会把当前模式标记成 bypass 风险态，readiness 不会显示为绿色。启用前必须填写原因，并输入确认文本。
          </div>
          <label className="mb-3 flex items-center gap-2">
            <input type="checkbox" checked={allowUnsafe} onChange={(e) => setAllowUnsafe(e.target.checked)} />
            允许本次切换跳过 live_small 前置校验
          </label>
          {allowUnsafe ? (
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
                bypass 原因
                <input
                  required={allowUnsafe}
                  value={unsafeNote}
                  onChange={(e) => setUnsafeNote(e.target.value)}
                  placeholder="例如：刚补录历史入金，待券商对账完成后重新切回正常校验"
                  className="mt-1 w-80 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
                />
              </label>
              <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
                输入 `LIVE_SMALL` 确认
                <input
                  required={allowUnsafe}
                  value={unsafeConfirmText}
                  onChange={(e) => setUnsafeConfirmText(e.target.value)}
                  className="mt-1 w-40 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
                />
              </label>
            </div>
          ) : null}
        </div>
      ) : null}
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
  const [confirmRealFill, setConfirmRealFill] = useState(false);

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
          setConfirmRealFill(false);
        },
      },
    );
  };

  const errorMsg = mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <div className="col-span-full">
        <FillRiskNotice
          confirmed={confirmRealFill}
          onConfirmedChange={setConfirmRealFill}
          checkboxLabel="我确认这是普通成交录入，并且该成交已在外部券商真实发生。"
        />
      </div>
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
          disabled={mutation.isPending || !confirmRealFill}
          className="focus-ring rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-1.5 text-[12px] text-[var(--accent)]"
        >
          录入成交
        </button>
      </div>
      {errorMsg ? <div className="col-span-full text-[12px] text-[var(--tone-risk)]">{errorMsg}</div> : null}
    </form>
  );
}

function DecisionWritebackPanel({
  context,
  defaultTradeDate,
  onWritebackSuccess,
  persistedOutcome,
}: {
  context: WritebackContext | null;
  defaultTradeDate: string;
  onWritebackSuccess?: (payload: { outcome: WritebackOutcome; noFillItem?: NoFillItem }) => void;
  persistedOutcome?: WritebackOutcome | null;
}) {
  const recordFill = useRecordPortfolioFill();
  const recordNoFill = useRecordPortfolioNoFill();
  const updateDecision = useUpdateTodayActionDecision();
  const [mode, setMode] = useState<WritebackMode>("fill");
  const [tradeDate, setTradeDate] = useState(context?.tradeDate || defaultTradeDate);
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [fees, setFees] = useState("");
  const [brokerRef, setBrokerRef] = useState("");
  const [reason, setReason] = useState("");
  const [feedback, setFeedback] = useState("");
  const [confirmRealFill, setConfirmRealFill] = useState(false);
  const [lastOutcome, setLastOutcome] = useState<WritebackOutcome | null>(null);
  const contextResetKey = `${context?.code || ""}|${context?.intentKey || ""}|${context?.tradeDate || ""}`;

  useEffect(() => {
    setTradeDate(context?.tradeDate || defaultTradeDate);
    setFeedback("");
    setReason("");
    setQty("");
    setPrice("");
    setFees("");
    setBrokerRef("");
    setConfirmRealFill(false);
    setLastOutcome(null);
    setMode("fill");
  }, [contextResetKey]);

  useEffect(() => {
    if (!context) {
      setTradeDate(defaultTradeDate);
    }
  }, [context, defaultTradeDate]);

  if (!context) {
    return (
      <div className="rounded-md border border-dashed border-[var(--border-subtle)] px-4 py-5 text-[12px] text-[var(--text-tertiary)]">
        从个股页点击“记录执行结果”后，这里会自动带入股票上下文。
      </div>
    );
  }

  const busy = recordFill.isPending || recordNoFill.isPending || updateDecision.isPending;
  const requiresIntentKey = mode !== "fill";
  const mutationError =
    (recordFill.error instanceof ApiError ? recordFill.error.message : "") ||
    (recordNoFill.error instanceof ApiError ? recordNoFill.error.message : "") ||
    (updateDecision.error instanceof ApiError ? updateDecision.error.message : "");
  const visibleOutcome = lastOutcome || persistedOutcome || null;

  const registerOutcome = (payload: { resultLabel: string; statusValue: "watch" | "skip" | "no_fill"; note?: string; processedAt?: string; noFillItem?: NoFillItem }) => {
    const outcome: WritebackOutcome = {
      intentKey: context.intentKey,
      tradeDate,
      code: context.code,
      name: context.name,
      resultLabel: payload.resultLabel,
      statusValue: payload.statusValue,
      processedAt: payload.processedAt || new Date().toISOString(),
      note: payload.note?.trim() || undefined,
    };
    setLastOutcome(outcome);
    if ((payload.statusValue === "watch" || payload.statusValue === "skip") && typeof window !== "undefined") {
      window.sessionStorage.setItem(outcomeStorageKey(context.intentKey, tradeDate), JSON.stringify(outcome));
    }
    onWritebackSuccess?.({ outcome, noFillItem: payload.noFillItem });
  };

  const submitDecision = (decision: Extract<DecisionValue, "watch" | "skip">, successText: string) => {
    if (!context.intentKey || !tradeDate) return;

    if (decision === "watch" || decision === "skip") {
      registerOutcome({
        resultLabel: decisionLabel(decision),
        statusValue: decision,
        note: reason,
      });
    }

    updateDecision.mutate(
      {
        trade_date: tradeDate,
        key: context.intentKey,
        decision,
      },
      {
        onSuccess: () => {
          setFeedback(successText);
          setReason("");
        },
      },
    );
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setFeedback("");

    if (mode === "fill") {
      recordFill.mutate(
        {
          trade_date: tradeDate,
          code: context.code,
          name: context.name || undefined,
          side,
          qty: Number(qty),
          price: Number(price),
          fees: fees ? Number(fees) : undefined,
          intent_key: context.intentKey || undefined,
          broker_ref: brokerRef || undefined,
          note: reason || undefined,
        },
        {
          onSuccess: () => {
            setFeedback("已记录成交。");
            setQty("");
            setPrice("");
            setFees("");
            setBrokerRef("");
            setReason("");
            setConfirmRealFill(false);
          },
        },
      );
      return;
    }

    if (mode === "no_fill") {
      recordNoFill.mutate(
        {
          trade_date: tradeDate,
          intent_key: context.intentKey,
          reason: reason || "今日未成交，保留原计划",
        },
        {
          onSuccess: (response) => {
            const savedItem =
              [...(response.account.no_fill_intents || [])]
                .reverse()
                .find((item) => item.trade_date === tradeDate && item.intent_key === context.intentKey) || {
                trade_date: tradeDate,
                intent_key: context.intentKey,
                reason: reason || "今日未成交，保留原计划",
                ts: new Date().toLocaleString("zh-CN", { hour12: false }),
              };
            setFeedback("已记录未成交。");
            registerOutcome({
              resultLabel: "未成交",
              statusValue: "no_fill",
              note: savedItem.reason,
              processedAt: savedItem.ts,
              noFillItem: savedItem,
            });
            setReason("");
          },
        },
      );
      return;
    }

    if (mode === "watch") {
      submitDecision("watch", "已标记为继续观察。");
      return;
    }

    submitDecision("skip", "已标记为放弃。");
  };

  const decisionSummary = [
    context.conclusion ? `当前结论：${context.conclusion}` : "",
    context.position ? `仓位建议：${context.position}` : "",
    context.continueCondition ? `继续条件：${context.continueCondition}` : "",
    context.stopCondition ? `失效条件：${context.stopCondition}` : "",
  ]
    .filter(Boolean)
    .join(" ｜ ");

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="info">{context.code}</Badge>
          <Badge tone="watch">{context.name || "未命名标的"}</Badge>
          <Badge tone="info">{context.sourceLabel || context.source}</Badge>
          {context.intentKey ? <Badge tone="warning">{context.intentKey}</Badge> : null}
        </div>
        <div className="mt-2 text-[12px] text-[var(--text-secondary)]">
          {decisionSummary || "已从个股页带入当前决策上下文。"}
        </div>
      </div>

      {visibleOutcome ? <WritebackOutcomeCard outcome={visibleOutcome} /> : null}

      <div className="flex flex-wrap gap-2">
        {WRITEBACK_ACTIONS.map((item) => (
          <button
            key={item.value}
            type="button"
            onClick={() => setMode(item.value)}
            className={`focus-ring rounded-md border px-3 py-1.5 text-[12px] ${
              mode === item.value
                ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "border-[var(--border-subtle)] text-[var(--text-secondary)]"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
            交易日
            <input
              required
              value={tradeDate}
              onChange={(e) => setTradeDate(e.target.value)}
              className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
            />
          </label>
          <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
            股票代码
            <input
              disabled
              value={context.code}
              className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 py-1 text-[12px] font-mono text-[var(--text-secondary)]"
            />
          </label>
          <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
            股票名称
            <input
              disabled
              value={context.name}
              className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 py-1 text-[12px] text-[var(--text-secondary)]"
            />
          </label>
          <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
            关联意图 key
            <input
              disabled
              value={context.intentKey}
              className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 py-1 text-[12px] font-mono text-[var(--text-secondary)]"
            />
          </label>
        </div>

        {mode === "fill" ? (
          <div className="space-y-3">
            <FillRiskNotice
              confirmed={confirmRealFill}
              onConfirmedChange={setConfirmRealFill}
              checkboxLabel="我确认这笔成交对应当前决策，并且已在外部券商真实发生。"
            />
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
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
                费用
                <input
                  type="number"
                  step="0.01"
                  value={fees}
                  onChange={(e) => setFees(e.target.value)}
                  className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
                />
              </label>
              <label className="flex flex-col text-[11px] text-[var(--text-tertiary)] xl:col-span-2">
                券商订单号 / 备注
                <input
                  value={brokerRef}
                  onChange={(e) => setBrokerRef(e.target.value)}
                  className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
                />
              </label>
              <label className="flex flex-col text-[11px] text-[var(--text-tertiary)] xl:col-span-2">
                补充说明
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="可选"
                  className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
                />
              </label>
            </div>
          </div>
        ) : (
          <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
            {mode === "no_fill" ? "未成交原因" : mode === "watch" ? "继续观察备注" : "放弃原因"}
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={
                mode === "no_fill"
                  ? "例如：挂单未成交 / 条件未满足 / 改为观察"
                  : mode === "watch"
                    ? "例如：条件还没到，继续跟踪"
                    : "例如：触发失效条件，今日放弃"
              }
              className="mt-1 min-h-24 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[12px]"
            />
          </label>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={
              busy ||
              !tradeDate ||
              (requiresIntentKey && !context.intentKey) ||
              (mode === "fill" && (!qty || !price || !confirmRealFill)) ||
              (mode === "no_fill" && !reason.trim())
            }
            className="focus-ring rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-1.5 text-[12px] text-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {mode === "fill"
              ? "提交已成交"
              : mode === "no_fill"
                ? "提交未成交"
                : mode === "watch"
                  ? "提交继续观察"
                  : "提交放弃"}
          </button>
          {requiresIntentKey && !context.intentKey ? (
            <span className="text-[12px] text-[var(--text-tertiary)]">当前没有关联意图 key，这个动作暂不可写回。</span>
          ) : null}
          {feedback ? <span className="text-[12px] text-[var(--tone-positive)]">{feedback}</span> : null}
          {mutationError ? <span className="text-[12px] text-[var(--tone-risk)]">{mutationError}</span> : null}
        </div>
      </form>
    </div>
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
  const today = useTodayData();
  const watchlist = useWatchlist();
  const searchParams = useSearchParams();
  const data = portfolio.data;
  const [optimisticNoFill, setOptimisticNoFill] = useState<NoFillItem | null>(null);
  const [optimisticOutcome, setOptimisticOutcome] = useState<WritebackOutcome | null>(null);
  const [storedOutcome, setStoredOutcome] = useState<WritebackOutcome | null>(null);
  const defaultTradeDate = useMemo(
    () => data?.expected_trade_date || data?.trade_date || todayStr(),
    [data?.expected_trade_date, data?.trade_date],
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
  const writebackContext = useMemo<WritebackContext | null>(() => {
    const code = searchParams.get("code")?.trim() || "";
    const intentKey = searchParams.get("intent_key")?.trim() || searchParams.get("today_action_key")?.trim() || "";

    if (!code) {
      return null;
    }

    return {
      code,
      name: searchParams.get("name")?.trim() || "",
      source: searchParams.get("source")?.trim() || "",
      sourceLabel: searchParams.get("source_label")?.trim() || "",
      tradeDate: searchParams.get("trade_date")?.trim() || defaultTradeDate,
      intentKey,
      conclusion: searchParams.get("conclusion")?.trim() || "",
      position: searchParams.get("position")?.trim() || "",
      continueCondition: searchParams.get("continue_condition")?.trim() || "",
      stopCondition: searchParams.get("stop_condition")?.trim() || "",
    };
  }, [defaultTradeDate, searchParams]);
  const persistedOutcome = useMemo<WritebackOutcome | null>(() => {
    if (!writebackContext) {
      return null;
    }

    const actionDecision =
      today.data?.action_queue?.items?.find((item) => item.key === writebackContext.intentKey)?.decision || null;

    if (actionDecision && (actionDecision.value === "watch" || actionDecision.value === "skip")) {
      return {
        intentKey: writebackContext.intentKey,
        tradeDate: writebackContext.tradeDate,
        code: writebackContext.code,
        name: writebackContext.name,
        resultLabel: decisionLabel(actionDecision.value),
        statusValue: actionDecision.value,
        processedAt: actionDecision.updated_at || actionDecision.updated_at_raw || new Date().toISOString(),
      };
    }

    if (!data) {
      return null;
    }

    const noFillItem =
      [...(data.account.no_fill_intents || [])]
        .reverse()
        .find(
          (item) =>
            item.intent_key === writebackContext.intentKey &&
            item.trade_date === writebackContext.tradeDate,
        ) || null;

    if (noFillItem) {
      return {
        intentKey: writebackContext.intentKey,
        tradeDate: writebackContext.tradeDate,
        code: writebackContext.code,
        name: writebackContext.name,
        resultLabel: "未成交",
        statusValue: "no_fill",
        processedAt: noFillItem.ts,
        note: noFillItem.reason,
      };
    }

    return null;
  }, [data, today.data, writebackContext]);

  useEffect(() => {
    if (!optimisticOutcome || !persistedOutcome) {
      return;
    }

    if (
      optimisticOutcome.intentKey === persistedOutcome.intentKey &&
      optimisticOutcome.tradeDate === persistedOutcome.tradeDate &&
      optimisticOutcome.statusValue === persistedOutcome.statusValue
    ) {
      setOptimisticOutcome(null);
    }
  }, [optimisticOutcome, persistedOutcome]);

  useEffect(() => {
    if (!writebackContext || typeof window === "undefined") {
      setStoredOutcome(null);
      return;
    }

    const raw = window.sessionStorage.getItem(outcomeStorageKey(writebackContext.intentKey, writebackContext.tradeDate));
    if (!raw) {
      setStoredOutcome(null);
      return;
    }

    try {
      const parsed = JSON.parse(raw) as WritebackOutcome;
      setStoredOutcome(parsed);
    } catch {
      setStoredOutcome(null);
    }
  }, [writebackContext]);

  useEffect(() => {
    if (
      !persistedOutcome ||
      (persistedOutcome.statusValue !== "watch" && persistedOutcome.statusValue !== "skip") ||
      typeof window === "undefined"
    ) {
      return;
    }

    window.sessionStorage.removeItem(outcomeStorageKey(persistedOutcome.intentKey, persistedOutcome.tradeDate));
    setStoredOutcome(null);
  }, [persistedOutcome]);

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

        <section className="mb-3">
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">真实账户执行区</div>
        </section>

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

        <section className="mb-7">
          <Panel title="未成交记录" eyebrow="No fill intents" className="surface-card p-4">
            {data ? <NoFillTable items={noFillItems} /> : <SkeletonBlock className="h-24 w-full" />}
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

        <section id="decision-writeback" className="mb-3 scroll-mt-6">
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">决策执行回写区</div>
        </section>

        <section className="mb-7">
          <Panel
            title="单票决策执行回写"
            eyebrow="Decision writeback"
            className="surface-card p-4"
            action={writebackContext ? <Badge tone="warning">来自个股页</Badge> : <Badge tone="info">等待上下文</Badge>}
          >
            <DecisionWritebackPanel
              context={writebackContext}
              defaultTradeDate={defaultTradeDate}
              persistedOutcome={optimisticOutcome || persistedOutcome || storedOutcome}
              onWritebackSuccess={({ outcome, noFillItem }) => {
                setOptimisticOutcome(outcome);
                if (noFillItem) {
                  setOptimisticNoFill(noFillItem);
                }
                void portfolio.refetch();
              }}
            />
          </Panel>
        </section>

        <section className="mb-3">
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">研究自选股区</div>
        </section>

        <section className="mb-7">
          <Panel
            title="研究自选股（不是真持仓）"
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
