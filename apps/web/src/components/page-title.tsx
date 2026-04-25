import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "./badge";

export function PageTitle({
  eyebrow,
  title,
  summary,
  icon: Icon,
  badge,
  actions,
}: {
  eyebrow?: string;
  title: string;
  summary?: string;
  icon: LucideIcon;
  badge?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
            <Icon size={19} />
          </div>
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              {eyebrow ? <div className="mono text-[11px] uppercase text-[var(--info)]">{eyebrow}</div> : null}
              {badge ? <Badge tone="info">{badge}</Badge> : null}
            </div>
            <h1 className="truncate text-2xl font-semibold leading-tight text-[var(--text-primary)]">{title}</h1>
            {summary ? <p className="mt-3 max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">{summary}</p> : null}
          </div>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
    </header>
  );
}
