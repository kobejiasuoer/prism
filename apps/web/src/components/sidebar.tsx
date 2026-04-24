"use client";

import {
  BarChart3,
  Circle,
  Command,
  Home,
  Search,
  Settings,
  Telescope,
  WalletCards,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useOverview } from "@/lib/hooks";
import { cn } from "@/lib/utils";

export const navItems = [
  { href: "/", label: "指挥中心", icon: Home },
  { href: "/portfolio", label: "持仓管理", icon: WalletCards },
  { href: "/discovery", label: "观察池", icon: Telescope },
  { href: "/review", label: "复盘", icon: BarChart3 },
] as const;

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
        "sticky top-0 h-screen w-[220px] shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-4",
        className,
      )}
    >
      <Link href="/" className="mb-5 block rounded-md px-3 py-2">
        <div className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">Prism</div>
        <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">棱镜 · 交易决策台</div>
      </Link>

      <button
        type="button"
        className="focus-ring mb-4 flex w-full items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-tertiary)] px-3 py-2 text-left text-[13px] text-[var(--text-tertiary)]"
        onClick={onOpenCommand}
      >
        <Search size={15} className="shrink-0 opacity-60" />
        <span className="min-w-0 flex-1 truncate">搜索股票、页面</span>
        <span className="inline-flex items-center gap-1 rounded border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-1.5 py-0.5 text-[11px]">
          <Command size={11} />K
        </span>
      </button>

      <nav className="flex flex-col gap-1">
        {navItems.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "focus-ring flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] transition-colors",
                active
                  ? "bg-[var(--bg-tertiary)] font-medium text-[var(--text-primary)]"
                  : "text-[var(--text-tertiary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-secondary)]",
              )}
            >
              <Icon size={16} className={cn("shrink-0", active ? "opacity-100" : "opacity-55")} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="mx-3 my-3 h-px bg-[var(--border-subtle)]" />

      <Link
        href="/settings"
        className={cn(
          "focus-ring flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px]",
          pathname.startsWith("/settings")
            ? "bg-[var(--bg-tertiary)] font-medium text-[var(--text-primary)]"
            : "text-[var(--text-tertiary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-secondary)]",
        )}
      >
        <Settings size={16} className="shrink-0 opacity-60" />
        设置
      </Link>

      <div className="mt-auto px-3 py-2">
        <div className="flex items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
          <Circle
            size={8}
            fill={statusOk ? "var(--positive)" : "var(--negative)"}
            className={statusOk ? "text-[var(--positive)]" : "text-[var(--negative)]"}
          />
          <span className="truncate">
            {statusOk ? "系统正常" : "后端未连接"}
            {overview.data?.generated_at ? ` · ${overview.data.generated_at.slice(11, 16)}` : ""}
          </span>
        </div>
      </div>
    </aside>
  );
}
