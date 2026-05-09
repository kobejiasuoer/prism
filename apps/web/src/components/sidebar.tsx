"use client";

import {
  Circle,
  Command,
  Monitor,
  Moon,
  Search,
  Sun,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useTheme, type ThemeMode } from "@/components/theme-provider";
import { useOverview } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export const navItems = [
  { href: "/", label: "指挥中心", mark: "01" },
  { href: "/portfolio", label: "持仓管理", mark: "02" },
  { href: "/discovery", label: "发现/观察", mark: "03" },
  { href: "/review", label: "复盘", mark: "04" },
] as const;

const nextThemeMode: Record<ThemeMode, ThemeMode> = {
  system: "dark",
  dark: "light",
  light: "system",
};

const themeCopy: Record<ThemeMode, { label: string; next: string; icon: typeof Sun }> = {
  system: { label: "跟随系统", next: "黑夜", icon: Monitor },
  dark: { label: "黑夜", next: "白天", icon: Moon },
  light: { label: "白天", next: "跟随系统", icon: Sun },
};

function ThemeCycleButton() {
  const { mode, resolvedTheme, setMode } = useTheme();
  const Icon = themeCopy[mode].icon;
  const resolvedCopy = mode === "system" ? (resolvedTheme === "dark" ? "系统黑夜" : "系统白天") : themeCopy[mode].label;

  return (
    <button
      type="button"
      className="focus-ring prism-theme-cycle"
      data-mode={mode}
      title={`当前：${resolvedCopy}。切换到${themeCopy[mode].next}`}
      aria-label={`切换主题，当前是${resolvedCopy}`}
      onClick={() => setMode(nextThemeMode[mode])}
    >
      <Icon size={14} aria-hidden="true" />
    </button>
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
  const statusOk = !overview.isError;

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
        <div className="prism-status-line">
          <span>daemon</span>
          <span className={cn("flex items-center gap-1.5", statusOk ? "buy-text" : "sell-text")}>
            <Circle
              size={7}
              fill={statusOk ? "var(--positive)" : "var(--negative)"}
              className={statusOk ? "text-[var(--positive)]" : "text-[var(--negative)]"}
            />
            {statusOk ? "online" : "offline"}
          </span>
        </div>
        <div className="prism-status-line">
          <span>brief</span>
          <span className="mono">{overview.data?.generated_at?.slice(11, 16) || "-"}</span>
        </div>
        <div className="prism-status-line">
          <span>watchlist</span>
          <span className="mono watch-text">
            {overview.data?.freshness?.find((source) => source.label.includes("自选") || source.key?.includes("watch"))
              ?.age_label || "数据可用"}
          </span>
        </div>
        <div className="prism-status-footer">
          <span className="prism-status-copy">
            <Circle
              size={8}
              fill={statusOk ? "var(--positive)" : "var(--negative)"}
              className={statusOk ? "text-[var(--positive)]" : "text-[var(--negative)]"}
            />
            <span className="truncate">
              {statusOk ? "系统正常" : "后端未连接"}
              {overview.data?.generated_at ? ` · ${overview.data.generated_at.slice(11, 16)}` : ""}
            </span>
          </span>
          <ThemeCycleButton />
        </div>
      </div>
    </aside>
  );
}
