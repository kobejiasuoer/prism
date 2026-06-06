"use client";

import { AlertTriangle, CheckCircle2, Database, Eye, ShieldAlert, WalletCards } from "lucide-react";
import Link from "next/link";

import type { AccountReadinessState, ReadinessPayload, TrustLevel } from "@/lib/types";
import { cn, toneColor } from "@/lib/utils";

const LEVEL_ICON = {
  trusted: CheckCircle2,
  observe_only: Eye,
  unreliable: ShieldAlert,
} as const;

function levelIcon(level: string) {
  if (level === "trusted" || level === "observe_only" || level === "unreliable") {
    return LEVEL_ICON[level];
  }
  return AlertTriangle;
}

function levelTone(trust?: TrustLevel | null): string {
  return trust?.tone || "warning";
}

const PROVIDER_LABELS: Record<string, string> = {
  tushare: "Tushare",
  official_exchange: "交易所/官方公告源",
  official_index: "指数官方源",
  ricequant: "RiceQuant",
  joinquant: "JoinQuant",
  eastmoney: "东方财富",
  sina: "新浪",
  akshare: "AKShare",
  baostock: "BaoStock",
  pipeline: "Prism 快源管线",
};

function providerLabel(value?: string | null) {
  const key = String(value || "").trim();
  return PROVIDER_LABELS[key] || key;
}

function uniqueValues(values: string[]) {
  return values.filter((item, index) => item && values.indexOf(item) === index);
}

function formalGapSummary(readiness?: ReadinessPayload | null) {
  if (!readiness) {
    return null;
  }
  const formalStatus = readiness.formal_data_status;
  const provider = formalStatus?.provider;
  if (formalStatus && provider && !provider.token_configured) {
    return {
      tone: "risk",
      badge: "Tushare Token 未配置",
      title: "正式源还没有真正接入",
      detail: "后端没有读到 PRISM_TUSHARE_TOKEN / TUSHARE_TOKEN；先在本机 .env 配置 token，再刷新正式口径数据。",
      href: "/settings#formal-data",
      action: "去配置",
    };
  }
  if (formalStatus && !formalStatus.ready) {
    const blocker = formalStatus.blockers?.[0];
    const label = blocker?.label || blocker?.dataset || "正式口径数据";
    const state = blocker?.state || "not_ready";
    return {
      tone: state === "rate_limited" ? "warning" : "risk",
      badge: "正式源待补齐",
      title: `${label} 未通过`,
      detail: blocker?.next_action || "正式源 token 已配置后，还需要刷新并补齐当日 formal manifest。",
      href: "/settings#formal-data",
      action: "看状态",
    };
  }
  const sources = readiness.source_freshness || [];
  const formalBlockers = readiness.formal_blockers || [];
  const affected = uniqueValues(
    sources
      .filter((source) => source.manifest_path && !source.formal_decision_allowed)
      .map((source) => source.label || source.key || "")
      .filter(Boolean),
  );
  const targets = uniqueValues(
    sources.flatMap((source) =>
      (source.authority_flags || [])
        .filter((flag) => flag.startsWith("target_authority_not_in_use:"))
        .map((flag) => providerLabel(flag.split(":", 2)[1])),
    ),
  );
  if (readiness.formal_ready && !formalBlockers.length) {
    return {
      tone: "positive",
      badge: "正式口径已通过",
      title: "正式数据口径已满足",
      detail: "当前数据链路可进入正式复核；真钱执行仍受账户模式和对账约束。",
    };
  }
  return {
    tone: "warning",
    badge: "正式口径未接入",
    title: affected.length ? `${affected.slice(0, 3).join("、")} 仍用快源/管线口径` : "正式数据口径尚未通过",
    detail: targets.length
      ? `目标源包括 ${targets.slice(0, 3).join("、")}；现在的快源可以看盘和复核，但不当作正式放行依据。`
      : "现在的快源可以看盘和复核，但不当作正式放行依据。",
  };
}

