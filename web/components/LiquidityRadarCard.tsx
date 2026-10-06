"use client";

import { RecommendationStatus } from "@/components/SignalBadge";
import { ar } from "@/lib/ar";
import { wsUrlFor } from "@/lib/api";
import {
  formatCompact,
  formatMoney,
  formatPercent,
  formatPrice,
  formatRatio,
  type TapeRegime,
} from "@/lib/liquidity";
import { useEffect, useState } from "react";

import { useHeldReport } from "@/hooks/useHeldReport";
import { useSymbolRegime } from "@/hooks/useSymbolRegime";
import { type LiveRadarReport, type LiveRadarSignal } from "@/lib/liveRadar";
import { useLiveRadar } from "@/hooks/useLiveRadar";
import { useLiquiditySocket } from "@/hooks/useLiquiditySocket";
import { displayCompanyTitle } from "@/lib/listedCompanies";
import { CompanyStrengthLine } from "@/components/CompanyStrengthLine";
import { DataSkeleton } from "@/components/DataSkeleton";
import { companyRankFor } from "@/lib/rankingMatrix";
import { buildStockDossier, resolveTapePath, valuationStance, type FieldState, type StockDossier } from "@/lib/stockDossier";

type QuoteMode = "live" | "waiting" | "last_close";

function toQuoteMode(value: string | null | undefined): QuoteMode | undefined {
  if (value === "live" || value === "waiting" || value === "last_close") return value;
  return undefined;
}

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
  const { status } = useLiquiditySocket(wsUrlFor(symbol));
  const report = useHeldReport(symbol, data?.analysis ?? null);
  const regime = useSymbolRegime(
    symbol,
    report
      ? {
          netFlow: report.net_flow,
          buyVolume: report.buy_volume,
          sellVolume: report.sell_volume,
          price: report.last_price,
        }
      : null,
  );
  const fundamentals = useDossierFundamentals(symbol);
  const dossier = buildStockDossier(symbol, report?.last_price ?? null, report, fundamentals);
  const title = displayCompanyTitle(symbol, symbolName);
  const quoteMode: QuoteMode | undefined =
    toQuoteMode(report?.quote_mode) ??
    (report?.live_quote ? "live" : report?.last_price ? "last_close" : "waiting");
  const inSession =
    report?.session_phase === "preopen" || report?.session_phase === "open" || report?.session_phase === "auction";
  const live = quoteMode === "live" && status === "live";
  const statusLabel = live
    ? ar.liveRadarLive
    : inSession && report?.last_price
      ? ar.lastPrice
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
          className="absolute left-2 top-2 z-20 inline-flex h-8 items-center gap-1 rounded-full border border-rose-400/70 bg-zinc-950 px-2.5 text-rose-100 shadow-lg shadow-rose-950/40 transition hover:border-rose-200 hover:bg-rose-500/20 hover:text-white"
        >
          <span aria-hidden="true" className="text-base leading-none">
            ×
          </span>
          <span className="text-[11px] font-semibold">{ar.marketRadarRemove}</span>
        </button>
      ) : null}
      <div className="flex flex-col items-center gap-3 text-center sm:flex-row sm:items-start sm:justify-between sm:text-start">
        <div className={onRemove ? "px-4 pt-8 sm:px-0 sm:pt-0" : ""}>
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
          <CompanyStrengthLine symbol={symbol} />
          <p className="mt-1 hidden text-xs text-zinc-500 sm:block">{ar.liveRadarHint}</p>
        </div>
        <div className={`hidden flex-wrap items-center gap-2 sm:flex ${onRemove ? "pl-[5.5rem]" : ""}`}>
          <span
            className={`inline-flex rounded-full border px-3 py-1.5 text-[11px] ${
              live
                ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-300"
                : "border-zinc-700 bg-zinc-900 text-zinc-400"
            }`}
          >
            {statusLabel}
          </span>
          {report ? <RegimePill regime={regime} /> : null}
          {report ? (
            <SignalPill
              report={{
                ...report,
                quote_mode: report.quote_mode as "live" | "waiting" | "last_close" | undefined,
              }}
            />
          ) : null}
          <RetryButton onRetry={retry} />
        </div>
      </div>

      {report ? (
        <SessionPathStrip
          quoteMode={report.quote_mode}
          phase={report.session_phase}
          price={report.last_price}
          vwap={report.session_vwap ?? report.vwap}
          stance={valuationStance(report.last_price, dossier.fairValue)}
        />
      ) : null}

      {loading && !report ? (
        <div className="mt-4">
          <DataSkeleton kind="card" />
        </div>
      ) : report ? (
        <ReportBody report={report} source={data?.source} regime={regime} dossier={dossier} />
      ) : (
        <p className="mt-4 text-center text-sm text-zinc-500 sm:mt-5 sm:text-start">{ar.liveRadarWaiting}</p>
      )}

      <RetryButton onRetry={retry} className="mx-auto mt-4 sm:hidden" />
    </article>
  );
}

