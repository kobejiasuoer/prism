"use client";

import Link from "next/link";
import { ArrowRight, ClipboardCheck, Pencil, RefreshCw } from "lucide-react";

import { Badge } from "@/components/badge";
import {
  EmptyState,
  ErrorState,
  Panel,
  SkeletonBlock,
} from "@/components/data-card";
import type {
  HoldingReview,
  PortfolioAccountResponse,
  PortfolioHoldingReviewsResponse,
  Tone,
} from "@/lib/types";
import {
  formatMoney,
  formatPercent,
  numericValue,
  pnlTone,
  stockDetailHref,
  suggestedSellQty,
} from "./portfolio-utils";

function positionPlanSourceLabel(source: string | null | undefined): string {
  if (source === "auto_on_buy_fill") return "买入后自动生成";
  if (source === "auto_runtime_default") return "持仓自动生成";
  return "Prism 自动生成";
}

function formatLevel(value: unknown): string {
  const parsed = numericValue(value);
  return parsed === null ? "-" : `¥${parsed.toFixed(2)}`;
}

function formatRulePercent(value: unknown): string {
  const parsed = numericValue(value);
  return parsed === null ? "-" : `${parsed.toFixed(2)}%`;
}

function formatSignedRulePercent(value: unknown): string {
  const parsed = numericValue(value);
  if (parsed === null) return "-";
  return `${parsed > 0 ? "+" : ""}${parsed.toFixed(2)}%`;
}

function formatQty(value: unknown): string {
  const parsed = numericValue(value);
  return parsed === null ? "-" : `${Math.round(parsed)} 股`;
}

function planVersionLabel(data: PortfolioAccountResponse): string {
  const sessionLabel = data.readiness.session?.label || "今日";
  if (sessionLabel.includes("盘中")) return "盘中动态版";
  if (sessionLabel.includes("盘前")) return "盘前预案版";
  if (sessionLabel.includes("盘后")) return "盘后冻结版";
  return `${sessionLabel}剧本`;
}

function quoteVersionLabel(
  data: PortfolioAccountResponse,
  holdingData: PortfolioHoldingReviewsResponse | undefined,
  review: HoldingReview,
): string {
  const updatedAt =
    holdingData?.market_quotes?.updated_at ||
    data.market_quotes?.updated_at ||
    review.quote_timestamp ||
    holdingData?.holding_action_summary?.generated_at ||
    data.holding_action_summary?.generated_at ||
    holdingData?.generated_at ||
    data.generated_at;
  return updatedAt || "-";
}

function actionButtonLabel(action: string | undefined): string {
  if (action === "清仓") return "录入清仓";
  if (action === "止盈") return "录入止盈";
  if (action === "减仓") return "录入减仓";
  return "录入卖出";
}

function aiVerdictTone(verdict: string | null | undefined): Tone {
  if (verdict === "loosen") return "sell";
  if (verdict === "tighten") return "warning";
  return "positive";
}

function aiStrengthTone(strength: string | null | undefined): Tone {
  if (strength === "high") return "positive";
  if (strength === "low") return "stale";
  return "watch";
}

function aiAdjustmentTone(adjustment: string | null | undefined): Tone {
  if (adjustment === "loosen") return "sell";
  if (adjustment === "tighten") return "warning";
  return "info";
}

function aiSourceLabel(
  review: HoldingReview["holding_ai_review"] | undefined,
): string {
  if (!review) return "AI 归因";
  if (review.fallback_reason) return "规则回退";
  if (review.provider === "deepseek") return "DeepSeek";
  return review.provider || "AI 归因";
}

function aiActionLabel(
  review: HoldingReview["holding_ai_review"] | undefined,
): string {
  const text = String(review?.action_rewrite || "").trim();
  if (!text) return "未生成";
  return text;
}

function aiCounterEvidenceLabel(
  review: HoldingReview["holding_ai_review"] | undefined,
  action: string | undefined,
): string {
  const label = String(review?.counter_evidence_label || "").trim();
  if (label) return label;
  if (action === "hold") return "风险证据";
  if (action === "refresh_quote") return "待确认点";
  if (action === "profit_take") return "回吐风险";
  return "缓冲证据";
}