function accountGapSummary(account?: AccountReadinessState | null) {
  if (!account) {
    return null;
  }
  if (account.mode === "live_small" && account.ready_for_live_small) {
    return {
      tone: "positive",
      badge: "账户可小额实盘",
      title: "账户已对账，可进入小额实盘纪律",
      detail: account.reconciliation?.age_label ? `最近对账 ${account.reconciliation.age_label}。` : "账户模式与对账均已通过。",
      href: "/portfolio#reconcile-form",
      action: "查看对账",
    };
  }
  if (account.mode === "live_small") {
    const reason = account.blockers?.[0]?.message || "live_small 需要现金、对账和未完成动作全部通过。";
    return {
      tone: "risk",
      badge: "实盘未就绪",
      title: "账户在小额实盘，但校验未通过",
      detail: reason,
      href: "/portfolio#reconcile-form",
      action: "补对账",
    };
  }
  if (account.mode === "shadow") {
    return {
      tone: "warning",
      badge: "影子盘",
      title: "账户处于影子盘",
      detail: "可以做动作推演和复盘；真钱执行前需要切到小额实盘并完成对账。",
      href: "/portfolio#mode-switch",
      action: "切换模式",
    };
  }
  return {
    tone: "info",
    badge: "研究态",
    title: "账户被保护在研究态",
    detail: account.mode_updated_at
      ? `上次切换时间 ${account.mode_updated_at}；研究态不会写真实账本或放行真钱执行。`
      : "研究态不会写真实账本或放行真钱执行；需要你手动切换后才会改变。",
    href: "/portfolio#mode-switch",
    action: "查看模式",
  };
}

function formalStatusReason(readiness?: ReadinessPayload | null) {
  const status = readiness?.formal_data_status;
  if (!status || status.ready) {
    return "";
  }
  const provider = status.provider;
  if (provider && !provider.token_configured) {
    return "正式源未接入：后端没有读到 Tushare token；先配置 PRISM_TUSHARE_TOKEN / TUSHARE_TOKEN。";
  }
  const blocker = status.blockers?.[0];
  const label = blocker?.label || blocker?.dataset || "正式数据";
  const keys = [...(blocker?.blocked_request_keys || []), ...(blocker?.missing_request_keys || [])];
  const keyText = keys.length ? `（${keys.slice(0, 3).join(" / ")}）` : "";
  if (blocker?.state === "rate_limited") {
    return `正式源已接入 ${status.ready_count}/${status.total_count}；剩余 ${label}${keyText} 被 Tushare 频控，等接口窗口后补齐。`;
  }
  return `正式源已接入 ${status.ready_count}/${status.total_count}；剩余 ${label}${keyText} 未通过。`;
}

function visibleBlockingReasons(trust: TrustLevel, readiness?: ReadinessPayload | null) {
  const formalReason = formalStatusReason(readiness);
  const source = trust.blocking_reasons || [];
  if (!formalReason) {
    return source;
  }
  const filtered = source.filter((reason) => !reason.startsWith("正式口径未接入") && !reason.includes("正式数据口径尚未通过"));
  return [formalReason, ...filtered];
}

