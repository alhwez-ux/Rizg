"use client";

import { FormEvent, memo, useEffect, useMemo, useRef, useState } from "react";

import { AnimatedNumber } from "@/components/AnimatedNumber";
import { AuthControls } from "@/components/AuthControls";
import { RizgLogo } from "@/components/RizgLogo";
import { SignalBadge, SuggestedPrices } from "@/components/SignalBadge";
import { SignalToasts, type SignalToastItem } from "@/components/SignalToasts";
import { StockRadarTable } from "@/components/StockRadarTable";
import { StockSignalCard } from "@/components/StockSignalCard";
import { useLiquiditySocket } from "@/hooks/useLiquiditySocket";
import { useScreener } from "@/hooks/useScreener";
import { useStockRadar } from "@/hooks/useStockRadar";
import { ar } from "@/lib/ar";
import { isAudioUnlocked, playSignalSound, unlockAudio } from "@/lib/audio";
import { wsUrlFor } from "@/lib/api";
import {
  DEFAULT_SYMBOL,
  formatClock,
  formatCount,
  formatMoney,
  formatPercent,
  formatPrice,
  formatVolume,
  regimeFromNetFlow,
  type ConnectionStatus,
  type LiquidityAlertEvent,
  type LiquidityTick,
  type TapeRegime,
} from "@/lib/liquidity";
import { signalKey } from "@/lib/screener";

const STATUS_COPY: Record<ConnectionStatus, string> = {
  connecting: ar.connecting,
  live: ar.connected,
  reconnecting: ar.reconnecting,
  offline: ar.offline,
};

const REGIME_COPY: Record<TapeRegime, string> = {
  accumulation: ar.accumulation,
  distribution: ar.distribution,
  neutral: ar.neutral,
};

