"use client";

import { ar } from "@/lib/ar";
import { wsUrlFor } from "@/lib/api";
import { formatMoney, formatPercent, formatPrice, formatRatio } from "@/lib/liquidity";
import {
  overlayTickOnReport,
  type LiveRadarReport,
  type LiveRadarSignal,
} from "@/lib/liveRadar";
import { useLiveRadar } from "@/hooks/useLiveRadar";
import { useLiquiditySocket } from "@/hooks/useLiquiditySocket";

export function LiquidityRadarCard({
  symbol,
  symbolName,
}: {
  symbol: string;
  symbolName?: string;
}) {
  const { data, loading, refresh } = useLiveRadar(symbol);
  const { tick, status } = useLiquiditySocket(wsUrlFor(symbol));
  const report = data?.analysis ? overlayTickOnReport(data.analysis, tick) : null;
  const title = (symbolName || "").trim();
  const quoteMode = report?.quote_mode ?? (report?.live_quote ? "live" : report?.last_price ? "last_close" : "waiting");
  const live = quoteMode === "live" && status === "live";
  const statusLabel = live
    ? ar.liveRadarLive
    : quoteMode === "last_close"
      ? ar.liveRadarLastClose
      : ar.liveRadarWaiting;

  return (
    <article className="rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-5 shadow-glow sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium text-zinc-500">{ar.liveRadarTitle}</p>
          <h3 className="mt-1 text-2xl font-semibold text-zinc-50">
            {title ? <span>{title} </span> : null}
            <span className="font-mono" dir="ltr">
              {symbol}
            </span>
          </h3>
          <p className="mt-1 text-xs text-zinc-500">{ar.liveRadarHint}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`inline-flex rounded-full border px-3 py-1.5 text-[11px] ${
              live
                ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
                : "border-zinc-700 bg-zinc-900 text-zinc-400"
            }`}
          >
            {statusLabel}
          </span>
          {report ? <SignalPill report={report} /> : null}
          <button
            type="button"
            onClick={() => {
              void refresh();
            }}
            className="rounded-full border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 transition hover:border-emerald-500 hover:text-emerald-300"
          >
            {ar.radarRetry}
          </button>
        </div>
      </div>

      {loading && !report ? (
        <p className="mt-5 text-sm text-zinc-500">{ar.liveRadarLoading}</p>
      ) : report ? (
        <ReportBody report={report} source={data?.source} />
      ) : (
        <p className="mt-5 text-sm text-zinc-500">{ar.liveRadarWaiting}</p>
      )}
    </article>
  );
}