export function TrustBanner({
  trust,
  readiness,
  recoveryHref = "/settings#recovery",
  className,
  compact,
}: {
  trust?: TrustLevel | null;
  readiness?: ReadinessPayload | null;
  recoveryHref?: string;
  className?: string;
  compact?: boolean;
}) {
  if (!trust) {
    return null;
  }
  const Icon = levelIcon(trust.level);
  const color = toneColor(levelTone(trust));
  const showCta = trust.level !== "trusted" && Boolean(trust.next_step);
  const formalGap = formalGapSummary(readiness);
  const accountGap = accountGapSummary(readiness?.account_state);
  const blockingReasons = visibleBlockingReasons(trust, readiness);

  if (compact) {
    return (
      <span
        className={cn("inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium", className)}
        style={{
          color,
          backgroundColor: `color-mix(in srgb, ${color} 10%, transparent)`,
          borderColor: `color-mix(in srgb, ${color} 22%, transparent)`,
        }}
        title={trust.headline}
      >
        <Icon size={11} aria-hidden="true" />
        <span className="truncate">{trust.label}</span>
      </span>
    );
  }

  return (
    <section
      className={cn("surface-card flex flex-col gap-3 p-4 lg:flex-row lg:items-start lg:justify-between", className)}
      style={{
        borderColor: `color-mix(in srgb, ${color} 28%, transparent)`,
        backgroundColor: `color-mix(in srgb, ${color} 6%, transparent)`,
      }}
      role="status"
      aria-live="polite"
      data-trust-level={trust.level}
    >
      <div className="flex min-w-0 items-start gap-3">
        <span
          className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
          style={{ backgroundColor: `color-mix(in srgb, ${color} 16%, transparent)`, color }}
        >
          <Icon size={15} aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium"
              style={{
                color,
                backgroundColor: `color-mix(in srgb, ${color} 12%, transparent)`,
                borderColor: `color-mix(in srgb, ${color} 24%, transparent)`,
              }}
            >
              今日可信度：{trust.label}
            </span>
            {trust.can_trade_live ? (
              <span className="text-[11px] text-[var(--text-tertiary)]">真钱执行：可</span>
            ) : (
              <span className="text-[11px] text-[var(--text-tertiary)]">真钱执行：暂不可</span>
            )}
          </div>
          <h2 className="mt-1 text-[14px] font-semibold leading-5 text-[var(--text-primary)]">
            {trust.headline}
          </h2>
          {blockingReasons.length > 0 ? (
            <ul className="mt-2 space-y-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              {blockingReasons.slice(0, 3).map((reason, idx) => (
                <li key={`${idx}-${reason.slice(0, 12)}`} className="flex gap-2">
                  <span className="text-[var(--text-tertiary)]">·</span>
                  <span className="min-w-0 flex-1">{reason}</span>
                </li>
              ))}
            </ul>
          ) : null}
          {readiness && (formalGap || accountGap) ? (
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {formalGap ? (
                <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
                  <div className="flex items-center gap-2">
                    <Database size={13} style={{ color: toneColor(formalGap.tone) }} />
                    <span className="text-[11px] font-medium" style={{ color: toneColor(formalGap.tone) }}>
                      {formalGap.badge}
                    </span>
                  </div>
                  <div className="mt-1 text-[12px] font-medium text-[var(--text-primary)]">{formalGap.title}</div>
                  <div className="mt-1 text-[11px] leading-4 text-[var(--text-secondary)]">{formalGap.detail}</div>
                  {"href" in formalGap && formalGap.href ? (
                    <Link href={formalGap.href} className="mt-2 inline-flex text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">
                      {formalGap.action}
                    </Link>
                  ) : null}
                </div>
              ) : null}
              {accountGap ? (
                <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <WalletCards size={13} style={{ color: toneColor(accountGap.tone) }} />
                      <span className="truncate text-[11px] font-medium" style={{ color: toneColor(accountGap.tone) }}>
                        {accountGap.badge}
                      </span>
                    </div>
                    {"href" in accountGap && accountGap.href ? (
                      <Link href={accountGap.href} className="shrink-0 text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">
                        {accountGap.action}
                      </Link>
                    ) : null}
                  </div>
                  <div className="mt-1 text-[12px] font-medium text-[var(--text-primary)]">{accountGap.title}</div>
                  <div className="mt-1 text-[11px] leading-4 text-[var(--text-secondary)]">{accountGap.detail}</div>
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
      {showCta ? (
        <Link
          href={recoveryHref}
          className="focus-ring inline-flex shrink-0 items-center justify-center rounded-md border border-[var(--border-strong)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] font-medium text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]"
        >
          去恢复 · {trust.next_step_label || "刷新数据"}
        </Link>
      ) : null}
    </section>
  );
}
