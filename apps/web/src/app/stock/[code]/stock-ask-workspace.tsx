"use client";

import { LoaderCircle, SendHorizontal } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/badge";
import { EmptyState, Panel, SkeletonBlock } from "@/components/data-card";
import { MetricCard } from "@/components/metric-card";
import { api } from "@/lib/api";
import type {
  AskCaseData,
  AskFollowupResponse,
  AskFollowupShell,
} from "@/lib/types";
import { StockDecisionCanonicalSummary } from "./stock-decision-support";

const followupHistoryTurnLimit = 3;

type StockAskWorkspaceProps = {
  code: string;
  stockName: string;
  askCase?: AskCaseData;
  followupShell?: AskFollowupShell | null;
  isLoading: boolean;
  sourceGeneratedAt?: string;
};

function historyPayload(messages: AskFollowupResponse[]) {
  return messages.slice(-followupHistoryTurnLimit).flatMap((item) => [
    {
      role: "user",
      title: "继续追问",
      summary: item.question,
    },
    {
      role: "assistant",
      title: item.answer?.title || "追问回答",
      summary: item.answer?.summary || "",
      bullets: (item.answer?.bullets || []).slice(0, 4),
      references: (item.answer?.references || []).slice(0, 3),
      engine_label: item.answer?.engine_label || "",
    },
  ]);
}

