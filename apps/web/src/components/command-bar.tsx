"use client";

import { Command } from "cmdk";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, BarChart3, Home, LoaderCircle, Search, Settings, Telescope, WalletCards } from "lucide-react";
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
    return pages.filter((item) => item.label.toLowerCase().includes(text) || item.href.includes(text));
  }, [query]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setSuggestions([]);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      api
        .askSuggest(query.trim())
        .then((payload) => {
          if (!controller.signal.aborted) {
            setSuggestions(payload.items?.length ? payload.items : payload.recent_queries ?? []);
          }
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setSuggestions([]);
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setLoading(false);
          }
        });
    }, 160);

    return () => {
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

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-50 flex items-start justify-center bg-black/55 px-3 pt-[12vh]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onMouseDown={() => onOpenChange(false)}
        >
          <motion.div
            className="w-full max-w-[640px] overflow-hidden rounded-lg border border-[var(--border-default)] bg-[var(--bg-elevated)]"
            initial={{ y: -12, scale: 0.98 }}
            animate={{ y: 0, scale: 1 }}
            exit={{ y: -12, scale: 0.98 }}
            transition={{ duration: 0.16 }}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <Command shouldFilter={false} className="bg-transparent">
              <div className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-4">
                <Search size={18} className="shrink-0 text-[var(--text-tertiary)]" />
                <Command.Input
                  value={query}
                  onValueChange={setQuery}
                  autoFocus
                  placeholder="搜索股票、跳转页面"
                  className="h-13 min-w-0 flex-1 bg-transparent text-[15px] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-tertiary)]"
                />
                {loading ? (
                  <LoaderCircle size={16} className="animate-spin text-[var(--text-tertiary)]" />
                ) : null}
              </div>

              <Command.List className="max-h-[420px] overflow-y-auto p-2">
                {filteredPages.length ? (
                  <Command.Group heading="页面" className="command-group">
                    {filteredPages.map((item) => {
                      const Icon = item.icon;
                      return (
                        <Command.Item
                          key={item.href}
                          value={`page:${item.href}`}
                          onSelect={() => goTo(item.href)}
                          className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2.5 text-[13px] text-[var(--text-secondary)] data-[selected=true]:bg-[var(--bg-tertiary)] data-[selected=true]:text-[var(--text-primary)]"
                        >
                          <Icon size={16} className="shrink-0" />
                          <span className="flex-1">{item.label}</span>
                          <ArrowRight size={14} className="text-[var(--text-tertiary)]" />
                        </Command.Item>
                      );
                    })}
                  </Command.Group>
                ) : null}

                {suggestions.length ? (
                  <Command.Group heading="股票" className="command-group">
                    {suggestions.map((item) => (
                      <Command.Item
                        key={`${item.code}-${item.name}`}
                        value={`stock:${item.code}:${item.name}`}
                        onSelect={() => goTo(`/stock/${encodeURIComponent(item.code)}`)}
                        className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2.5 text-[13px] text-[var(--text-secondary)] data-[selected=true]:bg-[var(--bg-tertiary)] data-[selected=true]:text-[var(--text-primary)]"
                      >
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[11px] text-[var(--text-tertiary)]">
                          股
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-[var(--text-primary)]">{item.name || item.code}</div>
                          <div className="mono truncate text-[11px] text-[var(--text-tertiary)]">
                            {item.detail || item.code}
                          </div>
                        </div>
                        {item.tag ? (
                          <span className="rounded-full border border-[var(--border-subtle)] px-2 py-0.5 text-[11px] text-[var(--text-tertiary)]">
                            {item.tag}
                          </span>
                        ) : null}
                      </Command.Item>
                    ))}
                  </Command.Group>
                ) : null}

                {!loading && !filteredPages.length && !suggestions.length ? (
                  <Command.Empty className="px-3 py-8 text-center text-[13px] text-[var(--text-tertiary)]">
                    没有匹配项
                  </Command.Empty>
                ) : null}
              </Command.List>
            </Command>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
