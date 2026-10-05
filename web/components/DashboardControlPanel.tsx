"use client";

import { useState, type ReactNode } from "react";

import { ar } from "@/lib/ar";
import { VISIBILITY_GROUPS, type VisibilityKey, type VisibilityMap } from "@/lib/dashboardVisibility";

export function DashboardControlPanel({
  map,
  onToggle,
  onReset,
  leading,
  trailing,
}: {
  map: VisibilityMap;
  onToggle: (key: VisibilityKey) => void;
  onReset: () => void;
  leading?: ReactNode;
  trailing?: ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex w-full flex-col items-center gap-2">
      <div className="flex max-w-full flex-wrap items-center justify-center gap-2">
        {leading}
        <button
          type="button"
          aria-expanded={open}
          aria-label={open ? ar.controlPanelClose : ar.controlPanel}
          title={open ? ar.controlPanelClose : ar.controlPanel}
          onClick={() => setOpen((value) => !value)}
          className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-zinc-700 bg-zinc-950 text-zinc-100 transition hover:border-sky-400/50 hover:text-sky-100"
        >
          <GearIcon />
        </button>
        {trailing}
      </div>
      {open ? (
        <div className="w-full text-start">
        <div className="rounded-2xl border border-zinc-800 bg-zinc-950/80 p-4 shadow-glow">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-zinc-400">{ar.controlPanelHint}</p>
            <button
              type="button"
              onClick={onReset}
              className="rounded-full border border-zinc-700 px-3 py-1 text-xs font-semibold text-zinc-300 hover:border-zinc-500 hover:text-zinc-100"
            >
              {ar.controlPanelReset}
            </button>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {VISIBILITY_GROUPS.map((group) => (
              <fieldset key={group.title} className="rounded-xl border border-zinc-800/80 p-3">
                <legend className="px-1 text-xs font-bold text-zinc-300">{group.title}</legend>
                <ul className="space-y-2">
                  {group.items.map((item) => {
                    const shown = map[item.key];
                    return (
                      <li key={item.key}>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={shown}
                          onClick={() => onToggle(item.key)}
                          className="flex w-full items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-sm text-zinc-200 hover:bg-zinc-900"
                        >
                          <span>{item.label}</span>
                          <span
                            className={`inline-flex min-w-14 items-center justify-center rounded-full px-2 py-0.5 text-[11px] font-bold ${
                              shown ? "bg-emerald-500/15 text-emerald-300" : "bg-zinc-800 text-zinc-500"
                            }`}
                          >
                            {shown ? ar.controlShow : ar.controlHide}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </fieldset>
            ))}
          </div>
        </div>
        </div>
      ) : null}
    </div>
  );
}

function GearIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden>
      <path
        d="M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Z"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path
        d="M19.4 13.1a7.7 7.7 0 0 0 .1-2.2l1.7-1.3-1.6-2.8-2 .6a7.8 7.8 0 0 0-1.9-1.1l-.4-2.1h-3.2l-.4 2.1a7.8 7.8 0 0 0-1.9 1.1l-2-.6-1.6 2.8 1.7 1.3a7.7 7.7 0 0 0 .1 2.2l-1.7 1.3 1.6 2.8 2-.6a7.8 7.8 0 0 0 1.9 1.1l.4 2.1h3.2l.4-2.1a7.8 7.8 0 0 0 1.9-1.1l2 .6 1.6-2.8-1.7-1.3Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}