function ReportBody({ report, source }: { report: LiveRadarReport; source?: string }) {
  const positive = report.net_flow > 0;
  const negative = report.net_flow < 0;

  return (
    <div className="mt-5 space-y-4">
      {report.trap ? (
        <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          {ar.liveRadarTrap}: {report.trap.label}
        </p>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <Metric
          label={ar.netFlow}
          value={formatMoney(report.net_flow)}
          tone={positive ? "up" : negative ? "down" : "flat"}
        />
        <Metric
          label={report.quote_mode === "last_close" ? ar.liveRadarLastClosePrice : ar.lastPrice}
          value={formatPrice(report.last_price)}
        />
        <Metric
          label={ar.regime}
          value={formatPercent(report.change_percent)}
          tone={(report.change_percent ?? 0) >= 0 ? "up" : "down"}
        />
      </div>

      {report.bid != null || report.ask != null ? (
        <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
          <span>
            {ar.bid} <span dir="ltr">{formatPrice(report.bid ?? null)}</span>
          </span>
          <span>
            {ar.ask} <span dir="ltr">{formatPrice(report.ask ?? null)}</span>
          </span>
          <span>
            {ar.spread} <span dir="ltr">{formatPrice(report.spread ?? null)}</span>
          </span>
        </p>
      ) : null}

      {report.entry && report.suggested_entry != null ? (
        <p className="text-sm font-semibold text-emerald-300">
          {ar.entryPriceLabel}:{" "}
          <span dir="ltr" className="font-mono">
            {formatPrice(report.suggested_entry)}
          </span>
        </p>
      ) : null}
      {report.exit && report.suggested_exit != null ? (
        <p className="text-sm font-semibold text-amber-200">
          {ar.exitPriceLabel}:{" "}
          <span dir="ltr" className="font-mono">
            {formatPrice(report.suggested_exit)}
          </span>
        </p>
      ) : null}

      <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
        <span>
          {ar.vwap} <span dir="ltr">{formatPrice(report.vwap)}</span>
        </span>
        <span>
          {ar.atr} <span dir="ltr">{formatPrice(report.atr)}</span>
        </span>
        <span>
          {ar.buyPressure} {formatRatio(report.buy_ratio)}
        </span>
        <span>
          {ar.sellPressure} {formatRatio(report.sell_ratio)}
        </span>
        <span>
          MFI مؤسسي{" "}
          <span dir="ltr">
            {report.institutional_mfi != null || report.mfi != null
              ? `${Math.round(report.institutional_mfi ?? report.mfi ?? 0)}%`
              : "—"}
          </span>
        </span>
        <span>
          MFI أفراد{" "}
          <span dir="ltr">{report.retail_mfi != null ? `${Math.round(report.retail_mfi)}%` : "—"}</span>
        </span>
        <span>
          تضاعف الحجم{" "}
          <span dir="ltr">
            {report.volume_ratio != null ? `${report.volume_ratio.toFixed(2)}×` : "—"}
          </span>
        </span>
        <span>
          صفقات بلوك{" "}
          <span dir="ltr">{report.block_trades ?? 0}</span>
        </span>
      </p>

      {report.bid_wall || report.ask_wall ? (
        <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
          {report.bid_wall ? (
            <span>
              جدار طلب{" "}
              <span dir="ltr">
                {formatPrice(report.bid_wall.price)} × {Math.round(report.bid_wall.quantity).toLocaleString("en-US")}
              </span>
            </span>
          ) : null}
          {report.ask_wall ? (
            <span>
              جدار عرض{" "}
              <span dir="ltr">
                {formatPrice(report.ask_wall.price)} × {Math.round(report.ask_wall.quantity).toLocaleString("en-US")}
              </span>
            </span>
          ) : null}
        </p>
      ) : null}

      {report.reasons.length ? (
        <ul className="space-y-1 text-sm text-zinc-300">
          {report.reasons.slice(0, 4).map((reason) => (
            <li key={reason}>• {reason}</li>
          ))}
        </ul>
      ) : null}

      <p className="text-[11px] text-zinc-600">
        {report.session_label ? `${report.session_label} · ` : ""}
        {report.quote_mode === "last_close"
          ? ar.liveRadarLastCloseHint
          : report.quote_mode === "waiting"
            ? ar.liveRadarWaiting
            : source === "cached"
              ? ar.liveRadarCached
              : ar.liveRadarSource}
      </p>
    </div>
  );
}

function SignalPill({ report }: { report: LiveRadarReport }) {
  const kind: LiveRadarSignal = report.entry ? "entry" : report.exit ? "exit" : report.trap ? "trap" : "neutral";
  const label =
    kind === "entry"
      ? ar.entryBadge
      : kind === "exit"
        ? ar.exitBadge
        : kind === "trap"
          ? ar.liveRadarTrap
          : ar.liveRadarNeutral;
  const tone =
    kind === "entry"
      ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-300"
      : kind === "exit"
        ? "border-amber-400/40 bg-amber-500/15 text-amber-200"
        : kind === "trap"
          ? "border-rose-400/40 bg-rose-500/15 text-rose-200"
          : "border-zinc-700 bg-zinc-900 text-zinc-400";
  return (
    <span className={`inline-flex rounded-full border px-3 py-1.5 text-xs font-semibold ${tone}`}>
      {label}
    </span>
  );
}

function Metric({
  label,
  value,
  tone = "flat",
}: {
  label: string;
  value: string;
  tone?: "up" | "down" | "flat";
}) {
  const color = tone === "up" ? "text-emerald-400" : tone === "down" ? "text-rose-400" : "text-zinc-100";
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 px-3 py-3">
      <p className="text-xs text-zinc-500">{label}</p>
      <p dir="ltr" className={`mt-1 font-mono text-sm ${color}`}>
        {value}
      </p>
    </div>
  );
}

export default LiquidityRadarCard;
