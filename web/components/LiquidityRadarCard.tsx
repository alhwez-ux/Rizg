"use client";

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
import { PathBadge } from "@/components/PathBadge";
import { TradePlanLadder } from "@/components/TradePlanLadder";
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

  const priceLabel = report
    ? sessionPriceLabel(report)
    : statusLabel;

  return (
    <article className="relative rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-3 shadow-glow sm:p-4">
      {onRemove ? (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`${ar.marketRadarRemove} ${title || symbol}`}
          title={ar.marketRadarRemove}
          className="absolute left-2 top-2 z-20 inline-flex h-7 items-center gap-1 rounded-full border border-rose-400/70 bg-zinc-950 px-2 text-rose-100 shadow-lg shadow-rose-950/40 transition hover:border-rose-200 hover:bg-rose-500/20 hover:text-white"
        >
          <span aria-hidden="true" className="text-base leading-none">
            ×
          </span>
          <span className="text-[11px] font-semibold">{ar.marketRadarRemove}</span>
        </button>
      ) : null}
      <header className={`flex items-start justify-between gap-3 ${onRemove ? "pe-16" : ""}`}>
        <div className="min-w-0 text-start">
          <h3 className="flex flex-wrap items-baseline gap-x-2 text-lg font-semibold text-zinc-50">
            {title ? <span>{title}</span> : null}
            <span className="font-mono text-sm text-zinc-400" dir="ltr">
              {symbol}
            </span>
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {report ? (
              <PathBadge price={report.last_price} vwap={report.session_vwap} change={report.change_percent} />
            ) : null}
            {report ? <RegimePill regime={regime} /> : null}
            {report ? (
              <SignalPill
                report={{
                  ...report,
                  quote_mode: report.quote_mode as "live" | "waiting" | "last_close" | undefined,
                }}
              />
            ) : null}
            <CompanyStrengthLine symbol={symbol} />
          </div>
        </div>
        <div className="shrink-0 text-end">
          <p className="text-[10px] text-zinc-500">{priceLabel}</p>
          <p dir="ltr" className="font-mono text-xl font-semibold tabular-nums text-zinc-50">
            {report ? priceText(report.last_price) : "—"}
          </p>
          {report?.change_percent ? (
            <p
              dir="ltr"
              className={`font-mono text-xs tabular-nums ${(report.change_percent ?? 0) > 0 ? "text-emerald-300" : "text-rose-300"}`}
            >
              {formatPercent(report.change_percent)}
            </p>
          ) : null}
          <RetryButton onRetry={retry} className="mt-1" />
        </div>
      </header>

      {report ? (
        <SessionPathStrip
          quoteMode={report.quote_mode}
          phase={report.session_phase}
          price={report.last_price}
          vwap={report.session_vwap ?? report.vwap}
          high={report.session_high}
          low={report.session_low}
        />
      ) : null}

      {loading && !report ? (
        <div className="mt-4">
          <DataSkeleton kind="card" />
        </div>
      ) : report ? (
        <ReportBody report={report} source={data?.source} dossier={dossier} />
      ) : (
        <p className="mt-4 text-center text-sm text-zinc-500 sm:mt-5 sm:text-start">{ar.liveRadarWaiting}</p>
      )}

    </article>
  );
}

function SessionPathStrip({
  quoteMode,
  phase,
  price,
  vwap,
  high,
  low,
}: {
  quoteMode?: string | null;
  phase?: string | null;
  price: number | null;
  vwap: number | null;
  high?: number | null;
  low?: number | null;
}) {
  const tape = resolveTapePath({ quoteMode, phase, price, vwap, high, low });
  const gap =
    tape.price != null && tape.anchor != null && tape.anchor > 0
      ? ((tape.price - tape.anchor) / tape.anchor) * 100
      : null;
  const sameAsHeader = tape.anchorSource === "close" || (tape.anchor != null && tape.price != null && tape.anchor === tape.price);
  const showGap = gap != null && gap !== 0 && tape.anchorSource !== "close";
  if (sameAsHeader && !showGap) return null;
  return (
    <section className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-zinc-800 bg-zinc-950/50 px-2.5 py-1.5 text-[11px] text-zinc-300">
      {sameAsHeader ? null : (
        <span>
          {anchorLabel(tape.anchorSource)}{" "}
          <strong dir="ltr" className="font-mono">
            {priceText(tape.anchor)}
          </strong>
        </span>
      )}
      {showGap ? (
        <span>
          {tape.anchorSource === "range" ? ar.sessionRangeGap : ar.sessionVwapGap}{" "}
          <strong dir="ltr" className="font-mono">
            {formatCompact(gap)}%
          </strong>
        </span>
      ) : null}
    </section>
  );
}

