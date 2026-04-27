import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { Providers } from "@/components/providers";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "棱镜 · 交易决策台",
  description: "Prism command center for trading decisions.",
};

const themeInitScript = `
(() => {
  const storageKey = "prism-web-theme-mode";
  const validModes = ["light", "dark", "system"];
  const root = document.documentElement;
  try {
    const stored = window.localStorage.getItem(storageKey);
    const mode = validModes.includes(stored) ? stored : "system";
    const prefersDark =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    const resolved = mode === "system" ? (prefersDark ? "dark" : "light") : mode;
    root.dataset.themeMode = mode;
    root.dataset.theme = resolved;
    root.style.colorScheme = resolved;
  } catch {
    root.dataset.themeMode = "system";
    root.dataset.theme = "light";
    root.style.colorScheme = "light";
  }
})();
`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
