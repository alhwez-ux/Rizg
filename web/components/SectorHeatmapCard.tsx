"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { LiquidityRadarCard } from "@/components/LiquidityRadarCard";
import { ar } from "@/lib/ar";
import { formatMoney } from "@/lib/liquidity";
import {
  fetchSectorCompanies,
  fetchSectorRotation,
  type SectorCompany,
  type SectorData,
} from "@/lib/sectorRotation";

export function SectorHeatmapCard() {
  const [sectors, setSectors] = useState<SectorData[]>([]);
  const [selectedSector, setSelectedSector] = useState<string | null>(null);
  const [companies, setCompanies] = useState<SectorCompany[]>([]);
  const [loadingSectors, setLoadingSectors] = useState(true);
  const [loadingCompanies, setLoadingCompanies] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [companyError, setCompanyError] = useState<string | null>(null);
  const [activeSymbolForRadar, setActiveSymbolForRadar] = useState<{
    symbol: string;
    name: string;
  } | null>(null);
  const requestId = useRef(0);
  const radarRef = useRef<HTMLDivElement | null>(null);

  const loadSectors = useCallback(async (silent = false) => {
    if (!silent) setLoadingSectors(true);
    try {
      const result = await fetchSectorRotation();
      if (result.success) {
        setSectors(result.sectors);
        setError(null);
      } else {
        throw new Error(ar.heatmapLoadError);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : ar.heatmapLoadError);
    } finally {
      setLoadingSectors(false);
    }
  }, []);

  useEffect(() => {
    void loadSectors();
    const interval = window.setInterval(() => {
      void loadSectors(true);
    }, 120_000);
    return () => window.clearInterval(interval);
  }, [loadSectors]);

  const handleSectorClick = async (sectorName: string) => {
    const ticket = ++requestId.current;
    setSelectedSector(sectorName);
    setActiveSymbolForRadar(null);
    setLoadingCompanies(true);
    setCompanyError(null);
    setCompanies([]);
    try {
      const result = await fetchSectorCompanies(sectorName);
      if (ticket !== requestId.current) return;
      if (result.success) {
        setSelectedSector(result.sector || sectorName);
        setCompanies(result.companies);
      } else {
        throw new Error(ar.heatmapPanelError);
      }
    } catch (err) {
      if (ticket !== requestId.current) return;
      setCompanyError(err instanceof Error ? err.message : ar.heatmapPanelError);
    } finally {
      if (ticket === requestId.current) setLoadingCompanies(false);
    }
  };

  const handleBack = useCallback(() => {
    requestId.current += 1;
    setSelectedSector(null);
    setCompanies([]);
    setCompanyError(null);
    setLoadingCompanies(false);
    setActiveSymbolForRadar(null);
  }, []);

  const handleBackToCompanies = useCallback(() => {
    setActiveSymbolForRadar(null);
  }, []);

  const openRadar = useCallback((company: SectorCompany) => {
    setActiveSymbolForRadar({ symbol: company.symbol, name: company.name });
  }, []);

  useEffect(() => {
    if (!activeSymbolForRadar) return;
    radarRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [activeSymbolForRadar]);

  useEffect(() => {
    if (!selectedSector) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (activeSymbolForRadar) {
        handleBackToCompanies();
        return;
      }
      handleBack();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeSymbolForRadar, handleBack, handleBackToCompanies, selectedSector]);

  if (loadingSectors && sectors.length === 0) {
    return (
      <section className="animate-pulse rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-6 text-center text-sm text-zinc-400 shadow-glow">
        {ar.heatmapLoading}
      </section>
    );
  }

  if (error && sectors.length === 0) {
    return (
      <section className="rounded-2xl border border-rose-900/50 bg-rose-950/30 p-6 text-center text-sm text-rose-300">
        {ar.heatmapError}: {error}
      </section>
    );
  }

  return (
    <section className="mx-auto max-w-6xl space-y-6 rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-5 text-zinc-100 shadow-glow sm:p-6">
      <div className="flex flex-col items-start justify-between gap-3 border-b border-zinc-800 pb-4 sm:flex-row sm:items-center">
        <div>
          <h2 className="text-xl font-bold text-zinc-50">{ar.heatmapTitle}</h2>
          <p className="mt-1 text-xs text-zinc-500">{ar.heatmapHint}</p>
        </div>
        {selectedSector ? (
          <button
            type="button"
            onClick={handleBack}
            className="rounded-xl bg-zinc-800 px-3 py-1.5 text-xs text-zinc-200 transition hover:bg-zinc-700"
          >
            {ar.heatmapBack}
          </button>
        ) : (
          <span className="rounded-xl bg-zinc-900 px-3 py-1 text-xs font-semibold text-zinc-300">
            {ar.heatmapLive}
          </span>
        )}
      </div>

      {!selectedSector ? (
        sectors.length === 0 ? (
          <p className="text-center text-sm text-zinc-500">{ar.heatmapEmpty}</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {sectors.map((sec) => (
              <SectorTile
                key={sec.sector}
                sector={sec}
                onSelect={() => {
                  void handleSectorClick(sec.sector);
                }}
              />
            ))}
          </div>
        )
      ) : activeSymbolForRadar ? (
        <div ref={radarRef} className="animate-fadeIn space-y-4 scroll-mt-6">
          <div className="flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={handleBackToCompanies}
              className="rounded-xl bg-zinc-800 px-3 py-1 text-xs text-zinc-200 transition hover:bg-zinc-700"
            >
              {ar.heatmapBackToCompanies}
            </button>
            <span className="text-xs text-zinc-400">{ar.heatmapRadarLiveHint}</span>
          </div>
          <LiquidityRadarCard
            symbol={activeSymbolForRadar.symbol}
            symbolName={activeSymbolForRadar.name}
          />
        </div>
      ) : (
        <CompanyTable
          sector={selectedSector}
          companies={companies}
          loading={loadingCompanies}
          error={companyError}
          onSelectCompany={openRadar}
        />
      )}
    </section>
  );
}

function SectorTile({
  sector,
  onSelect,
}: {
  sector: SectorData;
  onSelect: () => void;
}) {
  const isPositive = sector.sector_momentum_score > 0;
  const cardBg = isPositive
    ? "bg-emerald-950/20 border-emerald-500/30 hover:border-emerald-500/80 hover:bg-emerald-950/30"
    : "bg-rose-950/20 border-rose-500/30 hover:border-rose-500/80 hover:bg-rose-950/30";
  const badgeBg = isPositive
    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-400"
    : "border-rose-500/20 bg-rose-500/10 text-rose-400";

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex cursor-pointer flex-col justify-between rounded-2xl border p-5 text-start shadow-lg transition-all ${cardBg}`}
    >
      <div>
        <div className="mb-3 flex items-start justify-between gap-2">
          <h3 className="text-lg font-bold text-zinc-100">{sector.sector}</h3>
          <span className={`rounded-xl border px-2.5 py-1 text-[11px] font-semibold ${badgeBg}`}>
            {sector.status}
          </span>
        </div>
        <div className="my-3 space-y-2 text-xs text-zinc-300">
          <div className="flex justify-between gap-3">
            <span className="text-zinc-400">{ar.heatmapAvgChange}</span>
            <span
              className={`font-bold ${sector.avg_price_change >= 0 ? "text-emerald-400" : "text-rose-400"}`}
              dir="ltr"
            >
              {sector.avg_price_change >= 0 ? "+" : ""}
              {sector.avg_price_change.toFixed(2)}%
            </span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-zinc-400">{ar.heatmapValue}</span>
            <span className="font-semibold text-zinc-200" dir="ltr">
              {(sector.total_value_traded / 1_000_000).toLocaleString("en-US", {
                maximumFractionDigits: 1,
              })}{" "}
              {ar.heatmapMillion}
            </span>
          </div>
        </div>
      </div>
      <div className="mt-2 flex items-center justify-between border-t border-zinc-800/60 pt-3 text-[11px] font-semibold text-sky-400">
        <span>{ar.heatmapClickCta}</span>
        <span aria-hidden="true">🔍</span>
      </div>
    </button>
  );
}

function CompanyTable({
  sector,
  companies,
  loading,
  error,
  onSelectCompany,
}: {
  sector: string;
  companies: SectorCompany[];
  loading: boolean;
  error: string | null;
  onSelectCompany: (company: SectorCompany) => void;
}) {
  return (
    <div className="animate-fadeIn space-y-4">
      <div className="flex items-center justify-between rounded-xl border border-zinc-800 bg-zinc-950 p-4">
        <h3 className="text-lg font-bold text-sky-400">
          {ar.heatmapPanelTitle}: {sector} ({ar.heatmapCompaniesHint})
        </h3>
        <span className="text-xs text-zinc-400">
          {companies.length} {ar.heatmapCompaniesUnit}
        </span>
      </div>

      {loading ? (
        <div className="animate-pulse p-8 text-center text-zinc-400">{ar.heatmapPanelLoading}</div>
      ) : error ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </p>
      ) : companies.length === 0 ? (
        <p className="py-8 text-center text-sm text-zinc-500">{ar.heatmapPanelEmpty}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[780px] border-collapse text-start">
            <thead>
              <tr className="border-b border-zinc-800 text-xs text-zinc-400">
                <th className="p-3 font-medium">{ar.heatmapColSymbol}</th>
                <th className="p-3 font-medium">{ar.heatmapColCompany}</th>
                <th className="p-3 font-medium">{ar.heatmapColChange}</th>
                <th className="p-3 font-medium">{ar.heatmapColNetFlow}</th>
                <th className="p-3 font-medium">{ar.heatmapColValue}</th>
                <th className="p-3 text-center font-medium">{ar.heatmapColAction}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60 text-sm">
              {companies.map((comp) => (
                <tr
                  key={comp.symbol}
                  tabIndex={0}
                  onClick={() => onSelectCompany(comp)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelectCompany(comp);
                    }
                  }}
                  className="group cursor-pointer transition-colors hover:bg-zinc-800/50 focus:bg-zinc-800/50 focus:outline-none focus:ring-2 focus:ring-sky-500/40"
                >
                  <td className="p-3 font-mono font-bold text-sky-300" dir="ltr">
                    {comp.symbol}
                  </td>
                  <td className="p-3 font-bold text-zinc-100 transition-colors group-hover:text-sky-400">
                    {comp.name}
                  </td>
                  <td
                    className={`p-3 font-bold ${comp.price_change_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                    dir="ltr"
                  >
                    {comp.price_change_pct >= 0 ? "+" : ""}
                    {comp.price_change_pct.toFixed(2)}%
                  </td>
                  <td
                    className={`p-3 font-mono ${comp.net_flow > 0 ? "text-emerald-400" : comp.net_flow < 0 ? "text-rose-400" : "text-zinc-300"}`}
                    dir="ltr"
                  >
                    {formatMoney(comp.net_flow)}
                  </td>
                  <td className="p-3 text-zinc-200" dir="ltr">
                    {(comp.value_traded / 1_000_000).toLocaleString("en-US", {
                      maximumFractionDigits: 2,
                    })}{" "}
                    {ar.heatmapMillion}
                  </td>
                  <td className="p-3 text-center">
                    <span className="rounded-lg border border-sky-500/20 bg-sky-500/10 px-2.5 py-1 text-xs font-semibold text-sky-400">
                      {ar.heatmapOpenRadar}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default SectorHeatmapCard;
