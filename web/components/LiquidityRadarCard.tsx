"use client";

import { RecommendationStatus } from "@/components/SignalBadge";
import { ar } from "@/lib/ar";
import { wsUrlFor } from "@/lib/api";
import {
  formatMoney,
  formatPercent,
  formatPrice,
  formatRatio,
  regimeFromNetFlow,
  type TapeRegime,
} from "@/lib/liquidity";
import {
  overlayTickOnReport,
  type LiveRadarReport,
  type LiveRadarSignal,
} from "@/lib/liveRadar";
import { useLiveRadar } from "@/hooks/useLiveRadar";
import { useLiquiditySocket } from "@/hooks/useLiquiditySocket";
import { displayCompanyTitle } from "@/lib/listedCompanies";

export function LiquidityRadarCard({
  symbol,
  symbolName,
  onRemove,
}: {
  symbol: string;
  symbolName?: string;
  onRemove?: () => void;
}) {
  const { data, loading, refresh } = useLiveRadar(symbol);
  const { tick, status } = useLiquiditySocket(wsUrlFor(symbol));
  const report = data?.analysis ? overlayTickOnReport(data.analysis, tick) : null;
  const title = displayCompanyTitle(symbol, symbolName);
  const quoteMode = report?.quote_mode ?? (report?.live_quote ? "live" : report?.last_price ? "last_close" : "waiting");
  const live = quoteMode === "live" && status === "live";
  const statusLabel = live
    ? ar.liveRadarLive
    : quoteMode === "last_close"
      ? ar.liveRadarLastClose
      : ar.liveRadarWaiting;

  const retry = () => {
    void refresh();
  };

  return (
    <article className="relative rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-4 pt-5 shadow-glow sm:p-6 sm:pt-7">
      {onRemove ? (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`${ar.marketRadarRemove} ${title || symbol}`}
          title={ar.marketRadarRemove}
          className="absolute left-3 top-3 z-20 flex h-9 w-9 items-center justify-center rounded-full border border-rose-400/60 bg-zinc-950 text-xl font-light leading-none text-rose-200 shadow-lg shadow-rose-950/50 transition hover:border-rose-200 hover:bg-rose-500/20 hover:text-white"
        >
          ×
        </button>
      ) : null}
      <div className="flex flex-col items-center gap-3 text-center sm:flex-row sm:items-start sm:justify-between sm:text-start">
        <div className={onRemove ? "px-10 sm:px-0" : ""}>
          <p className="hidden text-sm font-medium text-zinc-500 sm:block">{ar.liveRadarTitle}</p>
          <h3 className="flex flex-wrap items-baseline justify-center gap-x-2 gap-y-1 text-xl font-semibold text-zinc-50 sm:mt-1 sm:justify-start sm:text-2xl">
            {title ? <span>{title}</span> : null}
            {report ? (
              <span className="hidden sm:inline">
                <RecommendationStatus value={report.entry ? "دخول" : report.exit ? "خروج" : null} />
              </span>
            ) : null}
            <span className="font-mono text-base text-zinc-300 sm:text-lg" dir="ltr">
              {symbol}
            </span>
          </h3>
          <p className="mt-1 hidden text-xs text-zinc-500 sm:block">{ar.liveRadarHint}</p>
        </div>
        <div className={`hidden flex-wrap items-center gap-2 sm:flex ${onRemove ? "pl-11" : ""}`}>
          <span
            className={`inline-flex rounded-full border px-3 py-1.5 text-[11px] ${
              live
                ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
                : "border-zinc-700 bg-zinc-900 text-zinc-400"
            }`}
          >
            {statusLabel}
          </span>
          {report ? <RegimePill report={report} /> : null}
          {report ? <SignalPill report={report} /> : null}
          <RetryButton onRetry={retry} />
        </div>
      </div>

      {loading && !report ? (
        <p className="mt-4 text-center text-sm text-zinc-500 sm:mt-5 sm:text-start">{ar.liveRadarLoading}</p>
      ) : report ? (
        <ReportBody report={report} source={data?.source} />
      ) : (
        <p className="mt-4 text-center text-sm text-zinc-500 sm:mt-5 sm:text-start">{ar.liveRadarWaiting}</p>
      )}

      <RetryButton onRetry={retry} className="mx-auto mt-4 sm:hidden" />
    </article>
  );
}