export function LiquidityDashboard({
  symbol = DEFAULT_SYMBOL,
}: {
  symbol?: string;
}) {
  const { snapshot, error, adding, addSymbol, removeSymbol } = useScreener();
  const {
    rows: tableRows,
    prohibitedSymbols,
    loading: radarTableLoading,
    error: radarError,
    configured,
    refresh: refreshRadar,
  } = useStockRadar();
  const [selected, setSelected] = useState(symbol);
  const [draft, setDraft] = useState("");
  const [muted, setMuted] = useState(false);
  const [soundArmed, setSoundArmed] = useState(false);
  const [toasts, setToasts] = useState<SignalToastItem[]>([]);
  const [complianceError, setComplianceError] = useState<string | null>(null);
  const seenSignals = useRef<Set<string>>(new Set());
  const primed = useRef(false);

  const wsUrl = wsUrlFor(selected);
  const { tick, sparkline, alerts, status, attempts } = useLiquiditySocket(wsUrl);
  const liveTick = tick?.symbol === selected ? tick : null;
  const regime = regimeFromNetFlow(liveTick?.netFlow ?? 0);
  const radarRows = useMemo(() => {
    const rows = snapshot?.radar ?? [];
    if (!configured || radarError || radarTableLoading) return rows;
    return rows.filter((row) => !prohibitedSymbols.has(row.symbol));
  }, [configured, prohibitedSymbols, radarError, radarTableLoading, snapshot?.radar]);

  const watchlistRows = useMemo(() => {
    const rows = snapshot?.watchlist ?? [];
    if (!configured || radarError || radarTableLoading) return rows;
    return rows.filter((row) => !prohibitedSymbols.has(row.symbol));
  }, [configured, prohibitedSymbols, radarError, radarTableLoading, snapshot?.watchlist]);

  const selectedRow =
    watchlistRows.find((row) => row.symbol === selected) ??
    radarRows.find((row) => row.symbol === selected) ??
    null;

  useEffect(() => {
    if (!prohibitedSymbols.has(selected)) return;
    const next =
      watchlistRows[0]?.symbol ?? radarRows[0]?.symbol ?? tableRows[0]?.symbol;
    if (next && next !== selected) setSelected(next);
  }, [prohibitedSymbols, radarRows, selected, tableRows, watchlistRows]);

  useEffect(() => {
    try {
      setMuted(window.localStorage.getItem("rizg-sound-muted") === "1");
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (!snapshot) return;
    const rows = [...watchlistRows, ...radarRows];
    const next: SignalToastItem[] = [];
    for (const row of rows) {
      if (!row.entry_signal && !row.exit_signal) continue;
      const key = signalKey(row);
      if (seenSignals.current.has(key)) continue;
      seenSignals.current.add(key);
      if (primed.current) {
        next.push({ id: `${key}-${Date.now()}`, row });
      }
    }
    primed.current = true;
    if (next.length === 0) return;
    setToasts((current) => [...next, ...current].slice(0, 3));
    if (!muted) {
      const kind = next[0].row.entry_signal ? "entry" : "exit";
      playSignalSound(kind);
    }
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      for (const toast of next) {
        const title = toast.row.entry_signal ? ar.entryBadge : ar.exitBadge;
        const price = toast.row.entry_signal ? toast.row.suggested_entry : toast.row.suggested_exit;
        const priceLabel = toast.row.entry_signal ? ar.entryPriceLabel : ar.exitPriceLabel;
        new Notification(`${title} ${toast.row.symbol}`, {
          body: price != null ? `${priceLabel}: ${price}` : toast.row.reasons[0],
          tag: toast.id,
          icon: "/icons/icon-192.png",
          badge: "/icons/icon-32.png",
        });
      }
    }
  }, [muted, radarRows, snapshot, watchlistRows]);

  const toggleMute = () => {
    setMuted((current) => {
      const next = !current;
      try {
        window.localStorage.setItem("rizg-sound-muted", next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
    void unlockAudio().then((ok) => setSoundArmed(ok));
  };

  const onAdd = async (event: FormEvent) => {
    event.preventDefault();
    const value = draft.trim();
    if (!value) return;
    const normalized = value.replace(/\D/g, "") || value;
    if (prohibitedSymbols.has(normalized)) {
      setComplianceError(ar.prohibitedBlocked);
      return;
    }
    try {
      setComplianceError(null);
      await addSymbol(value);
      setSelected(normalized);
      setDraft("");
    } catch {
      /* error banner from hook */
    }
  };

  const pulse = snapshot?.pulse;
  const screenerRows = useMemo(
    () =>
      [...watchlistRows, ...radarRows].filter(
        (row, index, rows) => rows.findIndex((item) => item.symbol === row.symbol) === index,
      ),
    [radarRows, watchlistRows],
  );

  return (
    <section className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-4 py-6 sm:px-6 lg:px-8">
      <SignalToasts toasts={toasts} onDismiss={(id) => setToasts((items) => items.filter((item) => item.id !== id))} />

      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <RizgLogo iconClassName="h-12 w-12 sm:h-14 sm:w-14" />
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-zinc-50 sm:text-4xl">{ar.title}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-500">{ar.subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <AuthControls />
          <ConnectionBadge status={status} attempts={attempts} />
          <button
            type="button"
            onClick={() => {
              void (async () => {
                if (!soundArmed) {
                  setSoundArmed(await unlockAudio());
                  return;
                }
                toggleMute();
              })();
            }}
            className="rounded-full border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-emerald-500"
          >
            {muted ? ar.soundOff : soundArmed || isAudioUnlocked() ? ar.soundOn : ar.enableSound}
          </button>
        </div>
      </header>

      {pulse ? (
        <div className="grid gap-3 rounded-2xl border border-zinc-800/80 bg-tape-panel/80 px-4 py-3 sm:grid-cols-4">
          <PulseStat label={pulse.index} value={pulse.index_value?.toString() ?? "—"} />
          <PulseStat
            label={ar.scanned}
            value={formatCount(snapshot?.scanned ?? 0)}
          />
          <PulseStat label={ar.advancing} value={formatCount(pulse.advancing ?? 0)} />
          <PulseStat
            label={snapshot?.delayed ? ar.delayed : ar.liveData}
            value={formatPercent(pulse.index_change_percent)}
          />
        </div>
      ) : null}

      {(error || complianceError) ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-sm text-rose-200">
          {complianceError ?? error}
        </p>
      ) : null}

      <StockRadarTable
        rows={tableRows}
        loading={radarTableLoading}
        error={radarError}
        onRetry={() => {
          void refreshRadar();
        }}
        selectedSymbol={selected}
        onSelect={setSelected}
        screenerRows={screenerRows}
      />

      <div className="grid gap-4 lg:grid-cols-12">
        <section className="lg:col-span-7">
          <div className="mb-3">
            <h2 className="text-lg font-semibold text-zinc-100">{ar.radarTitle}</h2>
            <p className="mt-1 text-xs text-zinc-500">{ar.radarHintCompliant}</p>
          </div>
          {radarRows.length ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {radarRows.map((row) => (
                <StockSignalCard
                  key={row.symbol}
                  row={row}
                  selected={row.symbol === selected}
                  onSelect={setSelected}
                />
              ))}
            </div>
          ) : (
            <p className="rounded-2xl border border-dashed border-zinc-800 px-4 py-10 text-center text-sm text-zinc-500">
              {ar.radarEmpty}
            </p>
          )}
        </section>

        <section className="lg:col-span-5">
          <div className="mb-3">
            <h2 className="text-lg font-semibold text-zinc-100">{ar.watchlistTitle}</h2>
            <p className="mt-1 text-xs text-zinc-500">{ar.watchlistHint}</p>
          </div>
          <form onSubmit={onAdd} className="mb-3 flex gap-2">
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              inputMode="numeric"
              maxLength={4}
              placeholder={ar.symbolPlaceholder}
              className="w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-sm outline-none ring-emerald-500/40 focus:ring"
            />
            <button
              type="submit"
              disabled={adding}
              className="shrink-0 rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 disabled:opacity-50"
            >
              {ar.addSymbol}
            </button>
          </form>
          <div className="grid gap-3">
            {watchlistRows.length ? (
              watchlistRows.map((row) => (
                <StockSignalCard
                  key={row.symbol}
                  row={row}
                  selected={row.symbol === selected}
                  onSelect={setSelected}
                  onRemove={(ticker) => {
                    void removeSymbol(ticker);
                  }}
                />
              ))
            ) : (
              <p className="rounded-2xl border border-dashed border-zinc-800 px-4 py-8 text-center text-sm text-zinc-500">
                {ar.watchlistEmpty}
              </p>
            )}
          </div>
        </section>
      </div>

      <div className="mt-2">
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-[13px] font-medium tracking-wide text-zinc-500">{ar.tape}</p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-50">
              <span className="font-mono">{selected}</span>
              <span className="me-3 ms-3 text-base font-medium text-zinc-500">{ar.netFlow}</span>
            </h2>
          </div>
          {selectedRow ? (
            <div className="rounded-2xl border border-zinc-800 bg-tape-panel px-4 py-3">
              <SignalBadge row={selectedRow} />
              <SuggestedPrices row={selectedRow} />
            </div>
          ) : null}
        </div>
        <div className="grid gap-4 lg:grid-cols-12">
          <NetFlowMeter tick={liveTick} sparkline={sparkline} className="lg:col-span-8" />
          <RegimeCard regime={regime} tick={liveTick} className="lg:col-span-4" />
          <VolumeCard
            label={ar.buy}
            hint={ar.buyHint}
            value={liveTick?.buyVolume ?? 0}
            notional={liveTick?.inflow ?? 0}
            tone="buy"
            className="lg:col-span-6"
          />
          <VolumeCard
            label={ar.sell}
            hint={ar.sellHint}
            value={liveTick?.sellVolume ?? 0}
            notional={liveTick?.outflow ?? 0}
            tone="sell"
            className="lg:col-span-6"
          />
          <LiveAlertsLog alerts={alerts} className="lg:col-span-12" />
        </div>
      </div>
    </section>
  );
}

function PulseStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 font-mono text-sm text-zinc-200" dir="ltr">
        {value}
      </p>
    </div>
  );
}

const ConnectionBadge = memo(function ConnectionBadge({
  status,
  attempts,
}: {
  status: ConnectionStatus;
  attempts: number;
}) {
  const color =
    status === "live"
      ? "bg-emerald-400"
      : status === "reconnecting" || status === "connecting"
        ? "bg-amber-400"
        : "bg-zinc-500";

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center gap-3 rounded-full border border-zinc-800 bg-zinc-900/70 px-4 py-2 text-sm text-zinc-300"
    >
      <span className={`h-2.5 w-2.5 rounded-full ${color} ${status === "live" ? "animate-pulseDot" : ""}`} />
      <span className="font-medium">{STATUS_COPY[status]}</span>
      {status === "reconnecting" && attempts > 0 ? (
        <span className="text-zinc-500">
          {ar.attempt} {formatCount(attempts)}
        </span>
      ) : null}
    </div>
  );
});

