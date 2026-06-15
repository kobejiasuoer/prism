"use client";

import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/badge";
import {
  useRecordPortfolioFill,
  useRecordPortfolioNoFill,
  useTodayActions,
  useUpdateTodayActionDecision,
} from "@/lib/hooks";
import type { DecisionValue } from "@/lib/types";
import { ApiError } from "@/lib/api";

import { FillRiskNotice } from "./portfolio-form-utils";
import {
  decisionLabel,
  decisionStatusText,
  formatOutcomeTime,
  outcomeStorageKey,
  type NoFillItem,
  type WritebackContext,
  type WritebackOutcome,
} from "./portfolio-writeback-utils";

type WritebackMode = "fill" | "no_fill" | "watch" | "skip";

const SIDE_OPTIONS: Array<{ value: "buy" | "sell"; label: string }> = [
  { value: "buy", label: "买入" },
  { value: "sell", label: "卖出" },
];

const WRITEBACK_ACTIONS: Array<{ value: WritebackMode; label: string }> = [
  { value: "fill", label: "记录已成交" },
  { value: "no_fill", label: "记录未成交" },
  { value: "watch", label: "继续观察" },
  { value: "skip", label: "放弃" },
];

export type DecisionWritebackPanelProps = {
  defaultTradeDate: string;
  noFillIntents?: NoFillItem[];
  onWritebackSuccess?: (payload: {
    outcome: WritebackOutcome;
    noFillItem?: NoFillItem;
  }) => void;
};

function readWritebackContext(
  defaultTradeDate: string,
): WritebackContext | null {
  if (typeof window === "undefined") {
    return null;
  }

  const params = new URLSearchParams(window.location.search);
  const code = params.get("code")?.trim() || "";
  const intentKey =
    params.get("intent_key")?.trim() ||
    params.get("today_action_key")?.trim() ||
    "";

  if (!code) {
    return null;
  }

  return {
    code,
    name: params.get("name")?.trim() || "",
    source: params.get("source")?.trim() || "",
    sourceLabel: params.get("source_label")?.trim() || "",
    tradeDate: params.get("trade_date")?.trim() || defaultTradeDate,
    intentKey,
    conclusion: params.get("conclusion")?.trim() || "",
    position: params.get("position")?.trim() || "",
    continueCondition: params.get("continue_condition")?.trim() || "",
    stopCondition: params.get("stop_condition")?.trim() || "",
  };
}

