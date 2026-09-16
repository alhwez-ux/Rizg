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
      className={`inline-flex h-10 items-center gap-2 rounded-full border border-zinc-700 bg-zinc-950/70 px-3 text-xs font-semibold text-zinc-200 transition hover:border-amber-400 hover:text-amber-200 ${className}`}
    >
      {isDay ? <MoonIcon /> : <SunIcon />}
      <span>{label}</span>
    </button>
  );
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="3.4" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M12 3.2v1.8M12 19v1.8M4.9 4.9l1.3 1.3M17.8 17.8l1.3 1.3M3.2 12h1.8M19 12h1.8M4.9 19.1l1.3-1.3M17.8 6.2l1.3-1.3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
      <path
        d="M16.5 13.2A6.4 6.4 0 0 1 10.8 5 6.6 6.6 0 1 0 19 14.4a6.3 6.3 0 0 1-2.5-1.2z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}
