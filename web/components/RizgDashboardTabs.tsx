"use client";

import { Suspense, useCallback, useEffect, useId, useMemo, type KeyboardEvent } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { AuthControls } from "@/components/AuthControls";
import { CloseRecommendationIcon } from "@/components/CloseRecommendationIcon";
import { DailyLiquidityCard } from "@/components/DailyLiquidityCard";
import { ThemeToggle } from "@/components/ThemeToggle";
import { LiquidityRadarCard } from "@/components/LiquidityRadarCard";
import { RankingRevealCard } from "@/components/RankingRevealCard";
import { RecommendationsCard } from "@/components/RecommendationsCard";
import { RizgLogo } from "@/components/RizgLogo";
import { SectorHeatmapCard } from "@/components/SectorHeatmapCard";
import { TasiSchedulerChip } from "@/components/TasiSchedulerChip";
import { TickChartSyncChip } from "@/components/TickChartSyncChip";
import { UnderWatchBanner, UnderWatchSection, WatchPulse } from "@/components/UnderWatchSection";
import { ShariahFilterBar } from "@/components/ShariahFilterBar";
import { DividendsCalendarCard } from "@/components/DividendsCalendarCard";
import { PreOpenCard } from "@/components/PreOpenCard";
import NotificationCenter from "./NotificationCenter";
import { useMarketRadarList } from "@/hooks/useMarketRadarList";
import { useUnderWatch } from "@/hooks/useUnderWatch";
import { useDividends } from "@/hooks/useDividends";
import { usePreOpen } from "@/hooks/usePreOpen";
import { listedNameFor } from "@/lib/listedCompanies";
import { parseShariahFilter, passesShariahFilter } from "@/lib/shariah";
import { useTasiTone } from "@/hooks/useTasiTone";
import { useTasiSession } from "@/hooks/useTasiSession";
import { ar } from "@/lib/ar";

type DashboardTab = "preopen" | "sectors" | "radar" | "flow" | "recommendations" | "ranking" | "dividends";

function parseTab(value: string | null): DashboardTab {
  if (
    value === "preopen" ||
    value === "radar" ||
    value === "flow" ||
    value === "recommendations" ||
    value === "ranking" ||
    value === "sectors" ||
    value === "dividends"
  ) {
    return value;
  }
  return "sectors";
}

