"use client";

import { CommandIcon, Search } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { Sidebar, navItems } from "./sidebar";

const CommandBar = dynamic(() => import("./command-bar").then((module) => module.CommandBar), {
  ssr: false,
  loading: () => null,
});

function warmCommandBar() {
  void import("./command-bar");
}

export function AppShell({ children }: { children: ReactNode }) {
  const [commandOpen, setCommandOpen] = useState(false);
  const [sidebarStatusEnabled, setSidebarStatusEnabled] = useState(false);
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
    if (typeof window.matchMedia !== "function") {
      return undefined;
    }

    const mediaQuery = window.matchMedia("(min-width: 768px)");
    const syncSidebarStatus = () => setSidebarStatusEnabled(mediaQuery.matches);
    syncSidebarStatus();

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", syncSidebarStatus);
      return () => mediaQuery.removeEventListener("change", syncSidebarStatus);
    }

    mediaQuery.addListener(syncSidebarStatus);
    return () => mediaQuery.removeListener(syncSidebarStatus);
  }, []);

  return (
    <div className="prism-app-shell" data-od-id="app-shell">
      <div className="prism-layout">
        <Sidebar
          onOpenCommand={() => setCommandOpen(true)}
          onWarmCommand={warmCommandBar}
          statusEnabled={sidebarStatusEnabled}
          className="hidden md:flex"
        />
        <div className="prism-content">
          <header className="prism-mobile-shell md:hidden">
            <div className="prism-mobile-top">
              <Link href="/" className="prism-mobile-brand min-w-0">
                <small>PRISM / A-SHARE DESK</small>
                <strong>棱镜 Prism</strong>
              </Link>
              <button
                type="button"
                aria-label="打开命令栏"
                className="focus-ring od-ghost-btn"
                onClick={() => setCommandOpen(true)}
                onFocus={warmCommandBar}
                onMouseEnter={warmCommandBar}
              >
                <Search size={15} />
                <CommandIcon size={13} />
              </button>
            </div>
            <nav className="prism-mobile-nav" aria-label="主导航">
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
              <Link
                href="/settings"
                className="focus-ring prism-nav-link"
                data-active={pathname.startsWith("/settings")}
              >
                <span className="prism-nav-mark">05</span>
                <span className="prism-nav-label">设置</span>
              </Link>
            </nav>
          </header>

          {children}
        </div>
      </div>
      {commandOpen ? <CommandBar open={commandOpen} onOpenChange={setCommandOpen} /> : null}
    </div>
  );
}
