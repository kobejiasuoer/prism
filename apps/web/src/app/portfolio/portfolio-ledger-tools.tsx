"use client";

import { useState } from "react";

import { Badge } from "@/components/badge";
import { Panel } from "@/components/data-card";
import {
  useRecordPortfolioCash,
  useRecordPortfolioReconcile,
  useSetPortfolioMode,
} from "@/lib/hooks";
import type { AccountMode, PortfolioAccountResponse } from "@/lib/types";
import { ApiError } from "@/lib/api";
import { formStatusTone } from "./portfolio-form-utils";
import { formatMoney } from "./portfolio-utils";

const MODE_OPTIONS: Array<{ value: AccountMode; label: string; hint: string }> =
  [
    { value: "research", label: "研究态", hint: "仅研究 / 复盘，无真钱" },
    { value: "shadow", label: "影子盘", hint: "记录意图但不入金" },
    { value: "live_small", label: "小额实盘", hint: "已入金、需对账" },
  ];

function ModeSwitch({ data }: { data: PortfolioAccountResponse }) {
  const mutation = useSetPortfolioMode();
  const [startingCash, setStartingCash] = useState<string>(
    String(data.account.starting_cash || ""),
  );
  const [showUnsafeControls, setShowUnsafeControls] = useState(false);
  const [allowUnsafe, setAllowUnsafe] = useState(false);
  const [unsafeNote, setUnsafeNote] = useState("");
  const [unsafeConfirmText, setUnsafeConfirmText] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const handle = (mode: AccountMode) => {
    const useUnsafeBypass = mode === "live_small" && allowUnsafe;
    setSuccessMessage("");
    mutation.mutate(
      {
        mode,
        starting_cash: startingCash ? Number(startingCash) : undefined,
        allow_unsafe: useUnsafeBypass,
        note: useUnsafeBypass ? unsafeNote : undefined,
      },
      {
        onSuccess: (response) => {
          setSuccessMessage(
            `已切换到 ${response.account.mode_label || mode}。`,
          );
        },
      },
    );
  };

  const errorMsg =
    mutation.error instanceof ApiError ? mutation.error.message : null;
  const unsafeConfirmReady = unsafeConfirmText.trim() === "LIVE_SMALL";
  const unsafeBlocked =
    allowUnsafe && (!unsafeNote.trim() || !unsafeConfirmReady);
  const latestModeChange = [...(data.account.mode_history || [])].reverse()[0];

  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge
            tone={
              data.account.mode_tone === "risk"
                ? "risk"
                : data.account.mode_tone === "watch"
                  ? "watch"
                  : "info"
            }
          >
            {data.account.mode_label || data.account.mode}
          </Badge>
          <span className="text-[12px] text-[var(--text-secondary)]">
            当前模式自 {data.account.mode_updated_at || "未记录"} 生效
          </span>
        </div>
        {latestModeChange ? (
          <div className="mt-1 text-[11px] leading-5 text-[var(--text-tertiary)]">
            最近切换：{latestModeChange.from_mode || "-"} →{" "}
            {latestModeChange.to_mode || "-"} · {latestModeChange.ts || "-"}
            {latestModeChange.allow_unsafe ? " · bypass" : ""}
            {latestModeChange.note ? ` · ${latestModeChange.note}` : ""}
          </div>
        ) : (
          <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">
            没有模式切换历史。
          </div>
        )}
        {data.account.unsafe_bypass_active ? (
          <div className="mt-1 text-[11px] leading-5 text-[var(--tone-risk)]">
            当前存在 unsafe bypass：
            {data.account.unsafe_bypass_note ||
              data.account.unsafe_bypass_at ||
              "未记录原因"}
          </div>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {MODE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            disabled={
              mutation.isPending ||
              (opt.value === "live_small" && unsafeBlocked)
            }
            onClick={() => handle(opt.value)}
            className={`focus-ring rounded-md border px-3 py-1.5 text-[12px] ${
              data.account.mode === opt.value
                ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "border-[var(--border-subtle)] text-[var(--text-secondary)]"
            }`}
          >
            {opt.label}
            <span className="ml-1 text-[10px] text-[var(--text-tertiary)]">
              {opt.hint}
            </span>
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
          <div className="mb-2 font-medium text-[var(--tone-risk)]">
            仅在紧急修账时使用 allow_unsafe
          </div>
          <div className="mb-3">
            这会把当前模式标记成 bypass 风险态，readiness
            不会显示为绿色。启用前必须填写原因，并输入确认文本。
          </div>
          <label className="mb-3 flex items-center gap-2">
            <input
              type="checkbox"
              checked={allowUnsafe}
              onChange={(e) => setAllowUnsafe(e.target.checked)}
            />
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
      {mutation.isPending ? (
        <div className="text-[12px] text-[var(--text-tertiary)]">
          正在切换运行模式...
        </div>
      ) : null}
      {unsafeBlocked ? (
        <div className="text-[12px] text-[var(--tone-watch)]">
          启用 bypass 时，需要填写原因并输入 LIVE_SMALL。
        </div>
      ) : null}
      {successMessage ? (
        <div className="text-[12px] text-[var(--tone-positive)]">
          {successMessage}
        </div>
      ) : null}
      {errorMsg ? (
        <div className="text-[12px] text-[var(--tone-risk)]">{errorMsg}</div>
      ) : null}
    </div>
  );
}

function CashAdjustForm({ suggestedDeposit }: { suggestedDeposit?: number }) {
  const mutation = useRecordPortfolioCash();
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("");
  const [touchedSubmit, setTouchedSubmit] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const hasSuggestedDeposit =
    typeof suggestedDeposit === "number" && suggestedDeposit > 0;

  const disabledReason = !delta.trim()
    ? "请先填写现金变动金额。"
    : Number(delta) === 0 || !Number.isFinite(Number(delta))
      ? "现金变动必须是非零数字。"
      : !reason.trim()
        ? "请先填写原因。"
        : "";

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setTouchedSubmit(true);
    setSuccessMessage("");
    if (disabledReason) return;
    mutation.mutate(
      { delta: Number(delta), reason },
      {
        onSuccess: (response) => {
          setSuccessMessage(
            `已记录现金调整，当前现金 ${formatMoney(response.account.cash_balance)}。`,
          );
          setDelta("");
          setReason("");
          setTouchedSubmit(false);
        },
      },
    );
  };

  const errorMsg =
    mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <form
      onSubmit={submit}
      noValidate
      className="flex flex-wrap items-end gap-2"
    >
      {hasSuggestedDeposit ? (
        <div className="basis-full rounded-md border border-[color-mix(in_srgb,var(--tone-risk)_28%,transparent)] bg-[color-mix(in_srgb,var(--tone-risk)_7%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
          <div className="font-medium text-[var(--tone-risk)]">
            当前现金为负，建议先补录入金 {formatMoney(suggestedDeposit)}。
          </div>
          <button
            type="button"
            onClick={() => {
              setDelta(String(suggestedDeposit));
              setReason("补录券商入金 / 初始现金");
              setTouchedSubmit(false);
              setSuccessMessage("");
            }}
            className="focus-ring mt-2 rounded-md border border-[var(--border-subtle)] px-3 py-1 text-[11px] text-[var(--text-primary)]"
          >
            预填入金
          </button>
        </div>
      ) : null}
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
        {mutation.isPending ? "记录中..." : "记录现金调整"}
      </button>
      {touchedSubmit && disabledReason ? (
        <div className={`basis-full text-[12px] ${formStatusTone("warning")}`}>
          {disabledReason}
        </div>
      ) : null}
      {successMessage ? (
        <div className={`basis-full text-[12px] ${formStatusTone("success")}`}>
          {successMessage}
        </div>
      ) : null}
      {errorMsg ? (
        <div className="basis-full text-[12px] text-[var(--tone-risk)]">
          {errorMsg}
        </div>
      ) : null}
    </form>
  );
}