function SessionPathStrip({
  quoteMode,
  phase,
  price,
  vwap,
  stance,
}: {
  quoteMode?: string | null;
  phase?: string | null;
  price: number | null;
  vwap: number | null;
  stance: ReturnType<typeof valuationStance>;
}) {
  const tape = resolveTapePath({ quoteMode, phase, price, vwap });
  const tone = tape.path === "up" ? "path-up" : tape.path === "down" ? "path-down" : "border-zinc-700 bg-zinc-950 text-zinc-300";
  const valuation =
    stance === "over"
      ? ar.valuationOver
      : stance === "attractive"
        ? ar.valuationAttractive
        : stance === "near"
          ? ar.valuationNear
          : ar.valuationPending;
  const valuationTone =
    stance === "over"
      ? "text-orange-200"
      : stance === "attractive"
        ? "text-emerald-200"
        : "text-zinc-400";
  const gap =
    tape.price != null && tape.anchor != null && tape.anchor > 0
      ? ((tape.price - tape.anchor) / tape.anchor) * 100
      : null;

  return (
    <section className={`mt-4 w-full rounded-xl border p-4 ${tone}`}>
      <div className="flex flex-col gap-2">
        <span className="text-xs font-medium">
          {phase === "preopen" || phase === "open" || phase === "auction" ? ar.lastPrice : ar.liveRadarLastClosePrice}:{" "}
          <strong dir="ltr" className="font-mono text-sm">
            {priceText(tape.price)}
          </strong>
        </span>
        <span className="text-xs font-medium">
          {ar.sessionVwap}:{" "}
          <strong dir="ltr" className="font-mono text-sm">
            {priceText(tape.anchor)}
          </strong>
        </span>
        {gap != null ? (
          <span className="text-xs font-medium">
            {ar.sessionVwapGap}:{" "}
            <strong dir="ltr" className="font-mono text-sm">
              {formatCompact(gap)}%
            </strong>
          </span>
        ) : null}
      </div>
      {tape.path === "up" ? (
        <p className="mt-3 inline-flex rounded-full bg-emerald-600 px-3 py-1.5 text-sm font-bold text-white">{ar.sessionPathUp}</p>
      ) : tape.path === "down" ? (
        <p className="mt-3 inline-flex rounded-full bg-rose-600 px-3 py-1.5 text-sm font-bold text-white">{ar.sessionPathDown}</p>
      ) : null}
      <p className={`mt-2 text-xs font-semibold leading-5 ${valuationTone}`}>{valuation}</p>
    </section>
  );
}

function priceText(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return ar.dossierMissing;
  return formatPrice(value);
}