function HoldingPlanCard({
  data,
  holdingData,
  review,
  onRecordSell,
  onAmendIdentity,
}: {
  data: PortfolioAccountResponse;
  holdingData?: PortfolioHoldingReviewsResponse;
  review: HoldingReview;
  onRecordSell?: (review: HoldingReview) => void;
  onAmendIdentity?: (review: HoldingReview) => void;
}) {
  const decision = review.holding_decision;
  const levels = decision?.levels || {};
  const rules = decision?.rules || review.position_plan?.rules || {};
  const shouldOfferSellFill = [
    "clear_exit",
    "defense_reduce",
    "profit_take",
    "time_exit",
  ].includes(String(review.today_action || ""));
  const planSource = positionPlanSourceLabel(review.position_plan?.source);
  const version = planVersionLabel(data);
  const updatedAt = quoteVersionLabel(data, holdingData, review);
  const actionLabel = actionButtonLabel(decision?.suggested_action);
  const marketQuoteStatus =
    holdingData?.market_quotes?.status || data.market_quotes?.status;
  const eventEvidence =
    marketQuoteStatus === "ok"
      ? "行情证据已刷新"
      : marketQuoteStatus === "partial"
        ? "行情部分刷新"
        : "等待行情刷新";
  const triggerFacts = (decision?.trigger_facts || []).filter(Boolean);
  const basis = (decision?.script?.basis || []).filter(Boolean);
  const hardFlags = Array.isArray(decision?.evidence?.hard_flags)
    ? decision.evidence.hard_flags
    : [];
  const positives = Array.isArray(decision?.evidence?.positives)
    ? decision.evidence.positives
    : [];
  const actionQty = suggestedSellQty(review);
  const actionPct = numericValue(decision?.target_sell_pct);
  const profileLabel = decision?.script?.profile_label || "Prism 个股剧本";
  const profileDetail =
    decision?.script?.profile_detail ||
    "按持仓成本、当日观察链和价格线动态生成。";
  const aiReview = review.holding_ai_review;
  const aiSupport = (aiReview?.supporting_evidence || [])
    .filter(Boolean)
    .slice(0, 3);
  const aiOppose = (aiReview?.opposing_evidence || [])
    .filter(Boolean)
    .slice(0, 2);
  const aiWatchText = String(aiReview?.next_watch || "").replace(/；/g, "。");
  const aiRiskText = String(aiReview?.risk_summary || "").replace(/；/g, "。");
  const aiCounterLabel = aiCounterEvidenceLabel(
    aiReview,
    String(review.today_action || ""),
  );

  return (
    <article className="overflow-hidden rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
      <div className="grid divide-y divide-[var(--border-subtle)] xl:grid-cols-[minmax(190px,0.8fr)_minmax(0,1.7fr)_minmax(210px,0.75fr)] xl:divide-x xl:divide-y-0">
        <section className="min-w-0 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold text-[var(--text-primary)]">
              {review.name || "未命名标的"}
            </span>
            <span className="mono text-[11px] text-[var(--text-tertiary)]">
              {review.code}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge tone={review.action_tone}>{review.action_label}</Badge>
            <Badge tone="info">{profileLabel}</Badge>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-[12px]">
            <div>
              <div className="text-[11px] text-[var(--text-tertiary)]">
                持仓数量
              </div>
              <div className="mt-1 font-medium text-[var(--text-primary)]">
                {review.qty || 0} 股
              </div>
            </div>
            <div>
              <div className="text-[11px] text-[var(--text-tertiary)]">
                浮盈亏
              </div>
              <div
                className={`mt-1 font-medium ${pnlTone(review.unrealized_pnl)}`}
              >
                {formatMoney(review.unrealized_pnl)}
              </div>
              <div
                className={`text-[11px] ${pnlTone(review.unrealized_pnl_pct)}`}
              >
                {formatPercent(review.unrealized_pnl_pct)}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-[var(--text-tertiary)]">
                当前价
              </div>
              <div className="mt-1 font-medium text-[var(--text-primary)]">
                {formatMoney(review.current_price)}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-[var(--text-tertiary)]">
                成本线
              </div>
              <div className="mt-1 font-medium text-[var(--text-secondary)]">
                {formatMoney(review.avg_cost)}
              </div>
            </div>
          </div>
        </section>

        <section className="min-w-0 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={review.action_tone}>今日动作协议</Badge>
            <span className="text-sm font-semibold text-[var(--text-primary)]">
              {decision?.category || review.review_reason}｜
              {decision?.suggested_action || "-"}
            </span>
          </div>
          <p className="mt-2 text-[14px] font-medium leading-6 text-[var(--text-primary)]">
            {decision?.execution_rule || "刷新行情后生成持仓动作。"}
          </p>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-[var(--text-secondary)]">
            <span>目标卖出：{actionQty ? formatQty(actionQty) : "-"}</span>
            <span>比例：{actionPct ? `${actionPct.toFixed(0)}%` : "-"}</span>
            <span>剧本：{version}</span>
            <span>更新：{updatedAt}</span>
          </div>
        </section>

        <section className="flex min-w-0 flex-col justify-between gap-3 p-4 text-[12px]">
          <div className="grid grid-cols-2 gap-x-5 gap-y-2 xl:grid-cols-1">
            <div>
              <div className="text-[11px] text-[var(--text-tertiary)]">
                防守线
              </div>
              <div className="mt-1 font-semibold text-[var(--tone-sell)]">
                {formatLevel(levels.defense_reduce_price)}（
                {formatRulePercent(rules.defense_reduce_loss_pct)}）
              </div>
            </div>
            <div>
              <div className="text-[11px] text-[var(--text-tertiary)]">
                清仓线
              </div>
              <div className="mt-1 font-semibold text-[var(--tone-risk)]">
                {formatLevel(levels.clear_exit_price)}（
                {formatRulePercent(rules.clear_loss_pct)}）
              </div>
            </div>
            <div>
              <div className="text-[11px] text-[var(--text-tertiary)]">
                修复线
              </div>
              <div className="mt-1 font-medium text-[var(--text-primary)]">
                {formatLevel(levels.repair_price || levels.reclaim_price)}
              </div>
            </div>
            <div>
              <div className="text-[11px] text-[var(--text-tertiary)]">
                止盈线
              </div>
              <div className="mt-1 font-medium text-[var(--tone-positive)]">
                {formatLevel(levels.profit_take_price)}（
                {formatSignedRulePercent(rules.profit_take_pct)}）
              </div>
            </div>
          </div>
          <div className="flex flex-wrap justify-end gap-2 xl:justify-start">
            {shouldOfferSellFill ? (
              <button
                type="button"
                onClick={() => onRecordSell?.(review)}
                className="focus-ring inline-flex h-9 items-center rounded-md border border-[var(--tone-sell)] bg-[color-mix(in_srgb,var(--tone-sell)_8%,transparent)] px-3 text-[12px] text-[var(--tone-sell)]"
              >
                {actionLabel}
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => onAmendIdentity?.(review)}
              className="focus-ring inline-flex h-9 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-3 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              <Pencil size={13} />
              更正
            </button>
            <Link
              href={stockDetailHref(review.code)}
              className="focus-ring inline-flex h-9 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-3 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              详情
              <ArrowRight size={13} />
            </Link>
          </div>
        </section>
      </div>

      <div className="grid border-t border-[var(--border-subtle)] divide-y divide-[var(--border-subtle)] lg:grid-cols-2 lg:divide-x lg:divide-y-0 xl:grid-cols-4">
        <section className="p-4">
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
            Prism 个股剧本
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge tone="info">{profileLabel}</Badge>
            <Badge
              tone={
                review.position_plan?.source === "auto_on_buy_fill"
                  ? "positive"
                  : "watch"
              }
            >
              {planSource}
            </Badge>
          </div>
          <p className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
            {profileDetail}
          </p>
          <div className="mt-3 grid gap-1 text-[12px] leading-5 text-[var(--text-secondary)]">
            <div>时间窗口：{rules.max_hold_days || "-"} 天</div>
            {levels.structure_support_price ? (
              <div>结构支撑：{formatLevel(levels.structure_support_price)}</div>
            ) : null}
            <div>行情状态：{eventEvidence}</div>
          </div>
        </section>

        <section className="p-4">
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
            触发事实
          </div>
          <ul className="mt-2 grid gap-1.5 text-[12px] leading-5 text-[var(--text-secondary)]">
            {(triggerFacts.length
              ? triggerFacts
              : [decision?.trigger_rule || review.action_instruction]
            )
              .slice(0, 6)
              .map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-[var(--accent)]" />
                  <span>{item}</span>
                </li>
              ))}
          </ul>
          {hardFlags.length || positives.length ? (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {hardFlags.slice(0, 3).map((item) => (
                <Badge key={`hard-${item}`} tone="risk">
                  {item}
                </Badge>
              ))}
              {positives.slice(0, 2).map((item) => (
                <Badge key={`pos-${item}`} tone="positive">
                  {item}
                </Badge>
              ))}
            </div>
          ) : null}
        </section>

        <section className="p-4">
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
            AI 证据归因
          </div>
          {aiReview ? (
            <>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Badge tone={aiVerdictTone(aiReview.verdict)}>
                  {aiReview.verdict_label || "维持原剧本"}
                </Badge>
                <Badge tone={aiStrengthTone(aiReview.evidence_strength)}>
                  {aiReview.scene_label || "场景归因"}
                </Badge>
                <Badge tone={aiReview.fallback_reason ? "warning" : "info"}>
                  {aiSourceLabel(aiReview)}
                </Badge>
              </div>
              <p className="mt-2 text-[12px] leading-5 text-[var(--text-primary)] break-words">
                {aiActionLabel(aiReview)}
              </p>
              <div className="mt-3 grid gap-1.5 text-[12px] leading-5 text-[var(--text-secondary)]">
                <div>
                  <span className="text-[var(--text-tertiary)]">
                    下一条线：
                  </span>
                  {aiWatchText || "-"}
                </div>
                <div>
                  <span className="text-[var(--text-tertiary)]">
                    风险判断：
                  </span>
                  {aiRiskText || "-"}
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[var(--text-tertiary)]">调整：</span>
                  <Badge
                    tone={aiAdjustmentTone(
                      aiReview.script_adjustment?.adjustment,
                    )}
                  >
                    {aiReview.script_adjustment?.adjustment_label || "保持"}
                  </Badge>
                  <span className="text-[var(--text-tertiary)]">
                    置信度{" "}
                    {aiReview.confidence !== null &&
                    aiReview.confidence !== undefined
                      ? `${Math.round(aiReview.confidence * 100)}%`
                      : "-"}
                  </span>
                </div>
              </div>
              {aiSupport.length ? (
                <div className="mt-3">
                  <div className="text-[11px] text-[var(--text-tertiary)]">
                    支持证据
                  </div>
                  <ul className="mt-1 grid gap-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                    {aiSupport.map((item) => (
                      <li key={item} className="flex gap-2">
                        <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-[var(--tone-positive)]" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {aiOppose.length ? (
                <div className="mt-3">
                  <div className="text-[11px] text-[var(--text-tertiary)]">
                    {aiCounterLabel}
                  </div>
                  <ul className="mt-1 grid gap-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                    {aiOppose.map((item) => (
                      <li key={item} className="flex gap-2">
                        <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-[var(--tone-risk)]" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : (
            <div className="mt-2 text-[12px] leading-5 text-[var(--text-secondary)]">
              AI 归因尚未生成，先按规则动作处理。
            </div>
          )}
        </section>

        <section className="p-4">
          <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
            升级 / 撤销
          </div>
          <div className="mt-2 grid gap-1.5 text-[12px] leading-5 text-[var(--text-secondary)]">
            <div>
              <span className="text-[var(--text-tertiary)]">触发：</span>
              {decision?.trigger_rule || "-"}
            </div>
            <div>
              <span className="text-[var(--text-tertiary)]">升级：</span>
              {decision?.upgrade_rule || "-"}
            </div>
            <div>
              <span className="text-[var(--text-tertiary)]">撤销：</span>
              {decision?.revoke_rule || "-"}
            </div>
          </div>
          {basis.length ? (
            <div className="mt-3 text-[11px] leading-5 text-[var(--text-tertiary)]">
              {basis.slice(0, 2).join("；")}
            </div>
          ) : null}
        </section>
      </div>
    </article>
  );
}

export function PortfolioHoldingWorkbench({
  data,
  holdingData,
  isLoading,
  isError,
  onRetry,
  onRefreshQuotes,
  isRefreshingQuotes,
  onRecordSell,
  onAmendIdentity,
}: {
  data: PortfolioAccountResponse;
  holdingData?: PortfolioHoldingReviewsResponse;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  onRefreshQuotes?: () => void;
  isRefreshingQuotes?: boolean;
  onRecordSell?: (review: HoldingReview) => void;
  onAmendIdentity?: (review: HoldingReview) => void;
}) {
  const reviews = holdingData?.holding_reviews || data.holding_reviews || [];
  const summary =
    holdingData?.holding_action_summary || data.holding_action_summary;
  const positionCount =
    holdingData?.position_count ?? data.account.open_positions.length;
  const mustReview =
    summary?.must_review ?? reviews.filter((item) => item.must_review).length;
  const title =
    summary?.title ||
    (positionCount ? `${mustReview} 只持仓需要动作` : "暂无真实持仓");
  const reviewsPending = Boolean(positionCount && !holdingData && isLoading);

  const metrics = [
    {
      label: "清仓退出",
      value: summary?.clear_exit ?? 0,
      tone: (summary?.clear_exit ?? 0) ? "sell" : "info",
      detail: "止损退出",
    },
    {
      label: "防守减仓",
      value: summary?.defense_reduce ?? 0,
      tone: (summary?.defense_reduce ?? 0) ? "sell" : "info",
      detail: "减仓动作",
    },
    {
      label: "止盈兑现",
      value: summary?.profit_take ?? 0,
      tone: (summary?.profit_take ?? 0) ? "positive" : "info",
      detail: "利润兑现",
    },
    {
      label: "时间失败",
      value: summary?.time_exit ?? 0,
      tone: (summary?.time_exit ?? 0) ? "warning" : "info",
      detail: "机会窗口",
    },
    {
      label: "亏损预警",
      value: summary?.loss_warning ?? 0,
      tone: (summary?.loss_warning ?? 0) ? "warning" : "positive",
      detail: "不加仓",
    },
    {
      label: "继续持有",
      value: summary?.hold ?? 0,
      tone: "positive",
      detail: "剧本内",
    },
  ];

  return (
    <Panel
      title="今日持仓动作"
      eyebrow="Holding script desk"
      className="surface-card p-4"
      action={
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
          <Badge tone={summary?.tone || (mustReview ? "warning" : "positive")}>
            {title}
          </Badge>
          <button
            type="button"
            onClick={onRefreshQuotes}
            disabled={!onRefreshQuotes || isRefreshingQuotes}
            className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[11px] text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw
              size={12}
              className={isRefreshingQuotes ? "animate-spin" : ""}
            />
            刷新行情
          </button>
        </div>
      }
    >
      <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
        <div className="flex items-start gap-2">
          <ClipboardCheck
            size={16}
            className="mt-0.5 shrink-0 text-[var(--accent)]"
          />
          <div className="min-w-0">
            <div className="text-sm font-semibold text-[var(--text-primary)]">
              {title}
            </div>
            <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              这里只读取真实账户持仓，按个股画像、当日观察链和价格线生成今天的持仓剧本；研究自选股不会被当作持仓，也不会自动交易。
            </div>
          </div>
        </div>
      </div>

      <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        {metrics.map((item) => (
          <div
            key={item.label}
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2"
          >
            <div className="truncate text-[11px] text-[var(--text-tertiary)]">
              {item.label}
            </div>
            <div className="mt-1 flex items-baseline justify-between gap-2">
              <span className="text-lg font-semibold text-[var(--text-primary)]">
                {item.value}
              </span>
              <Badge tone={item.tone}>{item.detail}</Badge>
            </div>
          </div>
        ))}
      </div>

      {isError ? (
        <ErrorState message="持仓动作暂不可用" onRetry={onRetry} />
      ) : reviewsPending ? (
        <div className="grid gap-3">
          <SkeletonBlock className="h-44 w-full" />
          <SkeletonBlock className="h-44 w-full" />
        </div>
      ) : !positionCount ? (
        <EmptyState>
          当前没有真实持仓。买入成交写入账本后，这里会自动生成 Prism
          个股持仓剧本和后续动作。
        </EmptyState>
      ) : !reviews.length ? (
        <EmptyState>
          持仓动作摘要尚未生成。刷新账本后，会按真实持仓生成 Prism
          个股持仓剧本。
        </EmptyState>
      ) : (
        <div className="grid gap-3">
          {reviews.map((review) => (
            <HoldingPlanCard
              key={review.code}
              data={data}
              holdingData={holdingData}
              review={review}
              onRecordSell={onRecordSell}
              onAmendIdentity={onAmendIdentity}
            />
          ))}
        </div>
      )}
    </Panel>
  );
}
