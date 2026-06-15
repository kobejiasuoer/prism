"use client";

import { Database, LoaderCircle } from "lucide-react";

import { Badge } from "@/components/badge";
import { Panel } from "@/components/data-card";
import { MetricCard } from "@/components/metric-card";
import { riskLevelTone } from "@/lib/risk-utils";
import type { StockFormalData } from "@/lib/types";
import { displayText, hasDisplayValue } from "./stock-display-utils";

export type FormalSectionKey = "profile" | "risk" | "sources";

function riskLevelLabel(level?: string) {
  if (level === "block") {
    return "硬执行约束";
  }
  if (level === "degrade") {
    return "候选降级";
  }
  if (level === "warn") {
    return "风险提醒";
  }
  return "只展示";
}

function recordField(row: Record<string, unknown> | undefined, keys: string[], fallback = "-") {
  if (!row) {
    return fallback;
  }
  for (const key of keys) {
    const value = row[key];
    if (hasDisplayValue(value)) {
      return String(value);
    }
  }
  return fallback;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function asRecordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object" && !Array.isArray(item))) : [];
}

function tagList(values?: string[], limit = 8) {
  return (values || []).filter(Boolean).slice(0, limit);
}

function usageLabel(value: unknown) {
  switch (String(value || "")) {
    case "hard_gate":
      return "硬闸门";
    case "ranking_signal":
      return "排序因子";
    case "risk_penalty":
      return "风险提示";
    case "research_only":
      return "研究口径";
    case "display_only":
      return "只读展示";
    case "evidence_only":
      return "只读证据";
    default:
      return displayText(value, "只读证据");
  }
}

