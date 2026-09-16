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
import NotificationCenter from "./NotificationCenter";
import { useMarketRadarList } from "@/hooks/useMarketRadarList";
import { listedNameFor } from "@/lib/listedCompanies";
import { useTasiTone } from "@/hooks/useTasiTone";
import { useTasiSession } from "@/hooks/useTasiSession";
import { ar } from "@/lib/ar";

type DashboardTab = "sectors" | "radar" | "flow" | "recommendations" | "ranking";

function parseTab(value: string | null): DashboardTab {
  if (value === "radar" || value === "flow" || value === "recommendations" || value === "ranking" || value === "sectors") {
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
  const tabs = useMemo(
    () =>
      [
        { id: "sectors" as const, label: ar.tabsSectors, icon: "🌐" },
        { id: "radar" as const, label: ar.tabsRadar, icon: "⚡" },
        { id: "flow" as const, label: ar.tabsFlow, icon: "💧" },
        {
          id: "recommendations" as const,
          label: sessionLive ? ar.recoButtonLive : ar.recoButtonEod,
          icon: sessionLive ? "⚡" : "🎯",
        },
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
    <section className="mx-auto flex w-full max-w-7xl flex-col items-center gap-6 px-4 pb-6 pt-24 text-center text-zinc-100 sm:px-6 lg:px-8">
      <NotificationCenter />
      <div className="flex w-full flex-col items-center gap-4 rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-5 text-center shadow-glow backdrop-blur-md sm:p-6">
        <div className="flex flex-col items-center">
          <RizgLogo iconClassName="h-12 w-12 sm:h-14 sm:w-14" tone={tone} />
          <h1 className="mt-3 bg-gradient-to-l from-sky-400 to-teal-400 bg-clip-text text-2xl font-black text-transparent">
            {ar.tabsTitle}
          </h1>
          <p className="mt-1 text-xs text-zinc-400">{ar.tabsWelcome}</p>
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
                tab.id === "flow"
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
              ) : (
                <span aria-hidden="true">{tab.icon}</span>
              )}
              {tab.label}
            </button>
          );
        })}
      </div>

      <div
        id={`${tablistId}-panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`${tablistId}-${activeTab}`}
        className="w-full animate-fadeIn"
      >
        {activeTab === "sectors" ? (
          <SectorHeatmapCard
            selectedSector={selectedSector}
            radarSymbol={radarSymbol}
            radarName={radarName}
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
            <div className="text-center">
              <h3 className="text-lg font-bold text-zinc-100">{ar.marketRadarTitle}</h3>
              <p className="mt-1 text-xs text-zinc-400">{ar.marketRadarHint}</p>
            </div>
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              {radarCards.length === 0 ? (
                <p className="text-center text-sm text-zinc-500 lg:col-span-2">{ar.marketRadarEmpty}</p>
              ) : (
                radarCards.map((item) => (
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
            onOpenSymbol={(company) => {
              addCompany(company);
              replaceQuery({ tab: "radar", symbol: company.symbol, name: company.name, sector: null });
            }}
          />
        ) : null}

        {activeTab === "recommendations" ? (
          <div className="space-y-6">
            <RecommendationsCard />
          </div>
        ) : null}

        {activeTab === "ranking" ? <RankingRevealCard /> : null}
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