function dashText(value: string): string {
  return value === "—" ? ar.dossierMissing : value;
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

function regimeCopy(regime: TapeRegime): { label: string; hint: string; tone: "up" | "down" | "flat" } {
  if (regime === "accumulation") {
    return { label: ar.accumulation, hint: ar.accumulationDesc, tone: "up" };
  }
  if (regime === "distribution") {
    return { label: ar.distribution, hint: ar.distributionDesc, tone: "down" };
  }
  return { label: ar.neutral, hint: ar.neutralDesc, tone: "flat" };
}

function sessionPriceLabel(report: { quote_mode?: string | null; session_phase?: string | null }): string {
  if (report.session_phase === "preopen" || report.session_phase === "open" || report.session_phase === "auction") {
    return ar.lastPrice;
  }
  return report.quote_mode === "last_close" ? ar.liveRadarLastClosePrice : ar.lastPrice;
}

function CompactSummary({ report, regime }: { report: LiveRadarReport; regime: TapeRegime }) {
  const copy = regimeCopy(regime);
  const priceLabel = sessionPriceLabel(report);
  const signal = report.entry ? "دخول" : report.exit ? "خروج" : null;
  const regimeColor =
    copy.tone === "up" ? "text-emerald-300" : copy.tone === "down" ? "text-rose-300" : "text-zinc-200";

  return (
    <div className="mt-4 flex flex-col items-center gap-3 text-center sm:hidden">
      <div>
        <p className="text-xs text-zinc-500">{priceLabel}</p>
        <p dir="ltr" className="mt-1 font-mono text-sm font-semibold text-zinc-100">
          {priceText(report.last_price)}
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

function ReportBody({
  report,
  source,
  regime,
  dossier,
}: {
  report: LiveRadarReport;
  source?: string;
  regime: TapeRegime;
  dossier: StockDossier;
}) {
  const positive = report.net_flow > 0;
  const negative = report.net_flow < 0;
  const copy = regimeCopy(regime);

  return (
    <>
      <CompactSummary report={report} regime={regime} />
      <DossierStrip dossier={dossier} price={report.last_price} />

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
            label={sessionPriceLabel(report)}
            value={priceText(report.last_price)}
          />
          <Metric
            label={ar.heatmapColChange}
            value={dashText(formatPercent(report.change_percent))}
            tone={(report.change_percent ?? 0) > 0 ? "up" : (report.change_percent ?? 0) < 0 ? "down" : "flat"}
          />
        </div>

        {report.bid != null || report.ask != null ? (
          <p className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
            <span>
              {ar.bid} <span dir="ltr">{priceText(report.bid)}</span>
            </span>
            <span>
              {ar.ask} <span dir="ltr">{priceText(report.ask)}</span>
            </span>
            <span>
              {ar.spread} <span dir="ltr">{priceText(report.spread)}</span>
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
            {ar.sessionVwap} <span dir="ltr">{priceText(report.session_vwap ?? report.vwap)}</span>
          </span>
          <span>
            {ar.atr} <span dir="ltr">{priceText(report.atr)}</span>
          </span>
          <span>
            {ar.buyPressure} {dashText(formatRatio(report.buy_ratio))}
          </span>
          <span>
            {ar.sellPressure} {dashText(formatRatio(report.sell_ratio))}
          </span>
          <span>
            MFI مؤسسي{" "}
            <span dir="ltr">
              {report.institutional_mfi != null || report.mfi != null
                ? `${Math.round(report.institutional_mfi ?? report.mfi ?? 0)}%`
                : ar.dossierMissing}
            </span>
          </span>
          <span>
            MFI أفراد{" "}
            <span dir="ltr">{report.retail_mfi != null ? `${Math.round(report.retail_mfi)}%` : ar.dossierMissing}</span>
          </span>
          <span>
            تضاعف الحجم{" "}
            <span dir="ltr">
              {report.volume_ratio != null ? `${report.volume_ratio.toFixed(2)}×` : ar.dossierMissing}
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
          {report.session_phase === "preopen" || report.session_phase === "open" || report.session_phase === "auction"
            ? ar.lastPrice
            : report.quote_mode === "last_close"
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

function DossierStrip({ dossier, price }: { dossier: StockDossier; price: number | null }) {
  const shariah =
    dossier.shariah === "PURE"
      ? ar.dossierPure
      : dossier.shariah === "MIXED"
        ? ar.dossierMixed
        : dossier.shariah === "PROHIBITED"
          ? ar.dossierProhibited
          : ar.dossierUnknown;
  const tone =
    dossier.shariah === "PURE"
      ? "text-emerald-300"
      : dossier.shariah === "PROHIBITED"
        ? "text-rose-300"
        : "text-amber-200";
  const stance = valuationStance(price, dossier.fairValue);
  return (
    <section className="mt-4 rounded-xl border border-zinc-800 bg-zinc-950/50 px-3 py-3">
      <div className="grid auto-rows-fr grid-cols-2 gap-2 sm:grid-cols-4">
        <DossierMetric label={ar.dossierShariah} value={shariah} valueClass={tone} />
        <DossierMetric label={ar.dossierPe} value={fixed(dossier.peRatio, 2)} state={dossier.peState} />
        <DossierMetric
          label={ar.dossierYield}
          value={dossier.dividendYieldPct == null ? "" : `${fixed(dossier.dividendYieldPct, 2)}%`}
          state={dossier.yieldState}
        />
        <DossierMetric
          label={ar.dossierDebt}
          value={dossier.debtToMarket == null ? "" : `${(dossier.debtToMarket * 100).toFixed(1)}%`}
          state={dossier.debtState}
        />
        <DossierMetric label={ar.dossierFair} value={dossier.fairValue == null ? "" : formatPrice(dossier.fairValue)} state={dossier.fairState} />
        <DossierMetric label={ar.dossierHealth} value={fixed(dossier.healthScore, 1)} state={dossier.healthState} />
        <DossierMetric label={ar.dossierLiquidity} value={fixed(dossier.liquidityScore, 1)} state={dossier.liquidityState} />
      </div>
      <ValuationBadge stance={stance} />
      <p className="mt-2 text-center text-[11px] text-zinc-500">{ar.dossierFairHint}</p>
    </section>
  );
}

function ValuationBadge({ stance }: { stance: ReturnType<typeof valuationStance> }) {
  if (stance === "pending") {
    return <p className="mt-3 text-center text-xs text-zinc-500">{ar.valuationPending}</p>;
  }
  const tone =
    stance === "over"
      ? "border-orange-400/40 bg-orange-500/10 text-orange-200"
      : stance === "attractive"
        ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-200"
        : "border-zinc-700 bg-zinc-900 text-zinc-300";
  const label = stance === "over" ? ar.valuationOver : stance === "attractive" ? ar.valuationAttractive : ar.valuationNear;
  return <p className={`mt-3 rounded-xl border px-3 py-2 text-center text-xs font-semibold leading-5 ${tone}`}>{label}</p>;
}

function DossierMetric({
  label,
  value,
  state = "ready",
  valueClass,
}: {
  label: string;
  value: string;
  state?: FieldState;
  valueClass?: string;
}) {
  const missing = state !== "ready" || value === "" || value === "—";
  const shown = missing ? (state === "updating" ? ar.dossierUpdating : ar.dossierMissing) : value;
  return (
    <div className="flex min-h-[4.5rem] flex-col justify-between rounded-lg border border-zinc-800/80 bg-zinc-950/30 px-2 py-2 text-center">
      <p className="text-[11px] leading-4 text-zinc-500">{label}</p>
      <p
        dir={missing ? "rtl" : "ltr"}
        className={
          missing
            ? "mt-1 text-xs font-medium leading-5 text-zinc-500"
            : `mt-1 font-mono text-sm font-semibold leading-5 text-zinc-100 ${valueClass ?? ""}`
        }
      >
        {shown}
      </p>
    </div>
  );
}

function useDossierFundamentals(symbol: string): { peRatio: number | null; dividendYieldPct: number | null; settled: boolean } {
  const [state, setState] = useState<{ peRatio: number | null; dividendYieldPct: number | null; settled: boolean }>({
    peRatio: null,
    dividendYieldPct: null,
    settled: false,
  });

  useEffect(() => {
    let alive = true;
    setState({ peRatio: null, dividendYieldPct: null, settled: false });
    companyRankFor(symbol)
      .then((rank) => {
        if (!alive) return;
        setState({
          peRatio: rank?.pe_ratio ?? null,
          dividendYieldPct: rank?.dividend_yield ?? null,
          settled: true,
        });
      })
      .catch(() => {
        if (alive) setState({ peRatio: null, dividendYieldPct: null, settled: true });
      });
    return () => {
      alive = false;
    };
  }, [symbol]);

  return state;
}

function fixed(value: number | null, digits: number): string {
  return value == null ? "—" : value.toFixed(digits);
}

function RegimePill({ regime }: { regime: TapeRegime }) {
  const copy = regimeCopy(regime);
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