function ReconcileForm({
  defaultTradeDate,
  suggestedCash,
  suggestedEquity,
}: {
  defaultTradeDate: string;
  suggestedCash?: number;
  suggestedEquity?: number;
}) {
  const mutation = useRecordPortfolioReconcile();
  const [trade_date, setTradeDate] = useState(defaultTradeDate);
  const [broker_cash, setBrokerCash] = useState("");
  const [broker_equity, setBrokerEquity] = useState("");
  const [note, setNote] = useState("");
  const [touchedSubmit, setTouchedSubmit] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");

  const disabledReason = !trade_date.trim()
    ? "请先填写对账日。"
    : broker_cash.trim() === "" || !Number.isFinite(Number(broker_cash))
      ? "请先填写券商现金。"
      : broker_equity.trim() === "" || !Number.isFinite(Number(broker_equity))
        ? "请先填写券商持仓市值。"
        : "";

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setTouchedSubmit(true);
    setSuccessMessage("");
    if (disabledReason) return;
    mutation.mutate(
      {
        trade_date,
        broker_cash: Number(broker_cash),
        broker_equity: Number(broker_equity),
        note: note || undefined,
      },
      {
        onSuccess: (response) => {
          const reconciliations = response.account.reconciliations || [];
          const lastRecon = reconciliations[reconciliations.length - 1];
          setSuccessMessage(
            lastRecon
              ? `已记录对账，现金差异 ${formatMoney(lastRecon.delta_cash)}，持仓差异 ${formatMoney(lastRecon.delta_equity)}。`
              : "已记录对账。",
          );
          setBrokerCash("");
          setBrokerEquity("");
          setNote("");
          setTouchedSubmit(false);
        },
      },
    );
  };

  const errorMsg =
    mutation.error instanceof ApiError ? mutation.error.message : null;

  return (
    <form
      onSubmit={submit}
      noValidate
      className="grid grid-cols-2 gap-2 sm:grid-cols-4"
    >
      <div className="col-span-full flex flex-wrap items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
        <span>
          用本地账本预填：现金 {formatMoney(suggestedCash)}，持仓成本{" "}
          {formatMoney(suggestedEquity)}
        </span>
        <button
          type="button"
          onClick={() => {
            setBrokerCash(String(suggestedCash ?? 0));
            setBrokerEquity(String(suggestedEquity ?? 0));
            setNote("按本地账本预填，待券商 App 核对");
            setTouchedSubmit(false);
            setSuccessMessage("");
          }}
          className="focus-ring rounded-md border border-[var(--border-subtle)] px-2 py-1 text-[11px] text-[var(--text-primary)]"
        >
          预填
        </button>
      </div>
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
          {mutation.isPending ? "记录中..." : "记录对账"}
        </button>
      </div>
      {touchedSubmit && disabledReason ? (
        <div
          className={`col-span-full text-[12px] ${formStatusTone("warning")}`}
        >
          {disabledReason}
        </div>
      ) : null}
      {successMessage ? (
        <div
          className={`col-span-full text-[12px] ${formStatusTone("success")}`}
        >
          {successMessage}
        </div>
      ) : null}
      {errorMsg ? (
        <div className="col-span-full text-[12px] text-[var(--tone-risk)]">
          {errorMsg}
        </div>
      ) : null}
    </form>
  );
}

export function PortfolioLedgerTools({
  data,
  defaultTradeDate,
}: {
  data: PortfolioAccountResponse;
  defaultTradeDate: string;
}) {
  const negativeCash =
    data.account.cash_balance < 0 ? Math.abs(data.account.cash_balance) : 0;

  return (
    <section className="mb-7 grid grid-cols-1 gap-4 xl:grid-cols-3">
      <div id="mode-switch" className="scroll-mt-6">
        <Panel title="切换运行模式" eyebrow="Mode" className="surface-card p-4">
          <ModeSwitch data={data} />
        </Panel>
      </div>
      <div id="cash-adjust" className="scroll-mt-6">
        <Panel title="现金调整" eyebrow="Cash" className="surface-card p-4">
          <CashAdjustForm suggestedDeposit={negativeCash || undefined} />
        </Panel>
      </div>
      <div id="reconcile-form" className="scroll-mt-6">
        <Panel
          title="对账（按券商真实数据）"
          eyebrow="Reconcile"
          className="surface-card p-4"
        >
          <ReconcileForm
            defaultTradeDate={defaultTradeDate}
            suggestedCash={data.account.cash_balance}
            suggestedEquity={data.account.equity_at_cost}
          />
        </Panel>
      </div>
    </section>
  );
}
