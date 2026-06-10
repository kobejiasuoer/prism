"use client";

import { AlertTriangle, ChevronRight, FileJson, LoaderCircle, RotateCcw, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/badge";
import { ErrorState, Panel } from "@/components/data-card";
import { MetricCard } from "@/components/metric-card";
import { ApiError } from "@/lib/api";
import { useParameters, useSaveParameters } from "@/lib/hooks";
import type { ParametersResponse } from "@/lib/types";

export function ParametersEditor() {
  const [raw, setRaw] = useState("");
  const [dirty, setDirty] = useState(false);
  const [localError, setLocalError] = useState("");
  const [success, setSuccess] = useState("");
  const [evaluation, setEvaluation] = useState<ParametersResponse["evaluation"]>(undefined);
  const [editorOpen, setEditorOpen] = useState(false);
  const [unsafeAcknowledged, setUnsafeAcknowledged] = useState(false);
  const [unsafeConfirm, setUnsafeConfirm] = useState("");
  const parameters = useParameters({ enabled: editorOpen });
  const saveParameters = useSaveParameters();
  const unsafeReady = unsafeAcknowledged && unsafeConfirm.trim() === "UNSAFE_APPLY";

  useEffect(() => {
    if (parameters.data?.raw && !dirty) {
      setRaw(parameters.data.raw);
    }
  }, [dirty, parameters.data?.raw]);

  const parsedSummary = useMemo(() => {
    try {
      const parsed = JSON.parse(raw || "{}") as Record<string, unknown>;
      return {
        ok: true,
        stocks: Array.isArray(parsed.stocks) ? parsed.stocks.length : 0,
        keys: Object.keys(parsed).length,
      };
    } catch {
      return { ok: false, stocks: 0, keys: 0 };
    }
  }, [raw]);

  function formatJson() {
    setLocalError("");
    setEvaluation(undefined);
    try {
      setRaw(JSON.stringify(JSON.parse(raw), null, 2));
      setDirty(true);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "JSON 格式错误");
    }
  }

  function reloadFromDisk() {
    setLocalError("");
    setSuccess("");
    setEvaluation(undefined);
    parameters.refetch().then((result) => {
      if (result.data?.raw) {
        setRaw(result.data.raw);
        setDirty(false);
      }
    });
  }

  function save(unsafeApply = false): void {
    setLocalError("");
    setSuccess("");
    setEvaluation(undefined);
    if (unsafeApply && !unsafeReady) {
      setLocalError("强制保存前需要勾选确认，并输入 UNSAFE_APPLY。");
      return;
    }
    try {
      JSON.parse(raw);
    } catch (error) {
      setLocalError(error instanceof Error ? error.message : "JSON 格式错误");
      return;
    }
    saveParameters.mutate(
      { payload: { raw }, unsafeApply },
      {
        onSuccess: (payload) => {
          if (payload.evaluation) {
            setEvaluation(payload.evaluation);
          }
          setRaw(payload.raw);
          setDirty(false);
          setUnsafeAcknowledged(false);
          setUnsafeConfirm("");
          setSuccess("参数已保存到磁盘。");
        },
        onError: (error) => {
          setLocalError(error instanceof Error ? error.message : "保存失败");
          // The 400 response body still carries `evaluation` — surface it so the
          // user can see the rule that blocked them and use 强制保存 if needed.
          if (error instanceof ApiError && error.payload && typeof error.payload === "object") {
            const payload = error.payload as { evaluation?: ParametersResponse["evaluation"] };
            if (payload.evaluation) {
              setEvaluation(payload.evaluation);
            }
          }
        },
      },
    );
  }

  return (
    <Panel
      title="参数编辑"
      eyebrow="Advanced / Dangerous"
      action={
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="focus-ring prism-btn prism-btn-secondary"
            onClick={reloadFromDisk}
            disabled={parameters.isFetching || !editorOpen}
          >
            <RotateCcw size={13} className={parameters.isFetching ? "animate-spin" : ""} />
            重载
          </button>
          <button
            type="button"
            className="focus-ring prism-btn prism-btn-primary"
            onClick={() => save()}
            disabled={saveParameters.isPending || !raw.trim() || !editorOpen}
          >
            {saveParameters.isPending ? <LoaderCircle size={13} className="animate-spin" /> : <Save size={13} />}
            保存
          </button>
        </div>
      }
    >
      {parameters.isError ? <ErrorState message="参数接口暂不可用" onRetry={() => void parameters.refetch()} /> : null}

      <details
        className="surface-card p-4"
        open={editorOpen}
        onToggle={(event) => setEditorOpen(event.currentTarget.open)}
      >
        <summary className="cursor-pointer list-none">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <Badge tone="risk">危险操作隔离</Badge>
                <Badge tone="warning">写入配置文件</Badge>
              </div>
              <div className="text-[13px] font-medium text-[var(--text-primary)]">参数编辑默认收起</div>
              <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                普通保存会写入自选股参数文件；强制保存会绕过评估硬拦截，可能影响后续刷新产物和 readiness。
              </p>
            </div>
            <span className="focus-ring inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-secondary)]">
              {editorOpen ? "收起" : "展开参数编辑"}
              <ChevronRight size={13} className={editorOpen ? "rotate-90" : ""} />
            </span>
          </div>
        </summary>
        <div className="mt-4">
        <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {(parameters.data?.summary_cards || []).map((card) => (
            <MetricCard key={card.label} {...card} tone={card.tone || "info"} />
          ))}
          {!parameters.data?.summary_cards?.length ? (
            <>
              <MetricCard label="JSON" value={parsedSummary.ok ? "有效" : "错误"} detail={`${parsedSummary.keys} 个键`} tone={parsedSummary.ok ? "positive" : "risk"} />
              <MetricCard label="stocks" value={parsedSummary.stocks} detail="本地解析" tone="info" />
            </>
          ) : null}
        </div>

        <div className="mb-4 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3">
          <div className="mb-2 text-[12px] font-medium text-[var(--text-primary)]">读写文件</div>
          <div className="mono break-all text-[11px] leading-5 text-[var(--text-tertiary)]">
            {parameters.data?.path || "等待 /api/parameters"}
          </div>
          {parameters.data?.updated_at ? (
            <div className="mt-2 text-[12px] text-[var(--text-tertiary)]">磁盘更新时间：{parameters.data.updated_at}</div>
          ) : null}
        </div>

        <div className="mb-4 flex flex-wrap gap-2">
          {(parameters.data?.required_groups || []).map((item) => (
            <Badge key={item.key} tone={item.ok ? "positive" : "risk"}>
              {item.label} {item.ok ? "OK" : "缺失"}
            </Badge>
          ))}
        </div>

        <div className="overflow-hidden rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
            <div className="flex items-center gap-2 text-[12px] text-[var(--text-tertiary)]">
              <FileJson size={14} />
              原始 JSON
              {dirty ? <Badge tone="watch">未保存</Badge> : <Badge tone="positive">已同步</Badge>}
            </div>
            <button
              type="button"
              className="focus-ring prism-btn prism-btn-secondary prism-btn-sm"
              onClick={formatJson}
            >
              格式化
            </button>
          </div>
          <textarea
            value={raw}
            onChange={(event) => {
              setRaw(event.target.value);
              setDirty(true);
              setLocalError("");
              setSuccess("");
              // Drop any stale evaluation banner — the user is editing now,
              // and the previous evaluation no longer reflects current input.
              setEvaluation(undefined);
            }}
            spellCheck={false}
            className="mono h-[480px] w-full resize-y bg-transparent px-4 py-3 text-[12px] leading-6 text-[var(--text-secondary)] outline-none placeholder:text-[var(--text-tertiary)]"
            placeholder="等待参数文件加载..."
          />
        </div>

        {localError || saveParameters.isError ? (
          <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--negative)_20%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            {localError || saveParameters.error?.message || "保存失败"}
          </div>
        ) : null}
        {success ? (
          <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--positive)_20%,transparent)] bg-[color-mix(in_srgb,var(--positive)_8%,transparent)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            {success}
          </div>
        ) : null}
        {evaluation && evaluation.errors.length > 0 ? (
          <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--negative)_20%,transparent)] bg-[color-mix(in_srgb,var(--negative)_8%,transparent)] px-3 py-2">
            <div className="mb-1 flex flex-wrap items-center gap-2 text-[12px] font-medium text-[var(--text-primary)]">
              <AlertTriangle size={14} className="text-[var(--negative)]" />
              评估拦截（硬错误）
              <Badge tone="risk">unsafe_apply</Badge>
            </div>
            <ul className="list-disc space-y-0.5 pl-4 text-[12px] text-[var(--text-secondary)]">
              {evaluation.errors.map((err, i) => <li key={i}>{err}</li>)}
            </ul>
            <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--negative)_24%,transparent)] bg-[var(--bg-secondary)] px-3 py-2">
              <div className="text-[12px] font-medium text-[var(--text-primary)]">影响范围</div>
              <p className="mt-1 text-[12px] leading-5 text-[var(--text-secondary)]">
                强制保存会把当前 JSON 写入参数文件，并让后续刷新任务使用这份配置；它不会自动下单、不会写真实账本，但可能让数据链路产物失真。
              </p>
              <label className="mt-3 flex items-start gap-2 text-[12px] leading-5 text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  checked={unsafeAcknowledged}
                  onChange={(event) => setUnsafeAcknowledged(event.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-[var(--negative)]"
                />
                我确认这是一次有意的危险操作，并已理解它会影响后续刷新结果。
              </label>
              <input
                value={unsafeConfirm}
                onChange={(event) => setUnsafeConfirm(event.target.value)}
                className="focus-ring mono mt-2 w-full rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]"
                placeholder="输入 UNSAFE_APPLY 以启用强制保存"
              />
            </div>
            <button
              type="button"
              className="focus-ring prism-btn prism-btn-danger mt-2"
              onClick={() => save(true)}
              disabled={saveParameters.isPending || !unsafeReady}
            >
              强制保存（unsafe apply）
            </button>
          </div>
        ) : null}
        {evaluation && evaluation.warnings.length > 0 ? (
          <div className="mt-3 rounded-md border border-[color-mix(in_srgb,var(--watch-color,var(--warning)_40%,transparent))] bg-[color-mix(in_srgb,var(--watch-color,var(--warning)_8%,transparent))] px-3 py-2">
            <div className="mb-1 text-[12px] font-medium text-[var(--text-primary)]">评估警告</div>
            <ul className="list-disc space-y-0.5 pl-4 text-[12px] text-[var(--text-secondary)]">
              {evaluation.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          </div>
        ) : null}
        </div>
      </details>
    </Panel>
  );
}

