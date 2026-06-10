"use client";

import { ChevronDown, Database, RefreshCw, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/badge";
import { SkeletonBlock } from "@/components/data-card";
import { useTodayActionContracts } from "@/lib/hooks";
import type {
  DecisionContract,
  DecisionContractConstraint,
  TodayActionsData,
  TodayActionItem,
  TodayActionRegister,
} from "@/lib/types";

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

function ContractRow({ item, contract }: { item: TodayActionItem; contract?: DecisionContract }) {
  const constraints = contract?.execution_constraints || [];
  const requirements = contract?.data_requirements || [];
  const critical = requirements.filter((row) => row.relationship === "critical").slice(0, 3);
  const constraintsCount = contract?.execution_constraints_count ?? constraints.length;

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
          {constraintsCount > 1 ? <span className="ml-1 text-[var(--text-tertiary)]">+{constraintsCount - 1}</span> : null}
        </div>
      ) : null}
    </li>
  );
}

function DecisionContractPanel({
  actions,
  contracts,
}: {
  actions?: TodayActionsData;
  contracts?: TodayActionsData["decision_contracts"];
}) {
  const queue = actions?.action_queue;
  const summary = contracts?.summary || {};
  const contractsByKey = contracts?.by_action_key || {};
  const actionItems = [...(queue?.items || []), ...(queue?.stale_items || [])]
    .filter((item) => contractsByKey[item.key])
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
          <ContractRow key={`${item.key}-${contractsByKey[item.key]?.contract_id}`} item={item} contract={contractsByKey[item.key]} />
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

export function TodayActionDetails({
  actions,
}: {
  actions?: TodayActionsData;
}) {
  const [contractsOpen, setContractsOpen] = useState(false);
  const inlineContracts = actions?.decision_contracts;
  const contracts = useTodayActionContracts({
    enabled: Boolean(contractsOpen && actions?.decision_contracts_deferred && !inlineContracts),
  });
  const contractsPayload = inlineContracts || contracts.data?.decision_contracts;

  return (
    <>
      <ActionRegisterStrip register={actions?.action_register} />
      <details
        open={contractsOpen}
        className="group rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]"
        onToggle={(event) => setContractsOpen(event.currentTarget.open)}
      >
        <summary className="focus-ring flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-wide text-[var(--text-tertiary)]">Decision Contract</div>
            <h2 className="mt-1 text-[15px] font-semibold text-[var(--text-primary)]">动作契约</h2>
            <p className="mt-1 line-clamp-1 text-[12px] text-[var(--text-secondary)]">
              展开后读取执行约束、能力依赖和真钱放行状态。
            </p>
          </div>
          <span className="flex shrink-0 items-center gap-2">
            <Badge tone={contracts.isFetching ? "info" : inlineContracts || contracts.data ? "positive" : "watch"}>
              {contracts.isFetching ? "读取中" : inlineContracts || contracts.data ? "已加载" : "按需加载"}
            </Badge>
            <ChevronDown size={16} className="text-[var(--text-tertiary)] transition group-open:rotate-180" />
          </span>
        </summary>
        {contractsOpen ? (
          <div className="border-t border-[var(--border-subtle)] p-4">
            {contracts.isLoading && !contracts.data && !inlineContracts ? (
              <SkeletonBlock className="h-32 w-full" />
            ) : contracts.isError && !contracts.data ? (
              <div className="rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                动作契约暂不可用
                <button
                  type="button"
                  className="focus-ring ml-3 inline-flex h-7 items-center gap-1 rounded-md border border-[var(--border-subtle)] px-2 text-[11px] text-[var(--text-primary)]"
                  onClick={() => void contracts.refetch()}
                >
                  <RefreshCw size={12} />
                  重试
                </button>
              </div>
            ) : contractsPayload ? (
              <DecisionContractPanel actions={actions} contracts={contractsPayload} />
            ) : (
              <div className="rounded-md border border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-tertiary)]">
                暂无动作契约。
              </div>
            )}
          </div>
        ) : null}
      </details>
    </>
  );
}
