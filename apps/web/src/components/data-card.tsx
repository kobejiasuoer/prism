import { ArrowRight } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { Badge } from "./badge";
import type { BasicCard } from "@/lib/types";
import { cn, toneColor } from "@/lib/utils";

export function Panel({
  title,
  eyebrow,
  children,
  action,
  className,
}: {
  title: string;
  eyebrow?: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={className}>
      <div className="mb-3 flex min-w-0 items-end justify-between gap-3">
        <div className="min-w-0">
          {eyebrow ? <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">{eyebrow}</div> : null}
          <h2 className="mt-1 truncate text-lg font-semibold text-[var(--text-primary)]">{title}</h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function DataCard({ card, href }: { card: BasicCard; href?: string }) {
  const title = card.title || card.label || "未命名";
  const color = toneColor(card.tone);
  const body = (
    <div className="surface-card h-full p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          {card.subtitle ? <div className="truncate text-[11px] text-[var(--text-tertiary)]">{card.subtitle}</div> : null}
          <div className="mt-1 line-clamp-2 text-sm font-medium text-[var(--text-primary)]">{title}</div>
        </div>
        {card.status || card.action ? <Badge tone={card.tone}>{card.status || card.action}</Badge> : null}
      </div>
      {card.value !== undefined ? (
        <div className="mb-2 truncate text-2xl font-semibold" style={{ color }}>
          {String(card.value)}
        </div>
      ) : null}
      <p className="line-clamp-3 text-[12px] leading-5 text-[var(--text-secondary)]">
        {card.copy || card.detail || card.reason || card.note || card.foot || "-"}
      </p>
      {card.metrics?.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {card.metrics.slice(0, 4).map((item) => (
            <span
              key={item}
              className="mono rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 py-0.5 text-[10px] text-[var(--text-tertiary)]"
            >
              {item}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );

  if (!href) {
    return body;
  }

  return (
    <Link href={href} className="focus-ring block h-full">
      {body}
    </Link>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="surface-panel px-4 py-8 text-center text-[13px] text-[var(--text-tertiary)]">
      {children}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-md border border-[color-mix(in_srgb,var(--warning)_20%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-4 py-3 text-[13px] text-[var(--text-secondary)]">
      <div className="font-medium text-[var(--text-primary)]">{message}</div>
      {onRetry ? (
        <button
          type="button"
          className="focus-ring mt-3 rounded-md border border-[var(--border-subtle)] px-3 py-1.5 text-[12px] text-[var(--text-primary)]"
          onClick={onRetry}
        >
          重试
        </button>
      ) : null}
    </div>
  );
}

export function DetailLink({ href }: { href?: string }) {
  if (!href) {
    return null;
  }
  return (
    <Link
      href={href}
      className="focus-ring inline-flex h-8 w-8 items-center justify-center rounded-md text-[var(--text-tertiary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]"
    >
      <ArrowRight size={14} />
    </Link>
  );
}

export function SkeletonBlock({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-[var(--bg-tertiary)]", className)} />;
}