const NetFlowMeter = memo(function NetFlowMeter({
  tick,
  sparkline,
  className = "",
}: {
  tick: LiquidityTick | null;
  sparkline: number[];
  className?: string;
}) {
  const netFlow = tick?.netFlow ?? 0;
  const buy = tick?.buyVolume ?? 0;
  const sell = tick?.sellVolume ?? 0;
  const total = buy + sell;
  const buyShare = total > 0 ? (buy / total) * 100 : 50;
  const positive = netFlow > 0;
  const negative = netFlow < 0;

  const marker = useMemo(() => {
    const magnitude = Math.abs(tick?.inflow ?? 0) + Math.abs(tick?.outflow ?? 0);
    if (magnitude <= 0) return 50;
    const ratio = Math.max(-1, Math.min(1, netFlow / magnitude));
    return 50 + ratio * 48;
  }, [netFlow, tick?.inflow, tick?.outflow]);

  return (
    <article
      className={`rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-5 shadow-glow sm:p-6 ${className}`}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium text-zinc-500">{ar.netFlow}</p>
          <p
            aria-live="polite"
            className={`mt-3 text-start font-semibold sm:text-5xl ${
              positive ? "text-emerald-400" : negative ? "text-rose-400" : "text-zinc-200"
            }`}
          >
            <span dir="ltr" className="inline-block font-mono text-4xl tabular-nums sm:text-5xl">
              <AnimatedNumber value={netFlow} format={formatMoney} />
            </span>
          </p>
        </div>
        <div className="shrink-0 text-xs text-zinc-500">
          <p className="whitespace-nowrap">
            {ar.lastPrice}{" "}
            <span dir="ltr" className="inline-block font-mono">
              {formatPrice(tick?.lastPrice ?? null)}
            </span>
          </p>
          <p className="mt-1 whitespace-nowrap">
            {formatCount(tick?.tradeCount ?? 0)} {ar.prints}
          </p>
        </div>
      </div>

      <div className="relative mt-8">
        <div className="h-2.5 overflow-hidden rounded-full bg-zinc-800">
          <div className="flex h-full w-full">
            <div className="h-full bg-rose-500" style={{ width: `${100 - buyShare}%` }} />
            <div className="h-full bg-emerald-500" style={{ width: `${buyShare}%` }} />
          </div>
        </div>
        <div
          className="pointer-events-none absolute -top-1 h-4 w-0.5 rounded-full bg-white shadow-[0_0_12px_rgba(255,255,255,0.65)]"
          style={{ insetInlineStart: `${marker}%` }}
        />
        <div className="mt-2 flex justify-between text-xs text-zinc-500">
          <span>{ar.outflow}</span>
          <span>{ar.inflow}</span>
        </div>
      </div>

      <Sparkline values={sparkline} positive={positive} />
    </article>
  );
});

