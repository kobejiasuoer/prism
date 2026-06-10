import { Monitor, Moon, Sun } from "lucide-react";

import type { ThemeMode } from "@/components/theme-provider";

type ThemeOption = {
  mode: ThemeMode;
  label: string;
  title: string;
  icon: typeof Sun;
};

export const THEME_OPTIONS: ThemeOption[] = [
  { mode: "system", label: "跟随系统", title: "跟随系统外观", icon: Monitor },
  { mode: "light", label: "白天", title: "切换到白天主题", icon: Sun },
  { mode: "dark", label: "黑夜", title: "切换到黑夜主题", icon: Moon },
];

export const THEME_COPY: Record<ThemeMode, ThemeOption> = {
  system: THEME_OPTIONS[0],
  light: THEME_OPTIONS[1],
  dark: THEME_OPTIONS[2],
};

export function resolvedThemeLabel(mode: ThemeMode, resolvedTheme: string) {
  if (mode === "system") {
    return resolvedTheme === "dark" ? "系统黑夜" : "系统白天";
  }
  return THEME_COPY[mode].label;
}