export function FormalDataSnapshotPanel({ data }: { data?: StockFormalData }) {
  if (!data?.available) {
    return null;
  }
  const cards = data.metric_cards || [];
  const indexRows = data.index_memberships || [];
  const topRows = data.top_list || [];
  const topInstRows = data.top_inst || [];
  const holderRows = data.shareholders || [];
  const dividendRows = data.dividends || [];
  const profile = asRecord(data.profile);
  const nameChanges = asRecordArray(profile.name_changes);
  const themes = data.themes || {};
  const businessRows = asRecordArray(data.business_breakdown?.top_items);
  const businessByType = asRecord(data.business_breakdown?.by_type);
  const eventRisks = asRecord(data.event_risks);
  const pledge = asRecord(eventRisks.pledge);
  const shareFloat = asRecord(eventRisks.share_float);
  const repurchase = asRecord(eventRisks.repurchase);
  const audit = asRecord(eventRisks.audit);
  const research = asRecord(eventRisks.research);
  const marketActivity = asRecord(data.market_activity);
  const blockTrade = asRecord(marketActivity.block_trade);
  const margin = asRecord(marketActivity.margin);
  const capital = asRecord(data.capital_flow);
  const technical = asRecord(data.technical_chips);
  const cyqChips = asRecord(technical.cyq_chips);
  const sourceCards = (data.source_cards || []).filter((card) => card.available);
  const factorRiskItems = data.factor_profile?.risk_items || [];
  const factorRiskRefs = data.factor_profile?.risk_evidence_refs || [];
  const section = data.section;
  const showFull = !section || section === "full";
  const showProfile = showFull || section === "profile";
  const showRisk = showFull || section === "risk";
  const showSources = showFull || section === "sources";
  const businessTypeRows = ["产品", "地区", "行业"].map((label) => {
    const rows = asRecordArray(businessByType[label]);
    return { label, item: rows[0] };
  }).filter((item) => item.item);

  const title = section === "profile" ? "公司画像" : section === "risk" ? "风险摘要" : section === "sources" ? "来源索引" : "Tushare 档案";
  const eyebrow = section === "profile" || section === "risk" || section === "sources" ? "Formal Section" : "Formal Data";

  return (
    <Panel
      title={title}
      eyebrow={eyebrow}
      action={
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="positive">{data.provider || "tushare/tinyshare"}</Badge>
          {data.stale ? <Badge tone="warning">只读旧证据</Badge> : null}
          {data.stale && data.requested_trade_date ? <Badge tone="warning">请求日 {data.requested_trade_date}</Badge> : null}
          {data.trade_date ? <Badge tone="info">交易日 {data.trade_date}</Badge> : null}
        </div>
      }
    >
      <div className="surface-card p-4">
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
            <Database size={17} className="text-[var(--positive)]" />
          </div>
          <div>
            <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">{data.headline || "Tushare 数据已接入个股档案"}</h2>
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              {data.summary || "估值、资金流、财务、股东、分红和指数权重以只读研究证据展示。"}
            </p>
          </div>
        </div>

        {cards.length ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {cards.slice(0, 8).map((card, index) => (
              <MetricCard key={`${card.label}-${index}`} {...card} tone={card.tone || (index < 2 ? "info" : "watch")} />
            ))}
          </div>
        ) : null}

        {showFull && data.factor_profile && (
          <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] uppercase text-[var(--text-tertiary)]">Tushare 因子评分</span>
              <div className="flex flex-wrap justify-end gap-1.5">
                <Badge tone={typeof data.factor_profile.tushare_score === "number" ? "positive" : "stale"}>
                  {typeof data.factor_profile.tushare_score === "number"
                    ? `${Math.round(data.factor_profile.tushare_score)} 分`
                    : "数据缺失/不可用"}
                </Badge>
                <Badge tone={riskLevelTone(data.factor_profile.risk_level)}>
                  {riskLevelLabel(data.factor_profile.risk_level)}
                </Badge>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {(data.factor_profile.factor_tags ?? []).map((t) => <Badge key={t} tone="info">{t}</Badge>)}
              {(data.factor_profile.risk_flags ?? []).map((t) => <Badge key={t} tone="risk">{t}</Badge>)}
            </div>
            {(data.factor_profile.block_reason || data.factor_profile.degrade_reason) && (
              <div className="mt-2 rounded-md border border-[color-mix(in_srgb,var(--negative)_24%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                {data.factor_profile.block_reason || data.factor_profile.degrade_reason}
              </div>
            )}
            {data.factor_profile.explanation?.entry_reason && (
              <p className="mt-2 text-[13px] text-[var(--text-primary)]">{data.factor_profile.explanation.entry_reason}</p>
            )}
            {factorRiskItems.length ? (
              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {factorRiskItems.slice(0, 4).map((item, index) => (
                  <div key={`${item.code || item.label || "risk"}-${index}`} className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
                    <div className="mb-1 flex items-center justify-between gap-2">
                      <span className="text-[11px] text-[var(--text-tertiary)]">{item.dataset_label || item.dataset || "风险证据"}</span>
                      <Badge tone={riskLevelTone(item.level)}>{riskLevelLabel(item.level)}</Badge>
                    </div>
                    <div className="text-[13px] font-medium text-[var(--text-primary)]">{item.label || "风险提示"}</div>
                    <div className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">{item.reason || "-"}</div>
                  </div>
                ))}
              </div>
            ) : null}
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {([
                ["基本面", data.factor_profile.explanation?.evidence?.fundamental],
                ["资金面", data.factor_profile.explanation?.evidence?.capital],
                ["交易异动", data.factor_profile.explanation?.evidence?.trading_anomaly],
                ["指数权重", data.factor_profile.explanation?.evidence?.index_weight],
                ["主题行业", data.factor_profile.explanation?.evidence?.theme],
                ["事件风险", data.factor_profile.explanation?.evidence?.event_risk],
                ["两融", data.factor_profile.explanation?.evidence?.margin],
                ["筹码", data.factor_profile.explanation?.evidence?.chips],
                ["执行约束", data.factor_profile.explanation?.evidence?.execution],
              ] as const).map(([label, block]) => (
                <div key={label} className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
                  <div className="text-[11px] text-[var(--text-tertiary)]">{label}</div>
                  <div className="text-[13px] text-[var(--text-primary)]">
                    {block?.available ? block?.interpretation : "数据缺失/不可用"}
                  </div>
                </div>
              ))}
            </div>
            {factorRiskRefs.length ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {factorRiskRefs.slice(0, 6).map((ref, index) => (
                  <Badge key={`${ref.dataset || ref.label}-${index}`} tone={ref.hard_block ? "risk" : "info"}>
                    {ref.label || ref.dataset || "风险证据"} · {riskLevelLabel(ref.level)}
                  </Badge>
                ))}
              </div>
            ) : null}
          </div>
        )}

        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
          {showProfile ? <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">公司画像</span>
              <Badge tone={profile.name ? "positive" : "warning"}>{displayText(profile.industry, "行业缺失")}</Badge>
            </div>
            <div className="grid gap-1.5 text-[12px] leading-5 text-[var(--text-secondary)]">
              <div>{displayText(profile.full_name || profile.name, data.code)}</div>
              <div>主营：{displayText(profile.main_business, "暂无主营描述")}</div>
              <div>地区：{displayText(profile.province || profile.area, "-")} {displayText(profile.city, "")}</div>
              <div>上市：{displayText(profile.list_date, "-")} · {displayText(profile.market || profile.exchange, "-")}</div>
              <div>历史名称：{nameChanges.length ? nameChanges.slice(0, 3).map((row) => recordField(row, ["name", "ann_name", "change_reason"])).join(" / ") : "暂无更名记录"}</div>
            </div>
          </div> : null}

          {showProfile ? <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">主题 / 行业</span>
              <Badge tone={(themes.concepts?.length || themes.industries?.length) ? "info" : "warning"}>
                {(themes.concepts?.length || 0) + (themes.industries?.length || 0)} 个标签
              </Badge>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {tagList(themes.concepts, 6).map((item) => <Badge key={`concept-${item}`} tone="info">{item}</Badge>)}
              {tagList(themes.industries, 4).map((item) => <Badge key={`industry-${item}`} tone="positive">{item}</Badge>)}
              {tagList(themes.ths, 3).map((item) => <Badge key={`ths-${item}`} tone="watch">{item}</Badge>)}
              {tagList(themes.dc, 3).map((item) => <Badge key={`dc-${item}`} tone="watch">{item}</Badge>)}
              {!(themes.concepts?.length || themes.industries?.length || themes.ths?.length || themes.dc?.length) ? (
                <span className="text-[12px] text-[var(--text-tertiary)]">暂无主题/行业归属命中。</span>
              ) : null}
            </div>
          </div> : null}

          {showProfile ? <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">主营构成</span>
              <Badge tone={businessRows.length ? "info" : "warning"}>{displayText(data.business_breakdown?.concentration_label, `${businessRows.length} 条`)}</Badge>
            </div>
            <div className="grid gap-1.5">
              {businessTypeRows.length ? (
                <div className="mb-1 flex flex-wrap gap-1.5">
                  {businessTypeRows.map((item) => (
                    <Badge key={item.label} tone="info">{item.label}：{recordField(item.item, ["item", "bz_item", "name"])}</Badge>
                  ))}
                </div>
              ) : null}
              {businessRows.slice(0, 4).map((row, index) => (
                <div key={`${recordField(row, ["item"])}-${index}`} className="flex items-center justify-between gap-3 text-[12px]">
                  <span className="line-clamp-1 text-[var(--text-secondary)]">{recordField(row, ["item", "bz_item", "name"])}</span>
                  <span className="shrink-0 text-[var(--text-primary)]">{recordField(row, ["sales", "bz_sales", "revenue"])}</span>
                </div>
              ))}
              {!businessRows.length ? <span className="text-[12px] text-[var(--text-tertiary)]">暂无主营构成命中。</span> : null}
            </div>
          </div> : null}

          {showRisk ? <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">事件风险</span>
              <Badge tone={audit.abnormal ? "risk" : "info"}>{audit.abnormal ? "审计异常" : "证据摘要"}</Badge>
            </div>
            <div className="grid gap-1.5 text-[12px] leading-5 text-[var(--text-secondary)]">
              <div>质押：{displayText(pledge.pledge_ratio, "-")}% · 解禁市值 {displayText(shareFloat.total_float_mv, "-")}</div>
              <div>回购：{displayText(repurchase.total_amount, "-")} · 研报目标均值 {displayText(research.average_target_price, "-")}</div>
              <div>审计：{displayText(audit.opinion, "暂无异常意见")}</div>
            </div>
          </div> : null}

          {showRisk ? <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">资金 / 两融 / 龙虎榜</span>
              <Badge tone={topRows.length || blockTrade.count ? "watch" : "info"}>{topRows.length} 次龙虎榜</Badge>
            </div>
            <div className="grid gap-1.5 text-[12px] leading-5 text-[var(--text-secondary)]">
              <div>主力净流入：{displayText(capital.main_net_yi, "-")} 亿 · 净占比 {displayText(capital.main_net_pct, "-")}%</div>
              <div>大宗：{displayText(blockTrade.count, "0")} 次 · 平均折溢价 {displayText(blockTrade.average_discount_pct, "-")}%</div>
              <div>两融：余额变化 {displayText(margin.balance_change, "-")} · 标的 {margin.is_margin_target ? "是" : "否"}</div>
              <div>机构席位：{topInstRows.length ? `${topInstRows.length} 条命中` : "近窗口未命中"}</div>
            </div>
          </div> : null}

          {showRisk ? <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">技术筹码</span>
              <Badge tone={cyqChips.winner_rate ? "watch" : "info"}>{displayText(cyqChips.winner_rate, "筹码缺失")}</Badge>
            </div>
            <div className="grid gap-1.5 text-[12px] leading-5 text-[var(--text-secondary)]">
              <div>MACD：{displayText(asRecord(technical.technical_factor).macd, "-")} · 收盘 {displayText(asRecord(technical.technical_factor).close, "-")}</div>
              <div>获利盘：{displayText(cyqChips.winner_rate, "-")} · 成本压力 {displayText(cyqChips.cost_pressure, "-")}</div>
              <div>筹码价格带：{displayText(cyqChips.price_low, "-")} - {displayText(cyqChips.price_high, "-")}</div>
            </div>
          </div> : null}
        </div>

        {showSources && sourceCards.length ? (
          <div className="mt-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">数据用途</span>
              <Badge tone="info">个股档案只读</Badge>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
              {sourceCards.slice(0, 8).map((card) => (
                <div key={`${card.dataset || card.label}-${card.value}`} className="rounded-md border border-[var(--border-subtle)] px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12px] font-medium text-[var(--text-primary)]">{card.label}</span>
                    <Badge tone={card.live_permission === "research_only" ? "watch" : "info"}>{usageLabel(card.stock_profile_use || card.live_permission)}</Badge>
                  </div>
                  <div className="mt-1 text-[11px] leading-4 text-[var(--text-tertiary)]">
                    {card.dataset || "-"} · {usageLabel(card.decision_use)} · {card.value}
                    {card.stale ? " · 旧证据" : ""}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {showFull ? <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">指数权重</span>
              <Badge tone={indexRows.length ? "positive" : "info"}>{indexRows.length} 个指数</Badge>
            </div>
            <div className="grid gap-1.5">
              {indexRows.slice(0, 4).map((row, index) => (
                <div key={`${recordField(row, ["index_code"])}-${index}`} className="flex items-center justify-between gap-2 text-[12px]">
                  <span className="mono text-[var(--text-secondary)]">{recordField(row, ["index_code"])}</span>
                  <span className="text-[var(--text-primary)]">{recordField(row, ["weight"])}%</span>
                </div>
              ))}
              {!indexRows.length ? <span className="text-[12px] text-[var(--text-tertiary)]">未命中已补采指数。</span> : null}
            </div>
          </div>

          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">龙虎榜</span>
              <Badge tone={topRows.length ? "watch" : "info"}>{topRows.length} 次</Badge>
            </div>
            <div className="grid gap-1.5">
              {topRows.slice(0, 3).map((row, index) => (
                <div key={`${recordField(row, ["trade_date"])}-${index}`} className="text-[12px] leading-5 text-[var(--text-secondary)]">
                  {recordField(row, ["trade_date"])} · 涨跌 {recordField(row, ["pct_change"])} · 净买 {recordField(row, ["net_amount", "net_buy"])}
                </div>
              ))}
              {!topRows.length ? <span className="text-[12px] text-[var(--text-tertiary)]">近窗口没有龙虎榜命中。</span> : null}
            </div>
          </div>

          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">前十大股东</span>
              <Badge tone={holderRows.length ? "info" : "warning"}>{holderRows.length} 条</Badge>
            </div>
            <div className="grid gap-1.5">
              {holderRows.slice(0, 4).map((row, index) => (
                <div key={`${recordField(row, ["holder_name"])}-${index}`} className="flex items-start justify-between gap-2 text-[12px]">
                  <span className="line-clamp-1 text-[var(--text-secondary)]">{recordField(row, ["holder_name"])}</span>
                  <span className="shrink-0 text-[var(--text-primary)]">{recordField(row, ["hold_ratio"])}%</span>
                </div>
              ))}
              {!holderRows.length ? <span className="text-[12px] text-[var(--text-tertiary)]">暂无股东结构命中。</span> : null}
            </div>
          </div>

          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">分红送配</span>
              <Badge tone={dividendRows.length ? "info" : "warning"}>{dividendRows.length} 条</Badge>
            </div>
            <div className="grid gap-1.5">
              {dividendRows.slice(0, 3).map((row, index) => (
                <div key={`${recordField(row, ["end_date", "ann_date"])}-${index}`} className="text-[12px] leading-5 text-[var(--text-secondary)]">
                  {recordField(row, ["end_date", "ann_date"])} · 派息 {recordField(row, ["cash_div_tax", "cash_div"])} · 进度 {recordField(row, ["div_proc"])}
                </div>
              ))}
              {!dividendRows.length ? <span className="text-[12px] text-[var(--text-tertiary)]">暂无分红记录命中。</span> : null}
            </div>
          </div>
        </div> : null}
      </div>
    </Panel>
  );
}

export function FormalDataSummaryPanel({
  data,
  loadingFull,
  fullLoaded,
  sectionStates,
  onLoadSection,
  onLoadFull,
}: {
  data?: StockFormalData;
  loadingFull?: boolean;
  fullLoaded?: boolean;
  sectionStates?: Record<FormalSectionKey, { loaded?: boolean; loading?: boolean; available?: boolean }>;
  onLoadSection?: (section: FormalSectionKey) => void;
  onLoadFull?: () => void;
}) {
  if (!data?.available) {
    return null;
  }
  const cards = data.metric_cards || [];
  const sourceCards = (data.source_cards || []).filter((card) => card.available);
  const coverage = data.coverage || {};
  const quickSections: Array<{ key: FormalSectionKey; label: string; detail: string }> = [
    { key: "profile", label: "公司画像", detail: "主题、行业、主营" },
    { key: "risk", label: "风险摘要", detail: "事件、两融、筹码索引" },
    { key: "sources", label: "来源索引", detail: "覆盖与权限" },
  ];

  return (
    <Panel
      title="正式数据轻量摘要"
      eyebrow="Formal Summary"
      action={
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="info">{data.provider || "tushare/tinyshare"}</Badge>
          {data.summary_only ? <Badge tone="watch">轻量首屏</Badge> : null}
          {data.stale ? <Badge tone="warning">只读旧证据</Badge> : null}
          {fullLoaded ? <Badge tone="positive">完整档案已加载</Badge> : null}
          {loadingFull ? <Badge tone="info">完整档案加载中</Badge> : null}
          {!fullLoaded && onLoadFull ? (
            <button
              type="button"
              className="focus-ring inline-flex h-7 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2 text-[11px] text-[var(--text-primary)]"
              onClick={onLoadFull}
              disabled={loadingFull}
            >
              {loadingFull ? <LoaderCircle size={12} className="animate-spin" /> : <Database size={12} />}
              完整档案
            </button>
          ) : null}
        </div>
      }
    >
      <div className="surface-card p-4">
        <div className="mb-4 flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
            <Database size={17} className="text-[var(--info)]" />
          </div>
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-[var(--text-primary)]">{data.headline || "正式数据摘要已就绪"}</h2>
            <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
              {data.summary || "先展示可快速读取的估值、资金、财务和来源索引；完整证据按需展开。"}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-6">
          {cards.slice(0, 6).map((card, index) => (
            <MetricCard key={`${card.label}-${index}`} {...card} tone={card.tone || "info"} />
          ))}
        </div>

        <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[12px] font-medium text-[var(--text-primary)]">来源索引</span>
              <Badge tone="info">{sourceCards.length} 个可用</Badge>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {sourceCards.slice(0, 10).map((card) => (
                <Badge key={`${card.dataset || card.label}-${card.value}`} tone={card.stock_profile_use === "coverage_hint" ? "watch" : "info"}>
                  {card.label}
                </Badge>
              ))}
            </div>
          </div>

          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-[12px] leading-5 text-[var(--text-secondary)]">
            <div className="font-medium text-[var(--text-primary)]">执行权限</div>
            <div className="mt-1">只读证据，不提升真钱 readiness。</div>
            <div className="mt-1 text-[var(--text-tertiary)]">
              个股直连 {coverage.stock_scoped_available ?? "-"} / {coverage.stock_scoped_total ?? "-"} · 数据集索引 {coverage.catalog_available ?? "-"} / {coverage.catalog_total ?? "-"}
            </div>
          </div>
        </div>

        {onLoadSection ? (
          <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-3">
            {quickSections.map((item) => {
              const state = sectionStates?.[item.key] || {};
              return (
                <button
                  key={item.key}
                  type="button"
                  className="focus-ring flex min-h-[76px] items-start justify-between gap-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-left hover:border-[var(--border-strong)] disabled:cursor-not-allowed disabled:opacity-60"
                  onClick={() => onLoadSection(item.key)}
                  disabled={state.loading}
                >
                  <span>
                    <span className="block text-[12px] font-medium text-[var(--text-primary)]">{item.label}</span>
                    <span className="mt-1 block text-[11px] leading-4 text-[var(--text-tertiary)]">{item.detail}</span>
                  </span>
                  {state.loading ? (
                    <LoaderCircle size={14} className="mt-0.5 shrink-0 animate-spin text-[var(--text-tertiary)]" />
                  ) : (
                    <Badge tone={state.loaded ? "positive" : state.available === false ? "warning" : "info"}>
                      {state.loaded ? "已加载" : state.available === false ? "暂无" : "加载"}
                    </Badge>
                  )}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>
    </Panel>
  );
}
