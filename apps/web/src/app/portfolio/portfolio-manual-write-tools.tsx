"use client";

import { Pencil, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import {
  useAmendPortfolioHoldingIdentity,
  useRecordPortfolioFill,
} from "@/lib/hooks";
import type { PortfolioAccountResponse } from "@/lib/types";
import { ApiError } from "@/lib/api";
import { FillRiskNotice, formStatusTone } from "./portfolio-form-utils";
import { formatMoney } from "./portfolio-utils";

const SIDE_OPTIONS: Array<{ value: "buy" | "sell"; label: string }> = [
  { value: "buy", label: "买入" },
  { value: "sell", label: "卖出" },
];

export type FillDraft = {
  code: string;
  name: string;
  side: "buy" | "sell";
  tradeDate?: string;
  intentKey?: string;
  brokerRef?: string;
  qty?: number | string;
  price?: number | string;
};

export type IdentityDraft = {
  fromCode: string;
  toCode: string;
  name?: string;
  reason?: string;
};

export type FillFormProps = {
  defaultTradeDate: string;
  draft?: FillDraft | null;
};

export type IdentityCorrectionFormProps = {
  draft?: IdentityDraft | null;
  onSaved?: () => void;
};

function isPositiveNumber(value: string): boolean {
  const parsed = Number(value);
  return value.trim() !== "" && Number.isFinite(parsed) && parsed > 0;
}

export function FillForm({ defaultTradeDate, draft }: FillFormProps) {
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
  const [touchedSubmit, setTouchedSubmit] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    if (!draft) return;
    setTradeDate(draft.tradeDate || defaultTradeDate);
    setCode(draft.code.toLowerCase());
    setName(draft.name || "");
    setSide(draft.side);
    setIntent(draft.intentKey || "");
    setBroker(draft.brokerRef || "");
    setQty(
      draft.qty !== undefined && draft.qty !== null ? String(draft.qty) : "",
    );
    setPrice(
      draft.price !== undefined && draft.price !== null
        ? String(draft.price)
        : "",
    );
    setTouchedSubmit(false);
    setSuccessMessage("");
  }, [defaultTradeDate, draft]);

  const disabledReason = !confirmRealFill
    ? "请先勾选真实成交确认。"
    : !trade_date.trim()
      ? "请先填写交易日。"
      : !code.trim()
        ? "请先填写股票代码。"
        : !isPositiveNumber(qty)
          ? "请先填写大于 0 的数量。"
          : !isPositiveNumber(price)
            ? "请先填写大于 0 的成交价。"
            : fees.trim() &&
                (!Number.isFinite(Number(fees)) || Number(fees) < 0)
              ? "费用必须是大于等于 0 的数字。"
              : "";

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setTouchedSubmit(true);
    setSuccessMessage("");
    if (disabledReason) return;
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
        onSuccess: (response: PortfolioAccountResponse) => {
          setSuccessMessage(
            `已录入成交，当前现金 ${formatMoney(response.account.cash_balance)}。`,
          );
          setQty("");
          setPrice("");
          setFees("");
          setBroker("");
          setConfirmRealFill(false);
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
          onChange={(event) => setTradeDate(event.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        代码（如 sh600690）
        <input
          required
          value={code}
          onChange={(event) => setCode(event.target.value.toLowerCase())}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px] font-mono"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        名称（可空，自动取 watchlist）
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        方向
        <select
          value={side}
          onChange={(event) => setSide(event.target.value as "buy" | "sell")}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        >
          {SIDE_OPTIONS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
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
          onChange={(event) => setQty(event.target.value)}
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
          onChange={(event) => setPrice(event.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        费用（可空）
        <input
          type="number"
          step="0.01"
          value={fees}
          onChange={(event) => setFees(event.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        关联意图 key（可空）
        <input
          value={intent_key}
          onChange={(event) => setIntent(event.target.value)}
          placeholder="如 wl-priority-sh600690"
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px] font-mono"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)] sm:col-span-2">
        券商订单号 / 备注（可空）
        <input
          value={broker_ref}
          onChange={(event) => setBroker(event.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <div className="flex items-end sm:col-span-2">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="focus-ring rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-1.5 text-[12px] text-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {mutation.isPending ? "录入中..." : "录入成交"}
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

export function IdentityCorrectionForm({
  draft,
  onSaved,
}: IdentityCorrectionFormProps) {
  const mutation = useAmendPortfolioHoldingIdentity();
  const [fromCode, setFromCode] = useState("");
  const [toCode, setToCode] = useState("");
  const [name, setName] = useState("");
  const [reason, setReason] = useState("录入代码修正");
  const [touchedSubmit, setTouchedSubmit] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    if (!draft) return;
    setFromCode(draft.fromCode.toLowerCase());
    setToCode(draft.toCode.toLowerCase());
    setName(draft.name || "");
    setReason(draft.reason || "录入代码修正");
    setTouchedSubmit(false);
    setSuccessMessage("");
  }, [draft]);

  const disabledReason = !fromCode.trim()
    ? "请填写原代码。"
    : !toCode.trim()
      ? "请填写新代码。"
      : !reason.trim()
        ? "请填写更正原因。"
        : "";

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setTouchedSubmit(true);
    setSuccessMessage("");
    if (disabledReason) return;
    mutation.mutate(
      {
        from_code: fromCode.trim(),
        to_code: toCode.trim(),
        name: name.trim() || undefined,
        reason: reason.trim(),
      },
      {
        onSuccess: (response: PortfolioAccountResponse) => {
          const corrected = response.account.open_positions.find(
            (item) => item.code === toCode.trim(),
          );
          setSuccessMessage(
            `已更正为 ${corrected?.name || name || toCode.trim()} ${toCode.trim()}。`,
          );
          setTouchedSubmit(false);
          onSaved?.();
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
      className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-5"
    >
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        原代码
        <input
          value={fromCode}
          onChange={(event) => setFromCode(event.target.value.toLowerCase())}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px] font-mono"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        新代码
        <input
          value={toCode}
          onChange={(event) => setToCode(event.target.value.toLowerCase())}
          placeholder="如 sz000625"
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px] font-mono"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
        名称
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="可空，自动查询"
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <label className="flex flex-col text-[11px] text-[var(--text-tertiary)] xl:col-span-2">
        更正原因
        <input
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
        />
      </label>
      <div className="flex items-end">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-[var(--accent)] bg-[var(--accent-soft)] px-3 py-1.5 text-[12px] text-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {mutation.isPending ? (
            <RefreshCw size={13} className="animate-spin" />
          ) : (
            <Pencil size={13} />
          )}
          {mutation.isPending ? "保存中..." : "保存更正"}
        </button>
      </div>
      {touchedSubmit && disabledReason ? (
        <div
          className={`sm:col-span-2 xl:col-span-5 text-[12px] ${formStatusTone("warning")}`}
        >
          {disabledReason}
        </div>
      ) : null}
      {successMessage ? (
        <div
          className={`sm:col-span-2 xl:col-span-5 text-[12px] ${formStatusTone("success")}`}
        >
          {successMessage}
        </div>
      ) : null}
      {errorMsg ? (
        <div className="sm:col-span-2 xl:col-span-5 text-[12px] text-[var(--tone-risk)]">
          {errorMsg}
        </div>
      ) : null}
    </form>
  );
}