export function StockAskWorkspace({
  code,
  stockName,
  askCase,
  followupShell,
  isLoading,
  sourceGeneratedAt,
}: StockAskWorkspaceProps) {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<AskFollowupResponse[]>([]);
  const [pendingQuestion, setPendingQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState("");
  const threadEndRef = useRef<HTMLDivElement | null>(null);
  const latestFollowups = messages.at(-1)?.answer?.followups || [];
  const presetQuestions = (followupShell?.presets || [])
    .map((item) => ({
      label: item.label || item.question,
      value: item.question,
    }))
    .filter((item) => item.value);
  const suggestedQuestions = latestFollowups.length
    ? latestFollowups.map((item) => ({ label: item, value: item }))
    : presetQuestions.length
      ? presetQuestions
      : [
          "这只今天要不要动？",
          "仓位和止损怎么设？",
          "最大的反向风险是什么？",
          "结论对应哪些证据？",
        ].map((item) => ({ label: item, value: item }));

  useEffect(() => {
    setQuestion("");
    setMessages([]);
    setPendingQuestion("");
    setAskError("");
    setAsking(false);
  }, [code]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ block: "nearest" });
  }, [messages, pendingQuestion]);

  async function submitFollowup(value?: string) {
    const text = (value ?? question).trim();
    if (!text || asking) {
      return;
    }
    setAsking(true);
    setAskError("");
    setPendingQuestion(text);
    try {
      const payload = await api.askFollowup({
        query: code,
        question: text,
        history: historyPayload(messages),
      });
      setMessages((current) => [...current, payload]);
      setQuestion("");
    } catch (error) {
      setAskError(error instanceof Error ? error.message : "追问失败");
    } finally {
      setPendingQuestion("");
      setAsking(false);
    }
  }

  return (
    <div
      data-testid="stock-ask-workspace"
      className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_420px]"
    >
      <Panel title="当前结论" eyebrow="Ask Context">
        <div className="surface-card p-4">
          {isLoading ? (
            <SkeletonBlock className="h-32 w-full" />
          ) : askCase ? (
            <div className="flex flex-col gap-4">
              <div>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <Badge tone="info">{stockName}</Badge>
                  {askCase.hero?.status_label ? (
                    <Badge tone="watch">{askCase.hero.status_label}</Badge>
                  ) : null}
                </div>
                <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                  {askCase.hero?.title || `${stockName} ${code}`}
                </h2>
                <p className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
                  {askCase.hero?.summary ||
                    "暂无问股摘要，直接输入问题继续追问。"}
                </p>
              </div>

              {(askCase.cross_cards || []).length ? (
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  {askCase.cross_cards?.slice(0, 4).map((card, index) => (
                    <MetricCard
                      key={`${card.label}-${index}`}
                      {...card}
                      tone={card.tone || "info"}
                    />
                  ))}
                </div>
              ) : null}

              {askCase.context_tags?.length ? (
                <div className="flex flex-wrap gap-2">
                  {askCase.context_tags.map((item) => (
                    <Badge key={item} tone="info">
                      {item}
                    </Badge>
                  ))}
                </div>
              ) : null}

              {askCase.canonical_decision ? (
                <StockDecisionCanonicalSummary
                  canonical={askCase.canonical_decision}
                  sourceLabel="Ask 临时分析"
                  generatedAt={sourceGeneratedAt}
                  embedded
                />
              ) : null}
            </div>
          ) : (
            <EmptyState>
              暂无问股上下文，输入问题后会使用规则引擎回答。
            </EmptyState>
          )}
        </div>
      </Panel>

      <Panel title="连续追问" eyebrow="Follow-up">
        <div className="surface-card flex min-h-[520px] flex-col p-4">
          <div className="min-h-0 flex-1 space-y-3 overflow-auto pr-1">
            {!messages.length ? (
              <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-[13px] leading-6 text-[var(--text-secondary)]">
                {followupShell?.starter?.summary ||
                  "可以围绕仓位、买卖点、风险和证据继续问，系统会带着本轮对话上下文回答。"}
                {followupShell?.engine_badge?.label ? (
                  <span className="mt-2 block text-[12px] text-[var(--text-tertiary)]">
                    {followupShell.engine_badge.label}
                    {followupShell.engine_badge.detail
                      ? `：${followupShell.engine_badge.detail}`
                      : ""}
                  </span>
                ) : null}
              </div>
            ) : null}
            {messages.map((item, index) => (
              <div key={`${item.question}-${index}`} className="space-y-2">
                <div className="ml-auto max-w-[88%] rounded-md bg-[var(--info)] px-3 py-2 text-[13px] leading-6 text-white">
                  {item.question}
                </div>
                <div className="max-w-[92%] rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className="text-[13px] font-medium text-[var(--text-primary)]">
                      {item.answer?.title || "追问回答"}
                    </span>
                    {item.answer?.intent_label ? (
                      <Badge tone="watch">{item.answer.intent_label}</Badge>
                    ) : null}
                    {item.answer?.engine_label ? (
                      <Badge tone="info">{item.answer.engine_label}</Badge>
                    ) : null}
                  </div>
                  <p className="text-[13px] leading-6 text-[var(--text-secondary)]">
                    {item.answer?.summary || "-"}
                  </p>
                  {item.answer?.bullets?.length ? (
                    <ul className="mt-2 list-disc space-y-1 pl-4 text-[12px] leading-5 text-[var(--text-secondary)]">
                      {item.answer.bullets.map((bullet, bulletIndex) => (
                        <li key={`${bullet}-${bulletIndex}`}>{bullet}</li>
                      ))}
                    </ul>
                  ) : null}
                  {item.answer?.references?.length ? (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {item.answer.references.map((ref, refIndex) => (
                        <Badge key={`${ref}-${refIndex}`} tone="watch">
                          {ref}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            ))}
            {pendingQuestion ? (
              <div className="space-y-2">
                <div className="ml-auto max-w-[88%] rounded-md bg-[var(--info)] px-3 py-2 text-[13px] leading-6 text-white">
                  {pendingQuestion}
                </div>
                <div className="inline-flex max-w-[92%] items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-[13px] text-[var(--text-secondary)]">
                  <LoaderCircle size={14} className="animate-spin" />
                  正在识别追问并整理回答
                </div>
              </div>
            ) : null}
            <div ref={threadEndRef} />
          </div>

          <div className="mt-4 border-t border-[var(--border-subtle)] pt-4">
            {suggestedQuestions.length ? (
              <div className="mb-3 flex flex-wrap gap-2">
                {suggestedQuestions.slice(0, 4).map((item) => (
                  <button
                    key={`${item.label}-${item.value}`}
                    type="button"
                    className="focus-ring rounded-md border border-[var(--border-subtle)] px-2.5 py-1.5 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    onClick={() => void submitFollowup(item.value)}
                    disabled={asking}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            ) : null}
            <form
              className="flex items-end gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                void submitFollowup();
              }}
            >
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    (event.metaKey || event.ctrlKey) &&
                    event.key === "Enter"
                  ) {
                    event.preventDefault();
                    void submitFollowup();
                  }
                }}
                placeholder="继续问：仓位怎么控？风险在哪？证据是什么？"
                className="focus-ring min-h-20 flex-1 resize-y rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-[13px] leading-6 text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
              />
              <button
                type="submit"
                className="focus-ring flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-[var(--text-primary)] text-[var(--text-inverse)] disabled:cursor-not-allowed disabled:opacity-50"
                disabled={asking || !question.trim()}
                aria-label="发送追问"
              >
                {asking ? (
                  <LoaderCircle size={16} className="animate-spin" />
                ) : (
                  <SendHorizontal size={16} />
                )}
              </button>
            </form>
            {askError ? (
              <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--negative)_20%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
                {askError}
              </div>
            ) : null}
          </div>
        </div>
      </Panel>
    </div>
  );
}
