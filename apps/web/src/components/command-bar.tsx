"use client";

import {
  ArrowRight,
  BarChart3,
  Home,
  LoaderCircle,
  Search,
  Settings,
  Telescope,
  WalletCards,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import type { AskSuggestion } from "@/lib/types";

const pages = [
  { label: "指挥中心", href: "/", icon: Home },
  { label: "持仓管理", href: "/portfolio", icon: WalletCards },
  { label: "观察池", href: "/discovery", icon: Telescope },
  { label: "复盘", href: "/review", icon: BarChart3 },
  { label: "设置", href: "/settings", icon: Settings },
];

export function CommandBar({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<AskSuggestion[]>([]);
  const [loading, setLoading] = useState(false);

  const filteredPages = useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!text) {
      return pages;
    }
    return pages.filter(
      (item) =>
        item.label.toLowerCase().includes(text) || item.href.includes(text),
    );
  }, [query]);
  const directStockSuggestion = useMemo<AskSuggestion | null>(() => {
    const code = query.trim().replace(/\D/g, "");
    if (code.length !== 6) {
      return null;
    }
    return {
      code,
      name: code,
      tag: "直接打开",
      detail: `${code} · 个股档案`,
      url: `/stock/${code}`,
    };
  }, [query]);
  const visibleSuggestions = useMemo(() => {
    if (!directStockSuggestion) {
      return suggestions;
    }
    return [
      directStockSuggestion,
      ...suggestions.filter((item) => item.code !== directStockSuggestion.code),
    ];
  }, [directStockSuggestion, suggestions]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setSuggestions([]);
      setLoading(false);
      return;
    }

    const text = query.trim();
    const digitText = text.replace(/\D/g, "");
    const shouldFetchSuggestions = text.length >= 2 && digitText.length !== 6;
    if (!shouldFetchSuggestions) {
      setSuggestions([]);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setLoading(true);
      const timeout = window.setTimeout(() => {
        controller.abort();
      }, 3_500);
      api
        .askSuggest(text, { signal: controller.signal })
        .then((payload) => {
          if (!cancelled) {
            setSuggestions(
              payload.items?.length
                ? payload.items
                : (payload.recent_queries ?? []),
            );
          }
        })
        .catch(() => {
          if (!cancelled) {
            setSuggestions([]);
          }
        })
        .finally(() => {
          window.clearTimeout(timeout);
          if (!cancelled) {
            setLoading(false);
          }
        });
    }, 160);

    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [open, query]);

  useEffect(() => {
    if (!open) {
      return;
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        onOpenChange(false);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onOpenChange, open]);

  function goTo(path: string) {
    onOpenChange(false);
    router.push(path);
  }

  function stockPath(item: AskSuggestion) {
    const params = new URLSearchParams();
    const name = String(item.name || "").trim();
    if (name && name !== item.code) {
      params.set("name", name);
    }
    const suffix = params.toString();
    return `/stock/${encodeURIComponent(item.code)}${suffix ? `?${suffix}` : ""}`;
  }

  if (!open) {
    return null;
  }

  return (
    <div
      className="prism-command-overlay fixed inset-0 z-50 flex items-start justify-center bg-black/55 px-3 pt-[12vh]"
      onMouseDown={() => onOpenChange(false)}
    >
      <div
        className="prism-command-panel w-full max-w-[640px] overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)]"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="命令栏"
      >
        <div className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-4">
          <Search size={18} className="shrink-0 text-[var(--text-tertiary)]" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            autoFocus
            placeholder="搜索股票、跳转页面"
            className="h-13 min-w-0 flex-1 bg-transparent text-[15px] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-tertiary)]"
          />
          {loading ? (
            <LoaderCircle
              size={16}
              className="animate-spin text-[var(--text-tertiary)]"
            />
          ) : null}
        </div>

        <div className="max-h-[420px] overflow-y-auto p-2">
          {filteredPages.length ? (
            <section className="command-group">
              <div className="command-group-heading">页面</div>
              {filteredPages.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.href}
                    type="button"
                    onClick={() => goTo(item.href)}
                    className="focus-ring flex w-full cursor-pointer items-center gap-3 rounded-md px-3 py-2.5 text-left text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                  >
                    <Icon size={16} className="shrink-0" />
                    <span className="flex-1">{item.label}</span>
                    <ArrowRight
                      size={14}
                      className="text-[var(--text-tertiary)]"
                    />
                  </button>
                );
              })}
            </section>
          ) : null}

          {visibleSuggestions.length ? (
            <section className="command-group">
              <div className="command-group-heading">股票</div>
              {visibleSuggestions.map((item) => (
                <button
                  key={`${item.code}-${item.name}`}
                  type="button"
                  onClick={() => goTo(stockPath(item))}
                  className="focus-ring flex w-full cursor-pointer items-center gap-3 rounded-md px-3 py-2.5 text-left text-[13px] text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]"
                >
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[11px] text-[var(--text-tertiary)]">
                    股
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[var(--text-primary)]">
                      {item.name || item.code}
                    </div>
                    <div className="mono truncate text-[11px] text-[var(--text-tertiary)]">
                      {item.detail || item.code}
                    </div>
                  </div>
                  {item.tag ? (
                    <span className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[11px] text-[var(--text-tertiary)]">
                      {item.tag}
                    </span>
                  ) : null}
                </button>
              ))}
            </section>
          ) : null}

          {!loading && !filteredPages.length && !visibleSuggestions.length ? (
            <div className="px-3 py-8 text-center text-[13px] text-[var(--text-tertiary)]">
              没有匹配项
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
