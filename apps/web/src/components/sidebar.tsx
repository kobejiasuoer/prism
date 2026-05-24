"use client";

import {
  ChevronDown,
  Circle,
  Command,
  Monitor,
  Moon,
  Search,
  Sun,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useTheme, type ThemeMode } from "@/components/theme-provider";
import { TrustBanner } from "@/components/trust-banner";
import { useOverview, useTodayData } from "@/lib/hooks";
import { cn, toneColor } from "@/lib/utils";

export const navItems = [
  { href: "/", label: "指挥中心", mark: "01" },
  { href: "/portfolio", label: "持仓管理", mark: "02" },
  { href: "/discovery", label: "发现/观察", mark: "03" },
  { href: "/review", label: "复盘", mark: "04" },
] as const;

const themeOptions: Array<{ mode: ThemeMode; label: string; icon: typeof Sun }> = [
  { mode: "system", label: "跟随系统", icon: Monitor },
  { mode: "light", label: "白天", icon: Sun },
  { mode: "dark", label: "黑夜", icon: Moon },
];

const themeCopy: Record<ThemeMode, { label: string; icon: typeof Sun }> = {
  system: { label: "跟随系统", icon: Monitor },
  dark: { label: "黑夜", icon: Moon },
  light: { label: "白天", icon: Sun },
};

function ThemeSelectButton() {
  const { mode, resolvedTheme, setMode } = useTheme();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const Icon = themeCopy[mode].icon;
  const resolvedCopy = mode === "system" ? (resolvedTheme === "dark" ? "系统黑夜" : "系统白天") : themeCopy[mode].label;

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    function handlePointerDown(event: PointerEvent) {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div className="prism-theme-select" ref={menuRef}>
      <button
        type="button"
        className="focus-ring prism-theme-cycle"
        data-mode={mode}
        aria-haspopup="menu"
        aria-expanded={open}
        title={`主题：${resolvedCopy}`}
        aria-label={`选择主题，当前是${resolvedCopy}`}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon size={14} aria-hidden="true" />
        <ChevronDown size={12} aria-hidden="true" />
      </button>
      {open ? (
        <div className="prism-theme-menu" role="menu" aria-label="主题选择">
          {themeOptions.map((option) => {
            const OptionIcon = option.icon;
            const active = option.mode === mode;
            return (
              <button
                key={option.mode}
                type="button"
                className="focus-ring prism-theme-menu-item"
                data-active={active}
                role="menuitemradio"
                aria-checked={active}
                onClick={() => {
                  setMode(option.mode);
                  setOpen(false);
                }}
              >
                <OptionIcon size={14} aria-hidden="true" />
                <span>{option.label}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export function Sidebar({
  onOpenCommand,
  className,
}: {
  onOpenCommand: () => void;
  className?: string;
}) {
  const pathname = usePathname();
  const overview = useOverview();
  const today = useTodayData();
  const daemonOk = !overview.isError;
  const readiness = today.data?.readiness;
  const trust = readiness?.trust_level;
  const trustTone = trust?.tone || "warning";
  const trustColor = toneColor(trustTone);
  const watchlistSource =
    readiness?.source_freshness?.find((source) => source.key === "watchlist")
    || overview.data?.freshness?.find((source) => source.label.includes("自选") || source.key?.includes("watch"));
  const watchlistBlocked = readiness?.readiness_mode === "blocked" || Boolean(watchlistSource?.stale);
  const watchlistLabel = watchlistSource?.age_label || (watchlistBlocked ? "不可用" : "待同步");

  return (
    <aside
      className={cn(
        "prism-sidebar shrink-0",
        className,
      )}
      data-od-id="sidebar"
    >
      <Link href="/" className="prism-brand">
        <small>PRISM / A-SHARE DESK</small>
        <strong>棱镜 Prism</strong>
        <small>交易决策台</small>
      </Link>

      <button
        type="button"
        className="focus-ring prism-command-button"
        onClick={onOpenCommand}
      >
        <span className="flex min-w-0 items-center gap-2">
          <Search size={15} className="shrink-0 opacity-60" />
          <span className="truncate">搜索股票 / 页面</span>
        </span>
        <span className="prism-kbd">
          <Command size={11} />K
        </span>
      </button>

      <nav className="prism-nav" aria-label="主导航">
        {navItems.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className="focus-ring prism-nav-link"
              data-active={active}
            >
              <span className="prism-nav-mark">{item.mark}</span>
              <span className="prism-nav-label">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <Link
        href="/settings"
        className="focus-ring prism-nav-link mt-1"
        data-active={pathname.startsWith("/settings")}
      >
        <span className="prism-nav-mark">05</span>
        <span className="prism-nav-label">设置</span>
      </Link>

      <div className="prism-side-status">
        {trust ? (
          <Link
            href="/settings#recovery"
            className="focus-ring -mx-1 mb-1 flex flex-col gap-1 rounded-md border px-2 py-1.5 text-left no-underline"
            style={{
              borderColor: `color-mix(in srgb, ${trustColor} 24%, transparent)`,
              backgroundColor: `color-mix(in srgb, ${trustColor} 6%, transparent)`,
            }}
            title={trust.headline}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="text-[10px] uppercase tracking-wide text-[var(--text-tertiary)]">今日可信度</span>
              <TrustBanner trust={trust} compact />
            </span>
            <span className="line-clamp-2 text-[11px] leading-4 text-[var(--text-secondary)]">
              {trust.headline}
            </span>
            {trust.next_step_label && trust.level !== "trusted" ? (
              <span className="text-[10px] text-[var(--text-tertiary)]">下一步：{trust.next_step_label}</span>
            ) : null}
          </Link>
        ) : null}
        <div className="prism-status-line">
          <span>daemon</span>
          <span className={cn("flex items-center gap-1.5", daemonOk ? "buy-text" : "sell-text")}>
            <Circle
              size={7}
              fill={daemonOk ? "var(--positive)" : "var(--negative)"}
              className={daemonOk ? "text-[var(--positive)]" : "text-[var(--negative)]"}
            />
            {daemonOk ? "已连接" : "未连接"}
          </span>
        </div>
        <div className="prism-status-line">
          <span>brief</span>
          <span className="mono">{overview.data?.generated_at?.slice(11, 16) || "-"}</span>
        </div>
        <div className="prism-status-line">
          <span>watchlist</span>
          <span className={cn("mono", watchlistBlocked ? "sell-text" : "watch-text")}>
            {watchlistBlocked ? `stale · ${watchlistLabel}` : watchlistLabel}
          </span>
        </div>
        <div className="prism-status-footer">
          <span className="prism-status-copy">
            <Circle
              size={8}
              fill={daemonOk ? "var(--positive)" : "var(--negative)"}
              className={daemonOk ? "text-[var(--positive)]" : "text-[var(--negative)]"}
            />
            <span className="truncate">
              {daemonOk ? "后端已连接" : "后端未连接"}
              {overview.data?.generated_at ? ` · ${overview.data.generated_at.slice(11, 16)}` : ""}
            </span>
          </span>
          <ThemeSelectButton />
        </div>
      </div>
    </aside>
  );
}
