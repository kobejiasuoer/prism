"use client";

import { AlertCircle, FileDown, RefreshCw } from "lucide-react";
import { useRuns, useRefreshStatus, useTodayData } from "@/lib/hooks";

import {
  CommandHeader,
  JudgementChain,
  ActionLanes,
  MiddayVerify,
  TrustFold,
} from "@/components/command-brief";
import { TrustBanner } from "@/components/trust-banner";

export default function CommandCenterPage() {
  const today = useTodayData();
  const runsQuery = useRuns();
  const refreshStatus = useRefreshStatus("today", true, { auto: true });
  const data = today.data;
  const brief = data?.command_brief;
  const trust = data?.readiness?.trust_level;
  const tradeDate = brief?.trade_date || data?.expected_trade_date || data?.trade_date || "-";

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

        {trust ? <TrustBanner trust={trust} className="mb-4" /> : null}

        {today.isError ? (
          <div className="war-error">
            <AlertCircle size={17} className="mt-0.5 shrink-0 text-[var(--warning)]" />
            <div className="min-w-0 flex-1">
              <div className="font-medium text-[var(--text-primary)]">后端数据暂不可用</div>
              <div className="mt-1">命令台骨架已加载，FastAPI 启动后会自动重新获取 `/api/today`。</div>
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
          </>
        ) : (
          <div className="war-error">
            <AlertCircle size={17} className="mt-0.5 shrink-0 text-[var(--warning)]" />
            <div className="min-w-0 flex-1">
              <div className="font-medium text-[var(--text-primary)]">命令台数据未到位</div>
              <div className="mt-1">后端尚未返回 `command_brief`；先到 Settings 跑安全刷新。</div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
