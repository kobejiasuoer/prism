"use client";

import {
  BarChart3,
  BookOpenCheck,
  CheckCircle2,
  ClipboardCheck,
  Database,
  LoaderCircle,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Target,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { Badge } from "@/components/badge";
import { EmptyState, ErrorState, Panel, SkeletonBlock } from "@/components/data-card";
import {
  useDecisionLedgerReviewCase,
  useGenerateDecisionLedgerAttributionDraft,
  useSaveDecisionLedgerReviewCase,
} from "@/lib/hooks";
import type {
  DecisionLedgerAttributionDraft,
  DecisionLedgerCaseRef,
  DecisionLedgerDetailResponse,
  DecisionLedgerOutcomeEvent,
  DecisionLedgerReviewCaseOption,
  DecisionLedgerReviewCaseSavePayload,
  ShadowCalibrationRow,
  Tone,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import {
  countText,
  pct,
  reasonLabel,
  reviewStatusMeta,
  sampleGuardrailText,
} from "./review-utils";

const FALLBACK_PRIMARY_CAUSES: DecisionLedgerReviewCaseOption[] = [
  { value: "too_strict", label: "判断过严" },
  { value: "too_loose", label: "判断过松" },
  { value: "signal_distortion", label: "信号失真" },
  { value: "execution_gap", label: "执行未跟上" },
  { value: "data_unavailable", label: "数据不可用" },
  { value: "insufficient_sample", label: "样本不足，暂不改规则" },
  { value: "rule_valid_noise", label: "规则有效，个例噪音" },
];

const FALLBACK_SECONDARY_CAUSES: DecisionLedgerReviewCaseOption[] = [
  { value: "volume_too_conservative", label: "量能判断偏保守" },
  { value: "capital_flow_filter_strict", label: "主力资金过滤过严" },
  { value: "market_regime_gate_strict", label: "环境阀门过严" },
  { value: "fundamental_weight_low", label: "个股基本面权重不足" },
  { value: "open_behavior_misread", label: "开盘行为误判" },
  { value: "risk_condition_not_triggered", label: "风险条件未发生" },
  { value: "followup_event_driven", label: "后续事件驱动" },
  { value: "liquidity_insufficient", label: "流动性不足" },
  { value: "data_delay", label: "数据延迟" },
];

const FALLBACK_CONCLUSION_ACTIONS: DecisionLedgerReviewCaseOption[] = [
  { value: "keep_rule", label: "保持规则" },
  { value: "loosen_filter", label: "调宽过滤条件" },
  { value: "tighten_filter", label: "收紧过滤条件" },
  { value: "add_guardrail", label: "增加护栏" },
  { value: "wait_more_samples", label: "等更多样本" },
  { value: "fix_data_pipeline", label: "修复数据链路" },
  { value: "fix_execution_pipeline", label: "修复执行链路" },
];

const FALLBACK_FOLLOW_UP_STATUSES: DecisionLedgerReviewCaseOption[] = [
  { value: "observing", label: "观察中" },
  { value: "sample_insufficient", label: "样本不足" },
  { value: "preliminary_effective", label: "初步有效" },
  { value: "invalid", label: "无效" },
  { value: "adopted", label: "已采纳" },
  { value: "rolled_back", label: "已回滚" },
];

const DIRECT_RULE_ACTIONS = new Set(["loosen_filter", "tighten_filter", "add_guardrail"]);

function latestOutcomeEvent(decision?: DecisionLedgerDetailResponse): DecisionLedgerOutcomeEvent | undefined {
  const events = decision?.outcome_events || [];
  const rank: Record<string, number> = { "T+10": 4, "T+5": 3, "T+3": 2, "T+1": 1 };
  return [...events].sort((a, b) => {
    const windowDiff = (rank[b.window || ""] || 0) - (rank[a.window || ""] || 0);
    if (windowDiff) {
      return windowDiff;
    }
    return String(b.evaluated_at || "").localeCompare(String(a.evaluated_at || ""));
  })[0];
}

function optionLabel(options: DecisionLedgerReviewCaseOption[], value?: string) {
  if (!value) {
    return "-";
  }
  return options.find((option) => option.value === value)?.label || value;
}

function optionLabels(options: DecisionLedgerReviewCaseOption[], values?: string[]) {
  const labels = (values || []).map((value) => optionLabel(options, value)).filter(Boolean);
  return labels.length ? labels.join("、") : "无";
}

function confidenceLabel(value?: string) {
  const labels: Record<string, string> = {
    low: "低",
    medium: "中",
    high: "高",
  };
  return labels[value || ""] || value || "-";
}

function draftStatusLabel(status: string) {
  const labels: Record<string, string> = {
    idle: "未生成",
    generating: "生成中",
    generated: "已生成",
    failed: "生成失败",
    adopted: "已采纳草稿",
    modified: "人工已修改",
  };
  return labels[status] || "未生成";
}

function draftStatusTone(status: string): Tone | string {
  if (status === "failed") {
    return "risk";
  }
  if (status === "modified") {
    return "warning";
  }
  if (status === "adopted" || status === "generated") {
    return "positive";
  }
  if (status === "generating") {
    return "info";
  }
  return "stale";
}

function caseRefLabel(ref: DecisionLedgerCaseRef) {
  const stock = ref.stock_name || ref.stock_code || "历史样本";
  const cause = ref.primary_cause_label || ref.primary_cause || "未归因";
  const date = ref.trade_date ? `${ref.trade_date} · ` : "";
  return `${date}${stock} · ${cause}`;
}

function shadowRefLabel(ref: ShadowCalibrationRow) {
  if (ref.title) {
    return ref.title;
  }
  const label = ref.label || ref.key || "影子样本";
  const windowLabel = ref.window || "T+5";
  return `${windowLabel} ${label} · 样本 ${countText(ref.total)}`;
}

function shadowRefDetail(ref: ShadowCalibrationRow) {
  const hasRejectStats = (ref.avoided_loss || 0) > 0 || (ref.missed_opportunity || 0) > 0;
  const parts = hasRejectStats
    ? [`避亏 ${ref.avoided_loss_rate ?? 0}%`, `错过 ${ref.missed_opportunity_rate ?? 0}%`]
    : [`验证 ${ref.validated_rate ?? 0}%`, `失效 ${ref.invalidated_rate ?? 0}%`];
  parts.push(`均值 ${pct(ref.avg_return_pct)}`);
  return parts.join(" · ");
}

export function ReviewCaseWorkspace({ decisionId }: { decisionId: string }) {
  const workbench = useDecisionLedgerReviewCase(decisionId, Boolean(decisionId));
  const saveMutation = useSaveDecisionLedgerReviewCase();
  const draftMutation = useGenerateDecisionLedgerAttributionDraft();
  const data = workbench.data;
  const decision = data?.decision;
  const learning = data?.learning_record;
  const existingCase = data?.review_case || null;
  const outcome = latestOutcomeEvent(decision);
  const [primaryCause, setPrimaryCause] = useState("insufficient_sample");
  const [secondaryCauses, setSecondaryCauses] = useState<string[]>([]);
  const [reviewNote, setReviewNote] = useState("");
  const [conclusionAction, setConclusionAction] = useState("wait_more_samples");
  const [ruleHypothesis, setRuleHypothesis] = useState("");
  const [followUpStatus, setFollowUpStatus] = useState("sample_insufficient");
  const [followUpDueAt, setFollowUpDueAt] = useState("");
  const [feedback, setFeedback] = useState("");
  const [aiDraft, setAiDraft] = useState<DecisionLedgerAttributionDraft | null>(null);
  const [draftStatus, setDraftStatus] = useState("idle");
  const [draftFeedback, setDraftFeedback] = useState("");

  useEffect(() => {
    if (existingCase) {
      setPrimaryCause(existingCase.primary_cause || "insufficient_sample");
      setSecondaryCauses(existingCase.secondary_causes || []);
      setReviewNote(existingCase.review_note || "");
      setConclusionAction(existingCase.conclusion_action || "wait_more_samples");
      setRuleHypothesis(existingCase.rule_hypothesis || "");
      setFollowUpStatus(existingCase.follow_up_status || "sample_insufficient");
      setFollowUpDueAt(existingCase.follow_up_due_at || "");
      setAiDraft(existingCase.ai_draft || null);
      setDraftStatus(existingCase.ai_draft ? (Object.keys(existingCase.human_overrides || {}).length ? "modified" : "adopted") : "idle");
      return;
    }
    const reason = learning?.review_reason_key;
    setPrimaryCause(reason === "execution_gap" ? "execution_gap" : reason === "data_issue" ? "data_unavailable" : "insufficient_sample");
    setSecondaryCauses([]);
    setReviewNote("");
    setConclusionAction("wait_more_samples");
    setRuleHypothesis("");
    setFollowUpStatus("sample_insufficient");
    setFollowUpDueAt("");
    setAiDraft(null);
    setDraftStatus("idle");
  }, [existingCase, learning?.review_reason_key]);

  const options = data?.options || {};
  const primaryOptions = options.primary_causes?.length ? options.primary_causes : FALLBACK_PRIMARY_CAUSES;
  const secondaryOptions = options.secondary_causes?.length ? options.secondary_causes : FALLBACK_SECONDARY_CAUSES;
  const conclusionOptions = options.conclusion_actions?.length ? options.conclusion_actions : FALLBACK_CONCLUSION_ACTIONS;
  const followUpOptions = options.follow_up_statuses?.length ? options.follow_up_statuses : FALLBACK_FOLLOW_UP_STATUSES;
  const sampleCount = existingCase?.sample_count || data?.guardrail?.sample_count || 1;
  const directRuleSelected = DIRECT_RULE_ACTIONS.has(conclusionAction);

  function markHumanEdited() {
    if (aiDraft && ["generated", "adopted"].includes(draftStatus)) {
      setDraftStatus("modified");
    }
  }

  function applyDraft(draft: DecisionLedgerAttributionDraft, status = "adopted") {
    setPrimaryCause(draft.primary_cause || "insufficient_sample");
    setSecondaryCauses(draft.secondary_causes || []);
    setReviewNote(draft.review_note || "");
    setConclusionAction(draft.conclusion_action || "wait_more_samples");
    setRuleHypothesis(draft.rule_hypothesis || "");
    setFollowUpStatus(draft.follow_up_status || "sample_insufficient");
    setAiDraft(draft);
    setDraftStatus(status);
  }

  function generateDraft() {
    setDraftFeedback("");
    setFeedback("");
    setDraftStatus("generating");
    draftMutation.mutate(decisionId, {
      onSuccess: (response) => {
        applyDraft(response.draft, "adopted");
        setDraftFeedback(response.draft.fallback_reason ? "已使用本地启发式草稿预填。" : "已生成并预填人工归因。");
      },
      onError: (error) => {
        setDraftStatus("failed");
        setDraftFeedback(error instanceof Error ? error.message : "AI 预归因生成失败。");
      },
    });
  }

  function toggleSecondary(value: string) {
    markHumanEdited();
    setSecondaryCauses((current) =>
      current.includes(value) ? current.filter((item) => item !== value) : [...current, value],
    );
  }

  function saveCase() {
    setFeedback("");
    const payload: DecisionLedgerReviewCaseSavePayload = {
      primary_cause: primaryCause,
      secondary_causes: secondaryCauses,
      review_note: reviewNote,
      conclusion_action: conclusionAction,
      rule_hypothesis: ruleHypothesis,
      follow_up_status: followUpStatus,
      follow_up_due_at: followUpDueAt || undefined,
      ai_draft: aiDraft || undefined,
      human_final: {
        primary_cause: primaryCause,
        secondary_causes: secondaryCauses,
        review_note: reviewNote,
        conclusion_action: conclusionAction,
        rule_hypothesis: ruleHypothesis,
        follow_up_status: followUpStatus,
        follow_up_due_at: followUpDueAt || undefined,
      },
      attribution_confidence: aiDraft?.confidence,
      evidence_refs: aiDraft?.evidence || [],
      human_check_required: aiDraft?.human_check_required || [],
      similar_case_refs: aiDraft?.similar_case_refs || [],
      shadow_sample_refs: aiDraft?.shadow_sample_refs || [],
    };
    saveMutation.mutate(
      { decisionId, payload },
      {
        onSuccess: (response) => {
          setFeedback(`已保存 Review Case：${response.review_case.evidence_strength_label || "观察假设"}。`);
        },
        onError: (error) => {
          setFeedback(error instanceof Error ? error.message : "保存失败。");
        },
      },
    );
  }

  if (workbench.isLoading && !data) {
    return (
      <section className="mb-7">
        <SkeletonBlock className="h-[520px] w-full" />
      </section>
    );
  }

  if (workbench.isError || !data || !decision) {
    return (
      <section className="mb-7">
        <ErrorState message="Review Case 工作台暂不可用" onRetry={() => void workbench.refetch()} />
      </section>
    );
  }

  return (
    <section className="mb-7 scroll-mt-6" id="review-case-workbench">
      <Panel
        title="单条 Review Case 工作台"
        eyebrow="Attribution"
        action={
          <Link
            href="/review"
            className="focus-ring inline-flex items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            返回队列
          </Link>
        }
      >
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.15fr)_430px]">
          <div className="space-y-4">
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Badge tone={reviewStatusMeta(learning?.review_status).tone}>{reviewStatusMeta(learning?.review_status).label}</Badge>
                <Badge tone="info">{decision.trade_date}</Badge>
                <Badge tone={learning?.outcome_tone || "watch"}>{reasonLabel(learning?.review_reason_key, learning?.review_reason)}</Badge>
              </div>
              <h2 className="text-2xl font-semibold leading-tight text-[var(--text-primary)]">
                {decision.stock?.name || learning?.name || decision.stock?.code}
                <span className="mono ml-2 text-base text-[var(--text-tertiary)]">{decision.stock?.code}</span>
              </h2>
              <p className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
                {learning?.next_action_reason || "先完成归因，保存结构化 Review Case，再让同类样本进入模式聚合。"}
              </p>
              <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                {existingCase?.evidence_strength_detail || data.guardrail?.detail || sampleGuardrailText(existingCase)}
              </div>
            </div>

            <WorkbenchSection icon={Target} title="当时我为什么这么判断">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <TextFact label="原始结论" value={decision.recommendation?.main_conclusion || "-"} />
                <TextFact label="推荐动作" value={decision.recommendation?.action_label || decision.recommendation?.action || "-"} />
                <TextFact label="触发信号" value={decision.recommendation?.trigger_condition || "-"} />
                <TextFact label="风险条件" value={decision.recommendation?.risk_summary || decision.recommendation?.stop_condition || "-"} />
                <TextFact label="数据新鲜度" value={`${decision.evidence_snapshot?.data_trade_date || "-"} · ${decision.evidence_snapshot?.readiness_mode || "-"}`} />
                <TextFact label="所处链路" value={`${decision.source?.lane || "-"} / ${decision.source?.surface || "-"}`} />
              </div>
            </WorkbenchSection>

            <WorkbenchSection icon={BarChart3} title="后来市场发生了什么">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                {(decision.outcome_events || []).map((event) => (
                  <OutcomeCard key={event.event_id || event.window} event={event} />
                ))}
                {!decision.outcome_events?.length ? <EmptyState>暂无 outcome。</EmptyState> : null}
              </div>
            </WorkbenchSection>

            <WorkbenchSection icon={ShieldAlert} title="差异在哪里">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <TextFact label="原始担忧是否发生" value={outcome?.boundary_checks ? "查看 boundary_checks；当前以人工核对为准" : "暂无 boundary 证据"} />
                <TextFact label="触发条件是否失效" value={outcome?.classification?.summary || learning?.review_reason || "-"} />
                <TextFact label="风险过滤是否过严" value={learning?.review_reason_key === "missed_opportunity" ? "可能过严，但单样本只能形成观察假设。" : "需要结合归因判断。"} />
                <TextFact label="执行/数据差异" value={learning?.execution_status === "missing" ? "缺执行记录" : outcome?.quality?.data_issue || "未见明确数据阻塞"} />
              </div>
            </WorkbenchSection>
          </div>

          <div className="space-y-4">
            <AttributionDraftCard
              draft={aiDraft}
              status={draftStatus}
              feedback={draftFeedback}
              primaryOptions={primaryOptions}
              secondaryOptions={secondaryOptions}
              conclusionOptions={conclusionOptions}
              onGenerate={generateDraft}
              onAdopt={() => {
                if (aiDraft) {
                  applyDraft(aiDraft, "adopted");
                  setDraftFeedback("已采纳草稿。");
                }
              }}
              onClear={() => {
                setAiDraft(null);
                setDraftStatus("idle");
                setDraftFeedback("已清空草稿。");
              }}
              isGenerating={draftMutation.isPending || draftStatus === "generating"}
            />
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
              <div className="mb-3 flex items-center gap-2">
                <ClipboardCheck size={16} className="text-[var(--text-tertiary)]" />
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">人工归因</h3>
              </div>
              <OptionGrid
                label="主归因"
                options={primaryOptions}
                value={primaryCause}
                onChange={(value) => {
                  markHumanEdited();
                  setPrimaryCause(value);
                }}
              />
              <CheckboxGrid
                label="辅助归因"
                options={secondaryOptions}
                values={secondaryCauses}
                onToggle={toggleSecondary}
              />
              <label className="mt-4 block">
                <span className="text-[12px] font-medium text-[var(--text-primary)]">复盘备注</span>
                <textarea
                  value={reviewNote}
                  onChange={(event) => {
                    markHumanEdited();
                    setReviewNote(event.target.value);
                  }}
                  className="focus-ring mt-2 min-h-24 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[13px] leading-5 text-[var(--text-primary)] outline-none"
                  placeholder="一句话说明这次判断错在哪里，或者为什么暂不改规则。"
                />
              </label>
            </div>

            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
              <div className="mb-3 flex items-center gap-2">
                <BookOpenCheck size={16} className="text-[var(--text-tertiary)]" />
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">沉淀动作</h3>
              </div>
              <OptionGrid
                label="结论动作"
                options={conclusionOptions}
                value={conclusionAction}
                onChange={(value) => {
                  markHumanEdited();
                  setConclusionAction(value);
                }}
              />
              {directRuleSelected && sampleCount < 5 ? (
                <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--warning)_24%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                  当前同类样本少于 5 条；保存后只会生成观察/验证假设，不会生成可执行规则修改。
                </div>
              ) : null}
              <label className="mt-4 block">
                <span className="text-[12px] font-medium text-[var(--text-primary)]">规则假设</span>
                <textarea
                  value={ruleHypothesis}
                  onChange={(event) => {
                    markHumanEdited();
                    setRuleHypothesis(event.target.value);
                  }}
                  className="focus-ring mt-2 min-h-24 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[13px] leading-5 text-[var(--text-primary)] outline-none"
                  placeholder="例如：类似形态需要承接确认后升级观察，而不是直接排除。"
                />
              </label>
              <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="block">
                  <span className="text-[12px] font-medium text-[var(--text-primary)]">验证状态</span>
                  <select
                    value={followUpStatus}
                    onChange={(event) => {
                      markHumanEdited();
                      setFollowUpStatus(event.target.value);
                    }}
                    className="focus-ring mt-2 h-10 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-primary)] outline-none"
                  >
                    {followUpOptions.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="text-[12px] font-medium text-[var(--text-primary)]">下次验证日期</span>
                  <input
                    value={followUpDueAt}
                    onChange={(event) => {
                      markHumanEdited();
                      setFollowUpDueAt(event.target.value);
                    }}
                    className="focus-ring mt-2 h-10 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-primary)] outline-none"
                    placeholder="YYYY-MM-DD"
                  />
                </label>
              </div>
              <button
                type="button"
                onClick={saveCase}
                disabled={saveMutation.isPending || !primaryCause || !conclusionAction}
                className="focus-ring prism-btn prism-btn-primary mt-4 w-full"
              >
                {saveMutation.isPending ? <LoaderCircle size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
                保存 Review Case
              </button>
              {feedback ? (
                <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                  {feedback}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </Panel>
    </section>
  );
}

function AttributionDraftCard({
  draft,
  status,
  feedback,
  primaryOptions,
  secondaryOptions,
  conclusionOptions,
  onGenerate,
  onAdopt,
  onClear,
  isGenerating,
}: {
  draft: DecisionLedgerAttributionDraft | null;
  status: string;
  feedback: string;
  primaryOptions: DecisionLedgerReviewCaseOption[];
  secondaryOptions: DecisionLedgerReviewCaseOption[];
  conclusionOptions: DecisionLedgerReviewCaseOption[];
  onGenerate: () => void;
  onAdopt: () => void;
  onClear: () => void;
  isGenerating: boolean;
}) {
  const similarRefs = draft?.similar_case_refs || [];
  const patternRefs = draft?.pattern_memory_refs || [];
  const shadowRefs = draft?.shadow_sample_refs || [];

  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Sparkles size={16} className="text-[var(--info)]" />
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">AI 预归因</h3>
          <Badge tone={draftStatusTone(status)}>{draftStatusLabel(status)}</Badge>
        </div>
        <button
          type="button"
          onClick={onGenerate}
          disabled={isGenerating}
          className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isGenerating ? <LoaderCircle size={14} className="animate-spin" /> : draft ? <RefreshCw size={14} /> : <Sparkles size={14} />}
          {draft ? "重新生成" : "AI 预归因"}
        </button>
      </div>

      {draft ? (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <TextFact label="建议主归因" value={optionLabel(primaryOptions, draft.primary_cause)} />
            <TextFact label="建议结论动作" value={optionLabel(conclusionOptions, draft.conclusion_action)} />
            <TextFact label="样本强度" value={`${draft.evidence_strength_label || "观察假设"} · ${draft.sample_count || 1} 条`} />
            <TextFact label="AI 置信度" value={confidenceLabel(draft.confidence)} />
          </div>
          <TextFact label="建议辅助归因" value={optionLabels(secondaryOptions, draft.secondary_causes)} />
          {draft.rule_hypothesis ? (
            <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
              {draft.rule_hypothesis}
            </div>
          ) : null}
          {draft.evidence?.length ? (
            <div>
              <div className="mb-1 text-[11px] font-medium text-[var(--text-tertiary)]">判断依据</div>
              <div className="space-y-1.5">
                {draft.evidence.slice(0, 4).map((item) => (
                  <div key={item} className="rounded-md bg-[var(--bg-secondary)] px-3 py-1.5 text-[11px] leading-4 text-[var(--text-secondary)]">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {draft.human_check_required?.length ? (
            <div>
              <div className="mb-1 text-[11px] font-medium text-[var(--text-tertiary)]">需要人工确认</div>
              <div className="space-y-1.5">
                {draft.human_check_required.slice(0, 3).map((item) => (
                  <div key={item} className="rounded-md bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-3 py-1.5 text-[11px] leading-4 text-[var(--text-secondary)]">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {similarRefs.length || patternRefs.length ? (
            <div>
              <div className="mb-1 text-[11px] font-medium text-[var(--text-tertiary)]">相似历史样本</div>
              <div className="space-y-1.5">
                {similarRefs.slice(0, 3).map((ref) => (
                  <div key={ref.review_case_id || ref.decision_id || caseRefLabel(ref)} className="rounded-md bg-[var(--bg-secondary)] px-3 py-1.5 text-[11px] leading-4 text-[var(--text-secondary)]">
                    {caseRefLabel(ref)}
                  </div>
                ))}
                {patternRefs.slice(0, 2).map((ref) => (
                  <div key={ref.review_case_id || ref.decision_id || ref.learning_hint} className="rounded-md bg-[var(--bg-secondary)] px-3 py-1.5 text-[11px] leading-4 text-[var(--text-secondary)]">
                    {ref.learning_hint || caseRefLabel(ref)}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {shadowRefs.length ? (
            <div>
              <div className="mb-1 flex items-center gap-2 text-[11px] font-medium text-[var(--text-tertiary)]">
                <Database size={12} />
                影子样本参考
              </div>
              <div className="space-y-1.5">
                {shadowRefs.slice(0, 3).map((ref) => (
                  <div
                    key={`${ref.axis || "shadow"}-${ref.key || ref.label || shadowRefLabel(ref)}`}
                    className="rounded-md border border-[color-mix(in_srgb,var(--warning)_18%,transparent)] bg-[color-mix(in_srgb,var(--warning)_7%,transparent)] px-3 py-2"
                  >
                    <div className="line-clamp-1 text-[11px] font-medium text-[var(--text-primary)]">
                      {shadowRefLabel(ref)}
                    </div>
                    <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
                      {shadowRefDetail(ref)}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-2 text-[11px] leading-4 text-[var(--text-tertiary)]">
                研究口径参考，不计入真实样本数，也不解锁规则修改。
              </div>
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onAdopt}
              className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              <CheckCircle2 size={14} />
              采纳草稿
            </button>
            <button
              type="button"
              onClick={onClear}
              className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              清空草稿
            </button>
          </div>
        </div>
      ) : (
        <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-[12px] leading-5 text-[var(--text-secondary)]">
          等待生成结构化草稿。
        </div>
      )}

      {feedback ? (
        <div className="mt-3 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[12px] leading-5 text-[var(--text-secondary)]">
          {feedback}
        </div>
      ) : null}
    </div>
  );
}

function WorkbenchSection({
  icon: Icon,
  title,
  children,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon size={16} className="text-[var(--text-tertiary)]" />
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
      </div>
      {children}
    </div>
  );
}

function TextFact({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <div className="text-[11px] text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-[12px] leading-5 text-[var(--text-primary)]">{value || "-"}</div>
    </div>
  );
}

function OutcomeCard({ event }: { event: DecisionLedgerOutcomeEvent }) {
  const tone = (event.classification?.tone as Tone | undefined) || "watch";
  return (
    <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[12px] font-medium text-[var(--text-primary)]">{event.window || "Outcome"}</span>
        <Badge tone={tone}>{reasonLabel(event.classification?.label, event.classification?.label)}</Badge>
      </div>
      <div className="grid grid-cols-2 gap-2 text-[11px] text-[var(--text-tertiary)]">
        <span>收益 {pct(event.market_data?.return_pct)}</span>
        <span>相对 {pct(event.market_data?.relative_return_pct)}</span>
        <span>最好 {pct(event.market_data?.max_favorable_pct)}</span>
        <span>最差 {pct(event.market_data?.max_adverse_pct)}</span>
      </div>
      <p className="mt-2 line-clamp-3 text-[11px] leading-4 text-[var(--text-secondary)]">
        {event.classification?.summary || event.classification?.reasons?.[0] || "-"}
      </p>
    </div>
  );
}

function OptionGrid({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: DecisionLedgerReviewCaseOption[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="mt-4 first:mt-0">
      <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">{label}</div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              "focus-ring min-h-9 rounded-md border px-3 py-2 text-left text-[12px] transition-colors",
              value === option.value
                ? "border-[var(--info)] bg-[color-mix(in_srgb,var(--info)_12%,transparent)] text-[var(--text-primary)]"
                : "border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function CheckboxGrid({
  label,
  options,
  values,
  onToggle,
}: {
  label: string;
  options: DecisionLedgerReviewCaseOption[];
  values: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <div className="mt-4">
      <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">{label}</div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {options.map((option) => {
          const active = values.includes(option.value);
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onToggle(option.value)}
              className={cn(
                "focus-ring min-h-9 rounded-md border px-3 py-2 text-left text-[12px] transition-colors",
                active
                  ? "border-[var(--info)] bg-[color-mix(in_srgb,var(--info)_12%,transparent)] text-[var(--text-primary)]"
                  : "border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
              )}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
