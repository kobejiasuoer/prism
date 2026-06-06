"use client";

import { AlertCircle, Database, FileDown, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useRuns, useRefreshStatus, useTodayActions, useTodaySummary } from "@/lib/hooks";

import { Badge } from "@/components/badge";
import {
  CommandHeader,
  JudgementChain,
  ActionLanes,
  MiddayVerify,
  TrustFold,
} from "@/components/command-brief";
import { SkeletonBlock } from "@/components/data-card";
import { TrustBanner } from "@/components/trust-banner";
import type { DecisionContract, DecisionContractConstraint, TodayActionsData, TodayActionItem, TodayActionRegister } from "@/lib/types";

function contractTone(contract?: DecisionContract) {
  if (contract?.allowed_for_real_money) {
    return "positive";
  }
  if (contract?.allowed_for_formal_action) {
    return "watch";
  }
  return "risk";
}

function contractLabel(contract?: DecisionContract) {
  if (contract?.allowed_for_real_money) {
    return "真钱可执行";
  }
  if (contract?.allowed_for_formal_action) {
    return "可正式复核";
  }
  return "只读复核";
}

function constraintMessage(constraint?: DecisionContractConstraint) {
  return constraint?.message || constraint?.label || constraint?.code || "约束未命名";
}

function ContractRow({ item }: { item: TodayActionItem }) {
  const contract = item.decision_contract;
  const constraints = contract?.execution_constraints || [];
  const requirements = contract?.data_requirements || [];
  const critical = requirements.filter((row) => row.relationship === "critical").slice(0, 3);

  return (
    <li className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-[12px] font-medium text-[var(--text-primary)]">{item.title}</div>
          <div className="mt-0.5 font-mono text-[11px] text-[var(--text-tertiary)]">{contract?.action_key || item.key}</div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          <Badge tone={contractTone(contract)}>{contractLabel(contract)}</Badge>
          {contract?.decision_scope ? <Badge tone="info">{contract.decision_scope}</Badge> : null}
        </div>
      </div>

      <div className="mt-2 grid gap-2 text-[11px] text-[var(--text-secondary)] sm:grid-cols-2">
        <div>
          <span className="text-[var(--text-tertiary)]">能力</span>{" "}
          {(contract?.required_capabilities || []).join(" / ") || "-"}
        </div>
        <div>
          <span className="text-[var(--text-tertiary)]">Ledger</span>{" "}
          {contract?.ledger_capture_key || "-"}
        </div>
      </div>

      {critical.length ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {critical.map((row) => (
            <span
              key={`${item.key}-${row.dataset}`}
              className="inline-flex items-center gap-1 rounded border border-[var(--border-subtle)] px-1.5 py-0.5 text-[11px] text-[var(--text-tertiary)]"
            >
              <Database size={11} />
              {row.label || row.dataset}
              <em className="font-mono not-italic">{row.state || "-"}</em>
            </span>
          ))}
        </div>
      ) : null}

      {constraints.length ? (
        <div className="mt-2 rounded border border-[var(--border-warn)] bg-[var(--surface-warn)] px-2 py-1.5 text-[11px] text-[var(--text-warn)]">
          {constraintMessage(constraints[0])}
          {constraints.length > 1 ? <span className="ml-1 text-[var(--text-tertiary)]">+{constraints.length - 1}</span> : null}
        </div>
      ) : null}
    </li>
  );
}

function DecisionContractPanel({ data }: { data?: TodayActionsData }) {
  const queue = data?.action_queue;
  const contracts = data?.decision_contracts || queue?.decision_contracts;
  const summary = contracts?.summary || {};
  const actionItems = [...(queue?.items || []), ...(queue?.stale_items || [])]
    .filter((item) => item.decision_contract)
    .slice(0, 5);

  if (!contracts || !actionItems.length) {
    return null;
  }

  const allowed = Number(summary.real_money_allowed || 0);
  const blocked = Number(summary.blocked || 0);

  return (
    <section
      id="decision-contracts"
      className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4"
      data-od-id="decision-contracts"
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Decision Contract</div>
          <h2 className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">动作契约</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone={allowed > 0 ? "positive" : "warning"}>
            <ShieldCheck size={12} /> 钱实盘 {allowed}
          </Badge>
          <Badge tone={blocked > 0 ? "risk" : "positive"}>
            <ShieldAlert size={12} /> 阻塞 {blocked}
          </Badge>
        </div>
      </header>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
          <div className="text-[11px] text-[var(--text-tertiary)]">总契约</div>
          <div className="mt-1 text-[18px] font-semibold text-[var(--text-primary)]">{summary.total ?? actionItems.length}</div>
        </div>
        <div className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
          <div className="text-[11px] text-[var(--text-tertiary)]">正式放行</div>
          <div className="mt-1 text-[18px] font-semibold text-[var(--text-primary)]">{summary.formal_allowed ?? 0}</div>
        </div>
        <div className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
          <div className="text-[11px] text-[var(--text-tertiary)]">真钱可执行</div>
          <div className="mt-1 text-[18px] font-semibold text-[var(--text-primary)]">{allowed}</div>
        </div>
        <div className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
          <div className="text-[11px] text-[var(--text-tertiary)]">复盘义务</div>
          <div className="mt-1 text-[18px] font-semibold text-[var(--text-primary)]">{summary.review_required ?? 0}</div>
        </div>
      </div>

      <ul className="mt-3 grid gap-2 lg:grid-cols-2">
        {actionItems.map((item) => (
          <ContractRow key={`${item.key}-${item.decision_contract?.contract_id}`} item={item} />
        ))}
      </ul>
    </section>
  );
}

