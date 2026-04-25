import type { ReactNode } from "react";

import type { Tone } from "@/lib/types";
import { cn, toneColor } from "@/lib/utils";

export function Badge({
  children,
  tone = "info",
  className,
}: {
  children: ReactNode;
  tone?: Tone | string;
  className?: string;
}) {
  const color = toneColor(tone);

  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium leading-5",
        className,
      )}
      style={{
        color,
        backgroundColor: `color-mix(in srgb, ${color} 10%, transparent)`,
        borderColor: `color-mix(in srgb, ${color} 20%, transparent)`,
      }}
    >
      <span className="truncate">{children}</span>
    </span>
  );
}