const Sparkline = memo(function Sparkline({
  values,
  positive,
}: {
  values: number[];
  positive: boolean;
}) {
  if (values.length < 2) {
    return <div className="mt-6 h-16 rounded-xl bg-zinc-900/80" />;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * 100;
      const y = 100 - ((value - min) / span) * 100;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <svg
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      className="mt-6 h-16 w-full -scale-x-100"
    >
      <polyline
        fill="none"
        stroke={positive ? "#34d399" : "#fb7185"}
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
        points={points}
      />
    </svg>
  );
});

const VolumeCard = memo(function VolumeCard({
  label,
  hint,
  value,
  notional,
  tone,
  className = "",
}: {
  label: string;
  hint: string;
  value: number;
  notional: number;
  tone: "buy" | "sell";
  className?: string;
}) {
  const accent = tone === "buy" ? "text-emerald-400" : "text-rose-400";
  const bar = tone === "buy" ? "from-emerald-500/20 to-transparent" : "from-rose-500/20 to-transparent";

  return (
    <article
      className={`relative overflow-hidden rounded-2xl border border-zinc-800/80 bg-tape-panel p-5 sm:p-6 ${className}`}
    >
      <div className={`pointer-events-none absolute inset-0 bg-gradient-to-bl ${bar}`} />
      <p className="relative text-sm font-medium text-zinc-500">{label}</p>
      <p className={`relative mt-3 text-start font-semibold ${accent}`}>
        <span dir="ltr" className="inline-block font-mono text-3xl tabular-nums">
          <AnimatedNumber value={value} format={formatVolume} />
        </span>
      </p>
      <p className="relative mt-2 text-start text-sm text-zinc-400">
        <span dir="ltr" className="inline-block font-mono">
          <AnimatedNumber value={Math.abs(notional)} format={formatMoney} />
        </span>{" "}
        {ar.notional}
      </p>
      <p className="relative mt-4 text-xs text-zinc-600">{hint}</p>
    </article>
  );
});