function writebackLabel(value?: string) {
  if (value === "writable") {
    return "可写回动作";
  }
  if (value === "stale") {
    return "旧线索只读";
  }
  return "命令建议";
}

function writebackTone(value?: string) {
  if (value === "writable") {
    return "positive";
  }
  if (value === "stale") {
    return "warning";
  }
  return "info";
}

function ActionRegisterStrip({ register }: { register?: TodayActionRegister }) {
  const items = register?.items || [];
  if (!register || !items.length) {
    return null;
  }
  const counts = register.counts || {};

  return (
    <section className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Action Semantics</div>
          <h2 className="mt-1 text-[15px] font-semibold text-[var(--text-primary)]">今日动作口径</h2>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Badge tone="positive">可写回 {counts.writable ?? 0}</Badge>
          <Badge tone="info">建议 {counts.read_only ?? 0}</Badge>
          <Badge tone="warning">旧线索 {counts.stale ?? 0}</Badge>
        </div>
      </div>
      <div className="grid gap-2 lg:grid-cols-3">
        {items.slice(0, 6).map((item) => (
          <a
            key={`${item.source}-${item.intent_key}`}
            href={item.url || "#"}
            className="focus-ring rounded-md border border-[var(--border-subtle)] px-3 py-2 text-left hover:bg-[var(--bg-tertiary)]"
          >
            <div className="flex min-w-0 items-center justify-between gap-2">
              <span className="truncate text-[12px] font-medium text-[var(--text-primary)]">{item.title}</span>
              <Badge tone={writebackTone(item.writeback_status)}>{writebackLabel(item.writeback_status)}</Badge>
            </div>
            <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
              {item.action_label || "-"} · {item.writeback_reason || item.detail || "等待复核"}
            </div>
          </a>
        ))}
      </div>
    </section>
  );
}

export default function CommandCenterPage() {
  const today = useTodaySummary();
  const [actionsEnabled, setActionsEnabled] = useState(false);
  const todayActions = useTodayActions({ enabled: actionsEnabled });
  const runsQuery = useRuns();
  const refreshStatus = useRefreshStatus("today", true, { auto: true });
  const data = today.data;
  const actionsData = todayActions.data;
  const brief = data?.command_brief;
  const loadingBrief = today.isLoading && !data;
  const trust = data?.readiness?.trust_level;
  const tradeDate = brief?.trade_date || data?.expected_trade_date || data?.trade_date || "-";

  useEffect(() => {
    if (!today.data || actionsEnabled) {
      return undefined;
    }

    const timer = window.setTimeout(() => setActionsEnabled(true), 900);
    return () => window.clearTimeout(timer);
  }, [actionsEnabled, today.data]);

  return (
    <main className="war-room">
      <div className="war-room-inner">
        <header className="war-topbar">
          <div>
            <div className="war-eyebrow">Daily Command Brief</div>
            <h1>每日交易命令台</h1>
          </div>
          <div className="war-top-actions">
            <button
              type="button"
              className="focus-ring war-tool-btn"
              onClick={() => {
                void today.refetch();
                if (actionsEnabled) {
                  void todayActions.refetch();
                } else {
                  setActionsEnabled(true);
                }
              }}
            >
              <RefreshCw size={14} className={today.isFetching || todayActions.isFetching ? "animate-spin" : ""} />
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

        {trust ? <TrustBanner trust={trust} readiness={data?.readiness} className="mb-4" /> : null}

        {today.isError ? (
          <div className="war-error">
            <AlertCircle size={17} className="mt-0.5 shrink-0 text-[var(--warning)]" />
            <div className="min-w-0 flex-1">
              <div className="font-medium text-[var(--text-primary)]">后端数据暂不可用</div>
              <div className="mt-1">命令台骨架已加载，FastAPI 启动后会自动重新获取 `/api/today/summary`。</div>
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

        {brief ? (
          <>
            <CommandHeader
              mode={brief.mode}
              permits={brief.permits}
              positionCap={brief.position_cap}
              firstAction={brief.first_action}
              forbid={brief.forbid_today}
              reclassify={brief.reclassify_when}
              tradeDate={tradeDate}
            />
            <JudgementChain items={brief.judgement_chain} />
            <ActionLanes lanes={brief.action_lanes} />
            <MiddayVerify payload={brief.midday_verify} />
            <TrustFold trust={brief.trust}>
              <div className="text-[12px] text-[var(--text-secondary)]">
                运行记录 {runsQuery.data?.runs?.length ?? 0} 条 · 自动刷新 {refreshStatus.data?.recommended_task?.title ?? "-"}
              </div>
            </TrustFold>
            <ActionRegisterStrip register={actionsData?.action_register || data?.action_register} />
          </>
        ) : loadingBrief ? (
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
            <div className="mb-3 flex items-center gap-2 text-[13px] text-[var(--text-secondary)]">
              <RefreshCw size={14} className="animate-spin" />
              正在读取今日命令台和数据可信度
            </div>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <SkeletonBlock key={index} className="h-28 w-full" />
              ))}
            </div>
          </div>
        ) : !today.isError ? (
          <div className="war-error">
            <AlertCircle size={17} className="mt-0.5 shrink-0 text-[var(--warning)]" />
            <div className="min-w-0 flex-1">
              <div className="font-medium text-[var(--text-primary)]">命令台数据未到位</div>
              <div className="mt-1">后端尚未返回 `command_brief`；先到 Settings 跑安全刷新。</div>
            </div>
          </div>
        ) : null}

        {todayActions.isFetching && !actionsData ? (
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            正在懒加载可写回动作队列与动作契约
          </div>
        ) : null}
        <DecisionContractPanel data={actionsData} />
      </div>
    </main>
  );
}
