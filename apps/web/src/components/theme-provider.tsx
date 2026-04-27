"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ThemeMode = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const THEME_STORAGE_KEY = "prism-web-theme-mode";
const THEME_MODES: ThemeMode[] = ["light", "dark", "system"];

type ThemeContextValue = {
  mode: ThemeMode;
  resolvedTheme: ResolvedTheme;
  setMode: (mode: ThemeMode) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function normalizeThemeMode(value: unknown): ThemeMode {
  return typeof value === "string" && THEME_MODES.includes(value as ThemeMode) ? (value as ThemeMode) : "system";
}

function systemTheme(): ResolvedTheme {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return "light";
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function resolveTheme(mode: ThemeMode): ResolvedTheme {
  return mode === "system" ? systemTheme() : mode;
}

function readStoredMode(): ThemeMode {
  try {
    return normalizeThemeMode(window.localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return "system";
  }
}

function writeStoredMode(mode: ThemeMode) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    return;
  }
}

function applyTheme(mode: ThemeMode): ResolvedTheme {
  const resolvedTheme = resolveTheme(mode);
  const root = document.documentElement;
  root.dataset.themeMode = mode;
  root.dataset.theme = resolvedTheme;
  root.style.colorScheme = resolvedTheme;
  return resolvedTheme;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>("system");
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("light");

  useEffect(() => {
    const initialMode = readStoredMode();
    setModeState(initialMode);
    setResolvedTheme(applyTheme(initialMode));
  }, []);

  useEffect(() => {
    if (mode !== "system" || typeof window.matchMedia !== "function") {
      return undefined;
    }

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleSystemThemeChange = () => {
      setResolvedTheme(applyTheme("system"));
    };

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", handleSystemThemeChange);
      return () => mediaQuery.removeEventListener("change", handleSystemThemeChange);
    }

    mediaQuery.addListener(handleSystemThemeChange);
    return () => mediaQuery.removeListener(handleSystemThemeChange);
  }, [mode]);

  const setMode = useCallback((nextMode: ThemeMode) => {
    const normalizedMode = normalizeThemeMode(nextMode);
    setModeState(normalizedMode);
    writeStoredMode(normalizedMode);
    setResolvedTheme(applyTheme(normalizedMode));
  }, []);

  const value = useMemo(
    () => ({
      mode,
      resolvedTheme,
      setMode,
    }),
    [mode, resolvedTheme, setMode],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return context;
}
