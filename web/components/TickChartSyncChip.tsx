"use client";

import { useEffect, useRef, useState } from "react";

import { ar } from "@/lib/ar";
import { resolveListedCompany, searchListedCompanies, type ListedCompany } from "@/lib/listedCompanies";
import {
  fetchTickChartStatus,
  followTickChartSymbol,
  refreshTickChartLive,
  uploadTickChartFile,
  type TickChartStatus,
} from "@/lib/tickchartStatus";

export function TickChartSyncChip({
  onFollow,
}: {
  onFollow?: (company: { symbol: string; name: string }) => void;
}) {
  const [status, setStatus] = useState<TickChartStatus | null>(null);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<ListedCompany[]>([]);
  const [busy, setBusy] = useState<"follow" | "refresh" | "upload" | null>(null);
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      const next = await fetchTickChartStatus();
      if (alive) {
        setStatus(next);
        if (next?.last_sync_at) setLastSyncAt(next.last_sync_at);
      }
    };
    const bootstrap = async () => {
      try {
        const pulled = await refreshTickChartLive();
        if (!alive) return;
        const next = await fetchTickChartStatus();
        setStatus(next);
        if (pulled.last_sync_at || next?.last_sync_at) {
          setLastSyncAt(pulled.last_sync_at || next?.last_sync_at || null);
        }
        if (pulled.count > 0) {
          setMessage(`${ar.tickchartRefreshed} (${pulled.count})`);
        }
      } catch (err) {
        if (alive) {
          setMessage(err instanceof Error ? err.message : ar.tickchartRefreshError);
          await load();
        }
      }
    };
    void bootstrap();
    const timer = window.setInterval(() => {
      void load();
    }, 2_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  const live = Boolean(status?.connected || status?.trades_live || status?.depth_live || status?.quote_mode === "live");
  const local = Boolean(status?.autosync_watching);
  const lastClose = !live && (status?.quote_mode === "last_close" || Number(status?.last_quotes || 0) > 0);
  const label = live
    ? ar.tickchartSyncLive
    : local
      ? ar.tickchartSyncLocal
      : lastClose
        ? ar.tickchartSyncLastClose
        : ar.tickchartSyncIdle;

  const follow = async (picked?: ListedCompany) => {
    const raw = picked?.symbol || query.trim();
    if (!raw) return;
    const local = picked || resolveListedCompany(raw);
    const matches = local ? [local] : searchListedCompanies(raw, 5);
    if (!local && matches.length > 1) {
      setSuggestions(matches);
      setMessage(ar.tickchartFollowAmbiguous);
      return;
    }
    const ticker = local?.symbol || raw;
    setBusy("follow");
    setMessage(null);
    try {
      const result = await followTickChartSymbol(ticker);
      const name = result.name && result.name !== result.symbol ? result.name : local?.name || result.symbol;
      setQuery("");
      setSuggestions([]);
      onFollow?.({ symbol: result.symbol, name });
      setMessage(`${ar.tickchartFollowed} ${name} (${result.symbol})`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : ar.tickchartFollowError);
    } finally {
      setBusy(null);
    }
  };

  const refresh = async () => {
    setBusy("refresh");
    setMessage(null);
    try {
      const pulled = await refreshTickChartLive();
      const next = await fetchTickChartStatus();
      setStatus(next);
      setLastSyncAt(pulled.last_sync_at || next?.last_sync_at || new Date().toISOString());
      setMessage(pulled.count > 0 ? `${ar.tickchartRefreshed} (${pulled.count})` : ar.tickchartRefreshed);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : ar.tickchartRefreshError);
    } finally {
      setBusy(null);
    }
  };

  const upload = async (file: File) => {
    setBusy("upload");
    setMessage(null);
    try {
      const ingested = await uploadTickChartFile(file);
      setMessage(`${ar.tickchartUploaded} ${ingested}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : ar.tickchartUploadError);
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="flex w-full flex-col gap-3 rounded-2xl border border-zinc-800/80 bg-zinc-950/60 p-3 sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div
          className={`inline-flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-semibold ${
            live
              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
              : local
                ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
                : lastClose
                ? "border-sky-500/20 bg-sky-500/10 text-sky-300"
                : "border-zinc-700 bg-zinc-900 text-zinc-400"
          }`}
          title={ar.tickchartSyncHint}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              live || local ? "animate-pulse bg-emerald-400" : lastClose ? "bg-sky-400" : "bg-zinc-500"
            }`}
          />
          {label}
        </div>
      </div>

      <div className="relative flex flex-col gap-2 sm:flex-row">
        <div className="relative min-w-0 flex-1">
          <input
            value={query}
            onChange={(event) => {
              const next = event.target.value;
              setQuery(next);
              setSuggestions(searchListedCompanies(next, 6));
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void follow();
              }
              if (event.key === "Escape") setSuggestions([]);
            }}
            maxLength={80}
            placeholder={ar.tickchartSymbolPlaceholder}
            className="min-h-11 w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 text-sm text-zinc-100 outline-none ring-sky-500/40 placeholder:text-zinc-500 focus:ring-2"
            aria-label={ar.tickchartSymbolPlaceholder}
            autoComplete="off"
          />
          {suggestions.length ? (
            <ul className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-xl border border-zinc-800 bg-zinc-950 py-1 shadow-lg">
              {suggestions.map((item) => (
                <li key={item.symbol}>
                  <button
                    type="button"
                    onClick={() => void follow(item)}
                    className="flex w-full items-center justify-between gap-3 px-3 py-2 text-start text-sm text-zinc-200 hover:bg-sky-500/15"
                  >
                    <span>{item.name}</span>
                    <span className="font-mono text-xs text-zinc-500" dir="ltr">
                      {item.symbol}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <button
          type="button"
          onClick={() => void follow()}
          disabled={busy !== null || !query.trim()}
          className="min-h-11 rounded-xl bg-sky-600 px-4 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:opacity-50"
        >
          {busy === "follow" ? ar.tickchartFollowing : ar.tickchartFollow}
        </button>
        <label className="flex min-h-11 cursor-pointer items-center justify-center rounded-xl border border-zinc-700 px-4 text-sm font-semibold text-zinc-300 transition hover:border-emerald-500 hover:text-emerald-300">
          {busy === "upload" ? ar.tickchartUploading : ar.tickchartUpload}
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.json,.txt,.tsv,text/csv,application/json"
            className="hidden"
            onChange={(event) => {
              const next = event.target.files?.[0];
              if (next) void upload(next);
            }}
          />
        </label>
        <div className="flex min-w-[9.5rem] flex-col items-stretch">
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={busy !== null}
            className="min-h-11 rounded-xl border border-sky-500/40 bg-sky-500/15 px-4 text-sm font-semibold text-sky-200 transition hover:bg-sky-500/25 disabled:opacity-50"
          >
            {busy === "refresh" ? ar.tickchartRefreshing : ar.tickchartRefresh}
          </button>
          <p className="mt-1 text-center text-[11px] leading-4 text-zinc-500">
            {ar.tickchartLastSync}
            <span dir="ltr" className="mt-0.5 block font-mono text-zinc-400">
              {formatSyncTime(lastSyncAt || status?.last_sync_at)}
            </span>
          </p>
        </div>
      </div>
      {message ? <p className="text-xs text-zinc-400">{message}</p> : null}
    </div>
  );
}

export default TickChartSyncChip;

function formatSyncTime(value: string | null | undefined): string {
  if (!value) return ar.tickchartLastSyncNever;
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) return ar.tickchartLastSyncNever;
  return stamp.toLocaleString("ar-SA", {
    timeZone: "Asia/Riyadh",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    day: "numeric",
    month: "short",
    hour12: true,
    numberingSystem: "latn",
  });
}