const RegimeCard = memo(function RegimeCard({
  regime,
  tick,
  className = "",
}: {
  regime: TapeRegime;
  tick: LiquidityTick | null;
  className?: string;
}) {
  const accumulating = regime === "accumulation";
  const distributing = regime === "distribution";
  const color = accumulating
    ? "text-emerald-300"
    : distributing
      ? "text-rose-300"
      : "text-zinc-300";
  const glow = accumulating
    ? "shadow-[0_0_36px_rgba(16,185,129,0.18)]"
    : distributing
      ? "shadow-[0_0_36px_rgba(244,63,94,0.16)]"
      : "";
  const stripe = accumulating
    ? "from-emerald-400 via-emerald-300 to-emerald-500"
    : distributing
      ? "from-rose-400 via-rose-300 to-rose-500"
      : "from-zinc-500 via-zinc-400 to-zinc-600";

  return (
    <article
      className={`flex flex-col justify-between overflow-hidden rounded-2xl border border-zinc-800/80 bg-tape-panel p-5 sm:p-6 ${glow} ${className}`}
    >
      <div>
        <p className="text-sm font-medium text-zinc-500">{ar.regime}</p>
        <p className={`mt-4 text-2xl font-semibold leading-snug tracking-tight ${color}`}>
          {REGIME_COPY[regime]}
        </p>
        <p className="mt-2 text-sm leading-relaxed text-zinc-500">
          {accumulating
            ? ar.accumulationDesc
            : distributing
              ? ar.distributionDesc
              : ar.neutralDesc}
        </p>
      </div>
      <div className="mt-6">
        <div
          className={`h-1.5 rounded-full bg-gradient-to-l ${stripe} bg-[length:200%_100%] ${
            regime === "neutral" ? "" : "animate-flow"
          }`}
        />
        <p className="mt-3 text-xs text-zinc-600">
          {tick?.lastSide === "BUY"
            ? ar.lastBuy
            : tick?.lastSide === "SELL"
              ? ar.lastSell
              : ar.noPrint}
        </p>
      </div>
    </article>
  );
});

const KIND_TONE: Record<LiquidityAlertEvent["kind"], string> = {
  inflow_surge: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  net_flow_spike: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  outflow_surge: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  volume_surge: "border-amber-500/40 bg-amber-500/10 text-amber-300",
};

const LiveAlertsLog = memo(function LiveAlertsLog({
  alerts,
  className = "",
}: {
  alerts: LiquidityAlertEvent[];
  className?: string;
}) {
  return (
    <article
      className={`rounded-2xl border border-zinc-800/80 bg-tape-panel p-5 sm:p-6 ${className}`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-zinc-500">{ar.alertsTitle}</p>
          <p className="mt-1 text-xs text-zinc-600">{ar.windowLabel}</p>
        </div>
        <PushToggle />
      </div>
      <div className="mt-4 max-h-72 space-y-2 overflow-y-auto pe-1">
        {alerts.length === 0 ? (
          <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-6 text-center text-sm text-zinc-500">
            {ar.noAlerts}
          </p>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.id}
              className={`rounded-xl border px-4 py-3 ${KIND_TONE[alert.kind]}`}
            >
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-semibold">{alert.title}</p>
                <time
                  dir="ltr"
                  className="shrink-0 font-mono text-xs text-zinc-400"
                  dateTime={alert.timestamp}
                >
                  {formatClock(alert.timestamp)}
                </time>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-zinc-300">{alert.message}</p>
            </div>
          ))
        )}
      </div>
    </article>
  );
});

function PushToggle() {
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">("default");

  useEffect(() => {
    if (typeof Notification === "undefined") {
      setPermission("unsupported");
      return;
    }
    setPermission(Notification.permission);
  }, []);

  if (permission === "unsupported") return null;
  if (permission === "granted") {
    return <span className="text-xs text-emerald-400">{ar.pushEnabled}</span>;
  }
  if (permission === "denied") {
    return <span className="text-xs text-zinc-600">{ar.pushDenied}</span>;
  }

  return (
    <button
      type="button"
      className="rounded-full border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 transition hover:border-emerald-500 hover:text-emerald-300"
      onClick={() => {
        void Notification.requestPermission().then(setPermission);
      }}
    >
      {ar.enablePush}
    </button>
  );
}