function DashboardShell() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { tone } = useTasiTone();
  const { live: sessionLive } = useTasiSession();
  const tablistId = useId();
  const activeTab = parseTab(searchParams.get("tab"));
  const selectedSector = searchParams.get("sector");
  const radarSymbol = searchParams.get("symbol");
  const radarName = searchParams.get("name");
  const { companies: radarCards, addCompany, removeCompany, ready: radarReady } = useMarketRadarList();
  const { rows: underWatchRows, loading: underWatchLoading } = useUnderWatch();
  const shariahFilter = parseShariahFilter(searchParams.get("shariah"));
  const { rows: dividendRows, hint: dividendHint, asOf: dividendAsOf, error: dividendError, loading: dividendLoading } =
    useDividends(shariahFilter === "pure");
  const { payload: preopenPayload, loading: preopenLoading, error: preopenError } = usePreOpen();
  const visibleRadarCards = useMemo(
    () => radarCards.filter((item) => passesShariahFilter(item.symbol, shariahFilter)),
    [radarCards, shariahFilter],
  );
  const visibleWatchRows = useMemo(
    () => underWatchRows.filter((row) => passesShariahFilter(row.symbol, shariahFilter)),
    [shariahFilter, underWatchRows],
  );
  const tabs = useMemo(
    () =>
      [
        { id: "preopen" as const, label: ar.tabsPreopen, icon: "🌅" },
        { id: "sectors" as const, label: ar.tabsSectors, icon: "🌐" },
        { id: "radar" as const, label: ar.tabsRadar, icon: "⚡" },
        { id: "flow" as const, label: ar.tabsFlow, icon: "💧" },
        {
          id: "recommendations" as const,
          label: sessionLive ? ar.recoButtonLive : ar.recoButtonEod,
          icon: sessionLive ? "⚡" : "🎯",
        },
        { id: "dividends" as const, label: ar.tabsDividends, icon: "💰" },
        { id: "ranking" as const, label: ar.tabsRanking, icon: "🏰" },
      ] satisfies { id: DashboardTab; label: string; icon: string }[],
    [sessionLive],
  );

  const replaceQuery = useCallback(
    (patch: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (!value) params.delete(key);
        else params.set(key, value);
      }
      const query = params.toString();
      router.replace(query ? `${pathname}?${query}` : pathname || "/", { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const setActiveTab = useCallback(
    (id: DashboardTab) => {
      if (id === "sectors") {
        replaceQuery({ tab: "sectors", symbol: null, name: null });
        return;
      }
      replaceQuery({ tab: id, sector: null, symbol: null, name: null });
    },
    [replaceQuery],
  );

  useEffect(() => {
    if (!radarReady || !radarSymbol) return;
    addCompany({ symbol: radarSymbol, name: listedNameFor(radarSymbol) || radarName || radarSymbol });
  }, [addCompany, radarName, radarReady, radarSymbol]);

  const removeRadarCompany = useCallback(
    (symbol: string) => {
      removeCompany(symbol);
      if (radarSymbol?.toUpperCase() === symbol.toUpperCase()) {
        replaceQuery({ symbol: null, name: null });
      }
    },
    [radarSymbol, removeCompany, replaceQuery],
  );

  const openWatchedCompany = useCallback(
    (company: { symbol: string; name: string }) => {
      addCompany(company);
      replaceQuery({ tab: "radar", symbol: company.symbol, name: company.name, sector: null });
    },
    [addCompany, replaceQuery],
  );

  const onTabKeyDown = useCallback(
    (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight" && event.key !== "Home" && event.key !== "End") {
        return;
      }
      event.preventDefault();
      const last = tabs.length - 1;
      let next = index;
      if (event.key === "Home") next = 0;
      else if (event.key === "End") next = last;
      else if (event.key === "ArrowLeft") next = index === last ? 0 : index + 1;
      else next = index === 0 ? last : index - 1;
      setActiveTab(tabs[next].id);
      document.getElementById(`${tablistId}-${tabs[next].id}`)?.focus();
    },
    [setActiveTab, tablistId, tabs],
  );

  return (
    <section className="mx-auto flex w-full max-w-7xl flex-col items-center gap-6 px-4 pb-6 pt-10 text-center text-zinc-100 sm:px-6 lg:px-8">
      <NotificationCenter />
      <div className="flex w-full flex-col items-center gap-4 rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-5 text-center shadow-glow backdrop-blur-md sm:p-6">
        <div className="flex flex-col items-center">
          <RizgLogo iconClassName="h-12 w-12 sm:h-14 sm:w-14" tone={tone} />
          <h1 className="mt-3 bg-gradient-to-l from-sky-400 to-teal-400 bg-clip-text text-2xl font-black text-transparent">
            {ar.tabsTitle}
          </h1>
        </div>
        <div className="flex w-full flex-col items-center gap-3">
          <div className="flex flex-wrap items-center justify-center gap-3">
            <ThemeToggle />
            <TasiSchedulerChip />
            <AuthControls />
          </div>
          <TickChartSyncChip
            onFollow={(company) => {
              addCompany(company);
              replaceQuery({ tab: "radar", symbol: company.symbol, name: null, sector: null });
            }}
          />
        </div>
      </div>

      <div
        role="tablist"
        aria-label={ar.tabsTitle}
        className="flex w-full flex-wrap items-center justify-center gap-2 border-b border-zinc-800 pb-4"
      >
        {tabs.map((tab, index) => {
          const selected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              id={`${tablistId}-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`${tablistId}-panel-${tab.id}`}
              aria-label={tab.label}
              tabIndex={selected ? 0 : -1}
              onClick={() => setActiveTab(tab.id)}
              onKeyDown={(event) => onTabKeyDown(event, index)}
              className={`flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-bold transition-all ${
                tab.id === "preopen"
                  ? selected
                    ? "bg-amber-200 text-amber-950 shadow-lg shadow-amber-900/30"
                    : "border border-amber-400/40 bg-amber-500/15 text-amber-100 hover:bg-amber-500/25 hover:text-amber-50"
                  : tab.id === "flow"
                  ? selected
                    ? "bg-teal-100 text-teal-900 shadow-lg shadow-teal-900/20"
                    : "border border-teal-500/30 bg-teal-500/10 text-teal-200 hover:bg-teal-500/20 hover:text-teal-100"
                  : tab.id === "recommendations"
                  ? selected
                    ? sessionLive
                      ? "bg-sky-100 text-sky-900 shadow-lg shadow-sky-900/20"
                      : "bg-emerald-100 text-emerald-900 shadow-lg shadow-emerald-900/20"
                    : sessionLive
                      ? "border border-sky-500/30 bg-sky-500/10 text-sky-200 hover:bg-sky-500/20 hover:text-sky-100"
                      : "border border-emerald-500/30 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20 hover:text-emerald-100"
                  : selected
                    ? "bg-sky-600 text-white shadow-lg shadow-sky-900/30"
                    : "border border-zinc-800 bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
              }`}
            >
              {tab.id === "recommendations" && !sessionLive ? (
                <CloseRecommendationIcon className="h-5 w-5 shrink-0" />
              ) : tab.id === "radar" && visibleWatchRows.length ? (
                <WatchPulse explosive={visibleWatchRows.some((row) => row.explosive)} />
              ) : tab.id === "preopen" && preopenPayload?.in_window ? (
                <span className="relative flex h-2.5 w-2.5" aria-hidden="true">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-300 opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-300" />
                </span>
              ) : (
                <span aria-hidden="true">{tab.icon}</span>
              )}
              {tab.label}
            </button>
          );
        })}
      </div>

      {activeTab !== "radar" ? (
        <UnderWatchBanner
          count={visibleWatchRows.length}
          onOpen={() => setActiveTab("radar")}
        />
      ) : null}

      <ShariahFilterBar
        value={shariahFilter}
        onChange={(next) => replaceQuery({ shariah: next === "pure" ? "pure" : null })}
      />

      <div
        id={`${tablistId}-panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`${tablistId}-${activeTab}`}
        className="w-full animate-fadeIn"
      >
        {activeTab === "preopen" ? (
          <PreOpenCard
            payload={preopenPayload}
            loading={preopenLoading}
            error={preopenError}
            shariahFilter={shariahFilter}
            onOpenSymbol={openWatchedCompany}
          />
        ) : null}

        {activeTab === "sectors" ? (
          <SectorHeatmapCard
            selectedSector={selectedSector}
            radarSymbol={radarSymbol}
            radarName={radarName}
            shariahFilter={shariahFilter}
            onSelectSector={(sector) => replaceQuery({ tab: "sectors", sector, symbol: null, name: null })}
            onOpenRadar={(company) =>
              replaceQuery({
                tab: "sectors",
                sector: selectedSector,
                symbol: company?.symbol ?? null,
                name: company?.name ?? null,
              })
            }
          />
        ) : null}

        {activeTab === "radar" ? (
          <div className="space-y-4">
            <UnderWatchSection
              rows={visibleWatchRows}
              loading={underWatchLoading}
              onOpen={openWatchedCompany}
            />
            <div className="text-center">
              <h3 className="text-lg font-bold text-zinc-100">{ar.marketRadarTitle}</h3>
              <p className="mt-1 text-xs text-zinc-400">{ar.marketRadarHint}</p>
            </div>
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              {radarCards.length === 0 ? (
                <p className="text-center text-sm text-zinc-500 lg:col-span-2">{ar.marketRadarEmpty}</p>
              ) : visibleRadarCards.length === 0 ? (
                <p className="text-center text-sm text-zinc-500 lg:col-span-2">{ar.shariahFilterEmpty}</p>
              ) : (
                visibleRadarCards.map((item) => (
                  <LiquidityRadarCard
                    key={item.symbol}
                    symbol={item.symbol}
                    symbolName={item.symbolName}
                    onRemove={() => removeRadarCompany(item.symbol)}
                  />
                ))
              )}
            </div>
          </div>
        ) : null}

        {activeTab === "flow" ? (
          <DailyLiquidityCard
            shariahFilter={shariahFilter}
            onOpenSymbol={(company) => {
              addCompany(company);
              replaceQuery({ tab: "radar", symbol: company.symbol, name: company.name, sector: null });
            }}
          />
        ) : null}

        {activeTab === "recommendations" ? (
          <div className="space-y-6">
            <RecommendationsCard shariahFilter={shariahFilter} />
          </div>
        ) : null}

        {activeTab === "dividends" ? (
          <DividendsCalendarCard
            rows={dividendRows}
            loading={dividendLoading}
            error={dividendError}
            hint={dividendHint}
            asOf={dividendAsOf}
            onOpen={openWatchedCompany}
          />
        ) : null}

        {activeTab === "ranking" ? <RankingRevealCard shariahFilter={shariahFilter} /> : null}
      </div>
    </section>
  );
}

export function RizgDashboardTabs() {
  return (
    <Suspense
      fallback={
        <section className="mx-auto max-w-7xl px-4 py-10 text-sm text-zinc-500">{ar.heatmapLoading}</section>
      }
    >
      <DashboardShell />
    </Suspense>
  );
}

export default RizgDashboardTabs;
