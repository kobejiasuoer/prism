"use client";

import { CommandIcon, Menu, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { CommandBar } from "./command-bar";
import { Sidebar, navItems } from "./sidebar";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";

export function AppShell({ children }: { children: ReactNode }) {
  const [commandOpen, setCommandOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen((value) => !value);
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [pathname]);

  return (
    <div className="min-h-screen bg-[var(--bg-primary)] text-[var(--text-primary)]">
      <div className="flex min-h-screen">
        <Sidebar onOpenCommand={() => setCommandOpen(true)} className="hidden md:flex" />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)]/95 px-3 md:hidden">
            <button
              type="button"
              aria-label="打开导航"
              className="focus-ring inline-flex h-9 w-9 items-center justify-center rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]"
              onClick={() => setMobileNavOpen((value) => !value)}
            >
              {mobileNavOpen ? <X size={17} /> : <Menu size={17} />}
            </button>
            <Link href="/" className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">棱镜 · 交易决策台</div>
            </Link>
            <button
              type="button"
              aria-label="打开命令栏"
              className="focus-ring inline-flex h-9 items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 text-[var(--text-secondary)]"
              onClick={() => setCommandOpen(true)}
            >
              <Search size={15} />
              <CommandIcon size={13} />
            </button>
          </header>

          {mobileNavOpen ? (
            <nav className="grid grid-cols-2 gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-3 md:hidden">
              {navItems.map((item) => {
                const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-2 rounded-md border px-3 py-2 text-sm",
                      active
                        ? "border-[var(--border-default)] bg-[var(--bg-tertiary)] text-[var(--text-primary)]"
                        : "border-[var(--border-subtle)] text-[var(--text-secondary)]",
                    )}
                  >
                    <Icon size={16} />
                    {item.label}
                  </Link>
                );
              })}
              <ThemeToggle className="col-span-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-2" />
            </nav>
          ) : null}

          {children}
        </div>
      </div>
      <CommandBar open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
  );
}
