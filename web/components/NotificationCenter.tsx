"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { ar } from "@/lib/ar";
import {
  collectLiveAlerts,
  collectMarketAlerts,
  type MarketAlert,
  type NoticeType,
} from "@/lib/notifications";

const TOAST_MS = 6000;

export default function NotificationCenter() {
  const [notifications, setNotifications] = useState<MarketAlert[]>(() => collectMarketAlerts());
  const [isOpen, setIsOpen] = useState(false);
  const [latestToast, setLatestToast] = useState<MarketAlert | null>(null);
  const [mounted, setMounted] = useState(false);
  const root = useRef<HTMLDivElement | null>(null);
  const known = useRef<Set<string>>(new Set(notifications.map((item) => item.id)));
  const toasted = useRef(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const initial = collectMarketAlerts();
    known.current = new Set(initial.map((item) => item.id));
    setNotifications(initial);
    if (!toasted.current && initial[0]) {
      toasted.current = true;
      setLatestToast(initial[0]);
      const timer = window.setTimeout(() => setLatestToast(null), TOAST_MS);
      return () => window.clearTimeout(timer);
    }
    return undefined;
  }, []);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const next = await collectLiveAlerts();
      if (!alive) return;
      const newcomers = next.filter((item) => !known.current.has(item.id));
      newcomers.forEach((item) => known.current.add(item.id));
      setNotifications(next);
      if (newcomers[0]) {
        setLatestToast(newcomers[0]);
        window.setTimeout(() => setLatestToast((current) => (current?.id === newcomers[0].id ? null : current)), TOAST_MS);
      }
    };
    void load();
    const timer = window.setInterval(() => {
      void load();
    }, 2_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const close = useCallback(() => setIsOpen(false), []);

  useEffect(() => {
    if (!isOpen) return;
    const onPointer = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("mousedown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [close, isOpen]);

  const clearAll = () => {
    setNotifications([]);
    setIsOpen(false);
    setLatestToast(null);
  };

  return (
    <div className="relative" dir="rtl" ref={root}>
      {mounted ? createPortal(<AlertTicker alerts={notifications} />, document.body) : null}

      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
        aria-haspopup="menu"
        title={ar.notifyBell}
        aria-label={ar.notifyBell}
        className="relative rounded-xl border border-zinc-800 bg-zinc-950 p-2.5 text-zinc-300 shadow-md transition-all hover:bg-zinc-800"
      >
        <span aria-hidden="true">🔔</span>
        {notifications.length > 0 ? (
          <span className="absolute -top-1 -right-1 flex h-5 w-5 animate-pulse items-center justify-center rounded-full bg-rose-500 text-[10px] font-bold text-white">
            {notifications.length > 9 ? "9+" : notifications.length}
          </span>
        ) : null}
      </button>

      {isOpen ? (
        <div
          role="menu"
          className="absolute left-0 z-[70] mt-2 w-80 animate-fadeIn rounded-2xl border border-zinc-800 bg-zinc-950 p-4 text-right shadow-2xl md:w-96"
        >
          <div className="mb-3 flex items-center justify-between border-b border-zinc-800 pb-2">
            <h3 className="text-sm font-bold text-zinc-100">{ar.notifyTitle}</h3>
            <button type="button" onClick={clearAll} className="text-[11px] text-zinc-400 hover:text-sky-400">
              {ar.notifyClear}
            </button>
          </div>
          <div className="max-h-72 space-y-2.5 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="py-6 text-center text-xs text-zinc-500">{ar.notifyEmpty}</p>
            ) : (
              notifications.map((item) => (
                <div key={item.id} className="space-y-1 rounded-xl border border-zinc-800/80 bg-zinc-950/60 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-xs font-bold ${typeTone(item.type)}`}>{item.title}</span>
                    <span className="font-mono text-[10px] text-zinc-500">{item.time}</span>
                  </div>
                  <p className="text-xs leading-relaxed text-zinc-300">{item.message}</p>
                </div>
              ))
            )}
          </div>
        </div>
      ) : null}

      {mounted && latestToast
        ? createPortal(
            <div className="fixed bottom-6 left-6 z-[60] max-w-sm animate-bounce rounded-2xl border border-sky-500/40 bg-zinc-950 p-4 text-right shadow-2xl">
              <div className="flex items-start gap-3">
                <span className="text-xl" aria-hidden="true">
                  ⚡
                </span>
                <div className="min-w-0 flex-1">
                  <h4 className={`text-xs font-bold ${typeTone(latestToast.type)}`}>{latestToast.title}</h4>
                  <p className="mt-1 text-xs text-zinc-200">{latestToast.message}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setLatestToast(null)}
                  className="text-xs text-zinc-400 hover:text-zinc-200"
                  aria-label="إغلاق"
                >
                  ✕
                </button>
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

function AlertTicker({ alerts }: { alerts: MarketAlert[] }) {
  const [today, setToday] = useState("");
  useEffect(() => {
    setToday(new Date().toLocaleDateString("ar-SA"));
  }, []);
  const headline = useMemo(() => {
    if (!alerts.length) return ar.notifyEmpty;
    return alerts.map((item) => `⚡ ${item.title}: ${item.message}`).join(" • ");
  }, [alerts]);
  const loop = alerts.length ? `${headline}  •  ${headline}` : headline;

  return (
    <div
      className="group/ticker fixed inset-x-0 top-0 z-40 border-b border-zinc-800 bg-zinc-950/90 text-xs text-zinc-300"
      dir="rtl"
    >
      <div className="flex items-center justify-between gap-3 overflow-hidden px-4 py-2">
        <div className="flex shrink-0 items-center gap-2 whitespace-nowrap font-semibold text-sky-400">
          <span className="h-2 w-2 animate-ping rounded-full bg-sky-400" />
          {ar.notifyTicker}
        </div>
        <div className="min-w-0 flex-1 overflow-hidden">
          <div
            dir="ltr"
            className="w-max animate-ticker whitespace-nowrap text-zinc-200 group-hover/ticker:[animation-play-state:paused] motion-reduce:animate-none"
          >
            {loop}
          </div>
        </div>
        <div className="shrink-0 whitespace-nowrap font-mono text-[11px] text-zinc-400">{today}</div>
      </div>
    </div>
  );
}

function typeTone(type: NoticeType): string {
  if (type === "success") return "text-emerald-400";
  if (type === "alert") return "text-amber-400";
  return "text-sky-400";
}
