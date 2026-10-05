"use client";

import { useState, type ReactNode } from "react";

import { ar } from "@/lib/ar";
import { VISIBILITY_GROUPS, type VisibilityKey, type VisibilityMap } from "@/lib/dashboardVisibility";

export function DashboardControlPanel({
  map,
  onToggle,
  onReset,
  trailing,
}: {
  map: VisibilityMap;
  onToggle: (key: VisibilityKey) => void;
  onReset: () => void;
  trailing?: ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="w-full text-start">
      <div className="flex flex-wrap items-center justify-between gap-3">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-zinc-700 bg-zinc-950 px-4 text-sm font-bold text-zinc-100 transition hover:border-sky-400/50 hover:text-sky-100"
      >
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        {open ? ar.controlPanelClose : ar.controlPanel}
      </button>
      {trailing}
      </div>
      {open ? (
        <div className="mt-3 rounded-2xl border border-zinc-800 bg-zinc-950/80 p-4 shadow-glow">
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
      ) : null}
    </div>
  );
}