function RetryButton({ onRetry, className }: { onRetry: () => void; className?: string }) {
  return (
    <button
      type="button"
      onClick={onRetry}
      className={`rounded-full border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 transition hover:border-emerald-500 hover:text-emerald-300 ${className ?? ""}`}
    >
      {ar.radarRetry}
    </button>
  );
}

function stockRegime(report: LiveRadarReport): TapeRegime {
  if (report.net_flow) return regimeFromNetFlow(report.net_flow);
  const change = report.change_percent ?? 0;
  if (change > 0) return "accumulation";
  if (change < 0) return "distribution";
  return "neutral";
}

function regimeCopy(regime: TapeRegime): { label: string; hint: string; tone: "up" | "down" | "flat" } {
  if (regime === "accumulation") {
    return { label: ar.accumulation, hint: ar.accumulationDesc, tone: "up" };
  }
  if (regime === "distribution") {
    return { label: ar.distribution, hint: ar.distributionDesc, tone: "down" };
  }
  return { label: ar.neutral, hint: ar.neutralDesc, tone: "flat" };
}

function CompactSummary({ report }: { report: LiveRadarReport }) {
  const copy = regimeCopy(stockRegime(report));
  const priceLabel = report.quote_mode === "last_close" ? ar.liveRadarLastClosePrice : ar.lastPrice;
  const signal = report.entry ? "دخول" : report.exit ? "خروج" : null;
  const regimeColor =
    copy.tone === "up" ? "text-emerald-300" : copy.tone === "down" ? "text-rose-300" : "text-zinc-200";

  return (
    <div className="mt-4 flex flex-col items-center gap-3 text-center sm:hidden">
      <div>
        <p className="text-xs text-zinc-500">{priceLabel}</p>
        <p dir="ltr" className="mt-1 font-mono text-sm font-semibold text-zinc-100">
          {formatPrice(report.last_price)}
        </p>
      </div>
      <div>
        <p className="text-xs text-zinc-500">{ar.regime}</p>
        <p className={`mt-1 text-sm font-semibold ${regimeColor}`}>{copy.label}</p>
      </div>
      <div>
        <p className="text-xs text-zinc-500">{ar.liveRadarConfirmed}</p>
        <div className="mt-1 flex justify-center">
          {signal ? (
            <RecommendationStatus value={signal} />
          ) : (
            <p className="text-sm text-zinc-400">{ar.liveRadarNeutral}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function ReportBody({ report, source }: { report: LiveRadarReport; source?: string }) {
  const positive = report.net_flow > 0;
  const negative = report.net_flow < 0;
  const regime = stockRegime(report);
  const copy = regimeCopy(regime);

  return (
    <>
      <CompactSummary report={report} />

      <div className="mt-5 hidden space-y-4 sm:block">
        {report.trap ? (
          <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
            {ar.liveRadarTrap}: {report.trap.label}
          </p>
        ) : null}

        <div
          className={`rounded-xl border px-4 py-3 ${
            copy.tone === "up"
              ? "border-emerald-500/30 bg-emerald-500/10"
              : copy.tone === "down"
                ? "border-rose-500/30 bg-rose-500/10"
                : "border-zinc-800 bg-zinc-950/60"
          }`}
        >
          <p className="text-xs text-zinc-500">{ar.regime}</p>
          <p
            className={`mt-1 text-lg font-semibold ${
              copy.tone === "up" ? "text-emerald-300" : copy.tone === "down" ? "text-rose-300" : "text-zinc-200"
            }`}
          >
            {copy.label}
          </p>
          <p className="mt-1 text-xs text-zinc-400">{copy.hint}</p>
        </div>

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
            label={ar.heatmapColChange}
            value={formatPercent(report.change_percent)}
            tone={(report.change_percent ?? 0) > 0 ? "up" : (report.change_percent ?? 0) < 0 ? "down" : "flat"}
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
    </>
  );
}

function RegimePill({ report }: { report: LiveRadarReport }) {
  const copy = regimeCopy(stockRegime(report));
  const tone =
    copy.tone === "up"
      ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-300"
      : copy.tone === "down"
        ? "border-rose-400/40 bg-rose-500/15 text-rose-200"
        : "border-zinc-700 bg-zinc-900 text-zinc-400";
  return (
    <span className={`inline-flex rounded-full border px-3 py-1.5 text-xs font-semibold ${tone}`}>
      {copy.label}
    </span>
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
