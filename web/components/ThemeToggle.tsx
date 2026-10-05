"use client";

import { ar } from "@/lib/ar";
import { useTheme } from "@/hooks/useTheme";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { isDay, toggleTheme } = useTheme();
  const label = isDay ? ar.themeNight : ar.themeDay;

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-pressed={isDay}
      aria-label={label}
      title={label}
      suppressHydrationWarning
      className={`inline-flex h-11 w-11 items-center justify-center rounded-full border border-amber-400/50 bg-zinc-950 text-amber-200 transition hover:border-amber-300 hover:text-amber-100 ${className}`}
    >
      <Crescent filled={!isDay} />
    </button>
  );
}

function Crescent({ filled }: { filled: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" aria-hidden>
      <path
        d="M15.8 14.6A6.2 6.2 0 0 1 9.2 4.6 7.2 7.2 0 1 0 19.4 16a6.1 6.1 0 0 1-3.6-1.4z"
        fill={filled ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}
