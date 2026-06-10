"use client";

import { ChevronDown, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState, type ComponentType } from "react";

import type { ReadinessPayload, TrustLevel } from "@/lib/types";
import { cn, toneColor } from "@/lib/utils";
import { TrustCompactBadge, trustLevelTone } from "./trust-compact-badge";

interface DeferredTrustBannerProps {
  trust?: TrustLevel | null;
  readiness?: ReadinessPayload | null;
  recoveryHref?: string;
  className?: string;
  compact?: boolean;
}

type TrustBannerComponent = ComponentType<DeferredTrustBannerProps>;

let cachedTrustBanner: TrustBannerComponent | null = null;
let trustBannerPromise: Promise<TrustBannerComponent> | null = null;

function loadTrustBanner() {
  if (cachedTrustBanner) {
    return Promise.resolve(cachedTrustBanner);
  }
  trustBannerPromise ??= import("./trust-banner").then((module) => {
    cachedTrustBanner = module.TrustBanner as TrustBannerComponent;
    return cachedTrustBanner;
  });
  return trustBannerPromise;
}

function DeferredTrustFallback({
  trust,
  className,
  loadingFull,
  onExpand,
}: {
  trust?: TrustLevel | null;
  className?: string;
  loadingFull?: boolean;
  onExpand?: () => void;
}) {
  if (!trust) {
    return null;
  }
  const color = toneColor(trustLevelTone(trust));
  const blockingReason = trust.blocking_reasons?.[0];

  return (
    <section
      className={cn("surface-card flex flex-col gap-2 p-4", className)}
      style={{
        borderColor: `color-mix(in srgb, ${color} 28%, transparent)`,
        backgroundColor: `color-mix(in srgb, ${color} 6%, transparent)`,
      }}
      role="status"
      aria-live="polite"
      data-trust-level={trust.level}
    >
      <div className="flex flex-wrap items-center gap-2">
        <TrustCompactBadge trust={trust} />
        <span className="text-[11px] text-[var(--text-tertiary)]">
          真钱执行：{trust.can_trade_live ? "可" : "暂不可"}
        </span>
      </div>
      <h2 className="text-[14px] font-semibold leading-5 text-[var(--text-primary)]">
        {trust.headline}
      </h2>
      {blockingReason ? (
        <div className="text-[12px] leading-5 text-[var(--text-secondary)]">
          {blockingReason}
        </div>
      ) : null}
      {onExpand ? (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="focus-ring inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--border-subtle)] px-2.5 text-[11px] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] disabled:cursor-not-allowed disabled:opacity-60"
            onClick={onExpand}
            disabled={loadingFull}
          >
            {loadingFull ? (
              <LoaderCircle size={12} className="animate-spin" />
            ) : (
              <ChevronDown size={12} />
            )}
            {loadingFull ? "加载中" : "展开细节"}
          </button>
          {trust.next_step_label ? (
            <span className="text-[11px] text-[var(--text-tertiary)]">
              下一步：{trust.next_step_label}
            </span>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export function DeferredTrustBanner(props: DeferredTrustBannerProps) {
  const { trust, className, compact } = props;
  const mounted = useRef(true);
  const [TrustBanner, setTrustBanner] = useState<TrustBannerComponent | null>(
    () => cachedTrustBanner,
  );
  const [loadingFull, setLoadingFull] = useState(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  function expandTrustBanner() {
    if (TrustBanner || loadingFull) {
      return;
    }
    if (cachedTrustBanner) {
      setTrustBanner(() => cachedTrustBanner);
      return;
    }
    setLoadingFull(true);
    void loadTrustBanner()
      .then((component) => {
        if (mounted.current) {
          setTrustBanner(() => component);
        }
      })
      .finally(() => {
        if (mounted.current) {
          setLoadingFull(false);
        }
      });
  }

  if (!trust) {
    return null;
  }
  if (compact) {
    return <TrustCompactBadge trust={trust} className={className} />;
  }
  if (TrustBanner) {
    return <TrustBanner {...props} />;
  }
  return (
    <DeferredTrustFallback
      trust={trust}
      className={className}
      loadingFull={loadingFull}
      onExpand={expandTrustBanner}
    />
  );
}