function WritebackOutcomeCard({ outcome }: { outcome: WritebackOutcome }) {
  const noteLabel =
    outcome.statusValue === "no_fill"
      ? "原因"
      : outcome.statusValue === "skip"
        ? "放弃原因"
        : "备注";

  return (
    <div className="rounded-md border border-[var(--tone-positive)]/30 bg-[var(--tone-positive)]/10 px-4 py-3 text-[12px] text-[var(--text-secondary)]">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="buy">已处理</Badge>
        <Badge tone={outcome.statusValue === "skip" ? "risk" : "watch"}>
          {outcome.resultLabel}
        </Badge>
        <span className="font-medium text-[var(--text-primary)]">
          {outcome.code} {outcome.name || "未命名标的"}
        </span>
      </div>
      <div className="mt-2 text-[var(--text-secondary)]">
        已处理：{outcome.code} {outcome.name || "未命名标的"}，本次结果为「
        {outcome.resultLabel}」。
      </div>
      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div>
          <div className="text-[11px] text-[var(--text-tertiary)]">
            处理时间
          </div>
          <div>{formatOutcomeTime(outcome.processedAt)}</div>
        </div>
        <div>
          <div className="text-[11px] text-[var(--text-tertiary)]">
            当前状态
          </div>
          <div>{decisionStatusText(outcome.statusValue)}</div>
        </div>
        {outcome.note ? (
          <div className="sm:col-span-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">
              {noteLabel}
            </div>
            <div>{outcome.note}</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function DecisionWritebackPanel({
  defaultTradeDate,
  noFillIntents = [],
  onWritebackSuccess,
}: DecisionWritebackPanelProps) {
  const recordFill = useRecordPortfolioFill();
  const recordNoFill = useRecordPortfolioNoFill();
  const updateDecision = useUpdateTodayActionDecision();
  const [context, setContext] = useState<WritebackContext | null>(null);
  const [mode, setMode] = useState<WritebackMode>("fill");
  const [tradeDate, setTradeDate] = useState(
    context?.tradeDate || defaultTradeDate,
  );
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [fees, setFees] = useState("");
  const [brokerRef, setBrokerRef] = useState("");
  const [reason, setReason] = useState("");
  const [feedback, setFeedback] = useState("");
  const [confirmRealFill, setConfirmRealFill] = useState(false);
  const [lastOutcome, setLastOutcome] = useState<WritebackOutcome | null>(null);
  const [storedOutcome, setStoredOutcome] = useState<WritebackOutcome | null>(
    null,
  );
  const contextResetKey = `${context?.code || ""}|${context?.intentKey || ""}|${context?.tradeDate || ""}`;
  const todayActions = useTodayActions({
    enabled: Boolean(context?.intentKey),
  });

  useEffect(() => {
    const syncContext = () => {
      setContext(readWritebackContext(defaultTradeDate));
    };
    syncContext();

    if (typeof window === "undefined") {
      return undefined;
    }

    window.addEventListener("popstate", syncContext);
    window.addEventListener("hashchange", syncContext);
    return () => {
      window.removeEventListener("popstate", syncContext);
      window.removeEventListener("hashchange", syncContext);
    };
  }, [defaultTradeDate]);

  const persistedOutcome = useMemo<WritebackOutcome | null>(() => {
    if (!context) {
      return null;
    }

    const actionDecision =
      todayActions.data?.action_queue?.items?.find(
        (item) => item.key === context.intentKey,
      )?.decision || null;

    if (
      actionDecision &&
      (actionDecision.value === "watch" || actionDecision.value === "skip")
    ) {
      return {
        intentKey: context.intentKey,
        tradeDate: context.tradeDate,
        code: context.code,
        name: context.name,
        resultLabel: decisionLabel(actionDecision.value),
        statusValue: actionDecision.value,
        processedAt:
          actionDecision.updated_at ||
          actionDecision.updated_at_raw ||
          new Date().toISOString(),
      };
    }

    const noFillItem =
      [...noFillIntents]
        .reverse()
        .find(
          (item) =>
            item.intent_key === context.intentKey &&
            item.trade_date === context.tradeDate,
        ) || null;

    if (noFillItem) {
      return {
        intentKey: context.intentKey,
        tradeDate: context.tradeDate,
        code: context.code,
        name: context.name,
        resultLabel: "未成交",
        statusValue: "no_fill",
        processedAt: noFillItem.ts,
        note: noFillItem.reason,
      };
    }

    return null;
  }, [context, noFillIntents, todayActions.data]);

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
  }, [contextResetKey, context?.tradeDate, defaultTradeDate]);

  useEffect(() => {
    if (!context) {
      setTradeDate(defaultTradeDate);
    }
  }, [context, defaultTradeDate]);

  useEffect(() => {
    if (!context || typeof window === "undefined") {
      setStoredOutcome(null);
      return;
    }

    const raw = window.sessionStorage.getItem(
      outcomeStorageKey(context.intentKey, context.tradeDate),
    );
    if (!raw) {
      setStoredOutcome(null);
      return;
    }

    try {
      setStoredOutcome(JSON.parse(raw) as WritebackOutcome);
    } catch {
      setStoredOutcome(null);
    }
  }, [context]);

  useEffect(() => {
    if (
      !persistedOutcome ||
      (persistedOutcome.statusValue !== "watch" &&
        persistedOutcome.statusValue !== "skip") ||
      typeof window === "undefined"
    ) {
      return;
    }

    window.sessionStorage.removeItem(
      outcomeStorageKey(persistedOutcome.intentKey, persistedOutcome.tradeDate),
    );
    setStoredOutcome(null);
  }, [persistedOutcome]);

  if (!context) {
    return (
      <div className="rounded-md border border-dashed border-[var(--border-subtle)] px-4 py-5 text-[12px] text-[var(--text-tertiary)]">
        从个股页点击“记录执行结果”后，这里会自动带入股票上下文。
      </div>
    );
  }

  const busy =
    recordFill.isPending || recordNoFill.isPending || updateDecision.isPending;
  const requiresIntentKey = mode !== "fill";
  const mutationError =
    (recordFill.error instanceof ApiError ? recordFill.error.message : "") ||
    (recordNoFill.error instanceof ApiError
      ? recordNoFill.error.message
      : "") ||
    (updateDecision.error instanceof ApiError
      ? updateDecision.error.message
      : "");
  const visibleOutcome = lastOutcome || persistedOutcome || storedOutcome;

  const registerOutcome = (payload: {
    resultLabel: string;
    statusValue: "watch" | "skip" | "no_fill";
    note?: string;
    processedAt?: string;
    noFillItem?: NoFillItem;
  }) => {
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
    if (
      (payload.statusValue === "watch" || payload.statusValue === "skip") &&
      typeof window !== "undefined"
    ) {
      window.sessionStorage.setItem(
        outcomeStorageKey(context.intentKey, tradeDate),
        JSON.stringify(outcome),
      );
    }
    onWritebackSuccess?.({ outcome, noFillItem: payload.noFillItem });
  };

  const submitDecision = (
    decision: Extract<DecisionValue, "watch" | "skip">,
    successText: string,
  ) => {
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

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
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
            const savedItem = [...(response.account.no_fill_intents || [])]
              .reverse()
              .find(
                (item) =>
                  item.trade_date === tradeDate &&
                  item.intent_key === context.intentKey,
              ) || {
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
          {context.intentKey ? (
            <Badge tone="warning">{context.intentKey}</Badge>
          ) : null}
        </div>
        <div className="mt-2 text-[12px] text-[var(--text-secondary)]">
          {decisionSummary || "已从个股页带入当前决策上下文。"}
        </div>
      </div>

      {visibleOutcome ? (
        <WritebackOutcomeCard outcome={visibleOutcome} />
      ) : null}

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

      <form onSubmit={submit} noValidate className="space-y-3">
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
            交易日
            <input
              required
              value={tradeDate}
              onChange={(event) => setTradeDate(event.target.value)}
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
                  onChange={(event) =>
                    setSide(event.target.value as "buy" | "sell")
                  }
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
                费用
                <input
                  type="number"
                  step="0.01"
                  value={fees}
                  onChange={(event) => setFees(event.target.value)}
                  className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
                />
              </label>
              <label className="flex flex-col text-[11px] text-[var(--text-tertiary)] xl:col-span-2">
                券商订单号 / 备注
                <input
                  value={brokerRef}
                  onChange={(event) => setBrokerRef(event.target.value)}
                  className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
                />
              </label>
              <label className="flex flex-col text-[11px] text-[var(--text-tertiary)] xl:col-span-2">
                补充说明
                <input
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  placeholder="可选"
                  className="mt-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 py-1 text-[12px]"
                />
              </label>
            </div>
          </div>
        ) : (
          <label className="flex flex-col text-[11px] text-[var(--text-tertiary)]">
            {mode === "no_fill"
              ? "未成交原因"
              : mode === "watch"
                ? "继续观察备注"
                : "放弃原因"}
            <textarea
              value={reason}
              onChange={(event) => setReason(event.target.value)}
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
            <span className="text-[12px] text-[var(--text-tertiary)]">
              当前没有关联意图 key，这个动作暂不可写回。
            </span>
          ) : null}
          {feedback ? (
            <span className="text-[12px] text-[var(--tone-positive)]">
              {feedback}
            </span>
          ) : null}
          {mutationError ? (
            <span className="text-[12px] text-[var(--tone-risk)]">
              {mutationError}
            </span>
          ) : null}
        </div>
      </form>
    </div>
  );
}