function anchorLabel(source: "vwap" | "range" | "close" | null): string {
  if (source === "range") return ar.sessionRangeAnchor;
  if (source === "close") return ar.sessionCloseAnchor;
  return ar.sessionVwap;
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

function ReportBody({
  report,
  source,
  dossier,
}: {
  report: LiveRadarReport;
  source?: string;
  dossier: StockDossier;
}) {
  const positive = report.net_flow > 0;
  const negative = report.net_flow < 0;

  return (
    <>
      <TradePlanLadder
        className="mt-2"
        variant="row"
        entry={report.suggested_entry}
        stop={report.stop_loss}
        resistances={[report.session_high]}
      />
      <DossierStrip dossier={dossier} price={report.last_price} />

      <div className="mt-2 space-y-2">
        {report.trap ? (
          <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-100">
            {ar.liveRadarTrap}: {report.trap.label}
          </p>
        ) : null}

        <div className="grid grid-cols-2 gap-1.5">
          <Metric
            label={ar.netFlow}
            value={formatMoney(report.net_flow)}
            tone={positive ? "up" : negative ? "down" : "flat"}
          />
          <Metric label={ar.atr} value={priceText(report.atr)} />
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

        {report.exit && report.suggested_exit != null ? (
          <p className="text-sm font-semibold text-amber-200">
            {ar.exitPriceLabel}:{" "}
            <span dir="ltr" className="font-mono">
              {formatPrice(report.suggested_exit)}
            </span>
          </p>
        ) : null}

        <p className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-zinc-500">
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
          <ul className="space-y-0.5 text-[11px] leading-4 text-zinc-400">
            {report.reasons.slice(0, 2).map((reason) => (
              <li key={reason}>• {reason}</li>
            ))}
          </ul>
        ) : null}

        <p className="text-[10px] text-zinc-600">
          {report.session_label ? `${report.session_label} · ` : ""}
          {source === "cached" ? ar.liveRadarCached : ar.liveRadarSource}
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
    <section className="mt-2 rounded-lg border border-zinc-800 bg-zinc-950/40 px-2 py-1.5">
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
        <DossierMetric label={ar.dossierShariah} value={shariah} valueClass={tone} />
        <DossierMetric label={ar.dossierPe} value={fixed(dossier.peRatio, 2)} state={dossier.peState} />
        <DossierMetric
          label={ar.dossierDebt}
          value={dossier.debtToMarket == null ? "" : `${(dossier.debtToMarket * 100).toFixed(1)}%`}
          state={dossier.debtState}
        />
        <DossierMetric
          label={ar.dossierYield}
          value={dossier.dividendYieldPct == null ? "" : `${fixed(dossier.dividendYieldPct, 2)}%`}
          state={dossier.yieldState}
        />
        <DossierMetric label={ar.dossierHealth} value={fixed(dossier.healthScore, 1)} state={dossier.healthState} />
        <DossierMetric label={ar.dossierLiquidity} value={fixed(dossier.liquidityScore, 1)} state={dossier.liquidityState} />
        <DossierMetric label={ar.dossierFair} value={dossier.fairValue == null ? "" : formatPrice(dossier.fairValue)} state={dossier.fairState} />
      </div>
      <ValuationBadge stance={stance} />
    </section>
  );
}

function ValuationBadge({ stance }: { stance: ReturnType<typeof valuationStance> }) {
  if (stance === "pending") {
    return <p className="mt-1 text-[10px] text-zinc-600">{ar.valuationPending}</p>;
  }
  const tone = stance === "over" ? "text-orange-200" : stance === "attractive" ? "text-emerald-200" : "text-zinc-400";
  const label = stance === "over" ? ar.valuationOver : stance === "attractive" ? ar.valuationAttractive : ar.valuationNear;
  return <p className={`mt-1 text-[11px] leading-4 ${tone}`}>{label}</p>;
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
    <div className="flex items-baseline justify-between gap-2 py-0.5">
      <p className="text-[11px] text-zinc-500">{label}</p>
      <p
        dir={missing ? "rtl" : "ltr"}
        className={
          missing
            ? "text-[10px] font-normal leading-4 text-zinc-600"
            : `font-mono text-xs font-semibold text-zinc-100 ${valueClass ?? ""}`
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
    <div className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-2 py-1.5">
      <p className="text-[10px] text-zinc-500">{label}</p>
      <p dir="ltr" className={`mt-0.5 text-xs ${color}`}>
        {value}
      </p>
    </div>
  );
}

export default LiquidityRadarCard;
