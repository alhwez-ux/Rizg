"use client";

import { Suspense, useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { AuthControls } from "@/components/AuthControls";
import { AnalystConsensusCard } from "@/components/AnalystConsensusCard";
import { DailyLiquidityCard } from "@/components/DailyLiquidityCard";
import { DailyOpportunitiesCard } from "@/components/DailyOpportunitiesCard";
import { ThemeToggle } from "@/components/ThemeToggle";
import { InstallAppButton } from "@/components/InstallAppButton";
import { LiquidityRadarCard } from "@/components/LiquidityRadarCard";
import { RankingRevealCard } from "@/components/RankingRevealCard";
import { RecommendationsCard } from "@/components/RecommendationsCard";
import { RizgLogo } from "@/components/RizgLogo";
import { SectorHeatmapCard } from "@/components/SectorHeatmapCard";
import { TickChartSyncChip } from "@/components/TickChartSyncChip";
import { DashboardControlPanel } from "@/components/DashboardControlPanel";
import { TasiIndexBadge } from "@/components/TasiIndexBadge";
import { InstitutionalMatrix } from "@/components/InstitutionalMatrix";
import { UnderWatchBanner, UnderWatchSection, WatchPulse } from "@/components/UnderWatchSection";
import { ShariahFilterBar } from "@/components/ShariahFilterBar";
import { DividendsCalendarCard } from "@/components/DividendsCalendarCard";
import { PreOpenCard } from "@/components/PreOpenCard";
import { SmartMoneyCard } from "@/components/SmartMoneyCard";
import { RecoveryCard } from "@/components/RecoveryCard";
import NotificationCenter from "./NotificationCenter";
import { useAnalystConsensus } from "@/hooks/useAnalystConsensus";
import { useDailyOpportunities } from "@/hooks/useDailyOpportunities";
import { useMarketRadarList } from "@/hooks/useMarketRadarList";
import { useUnderWatch } from "@/hooks/useUnderWatch";
import { useTapeLastPrices } from "@/hooks/useTapeLastPrices";
import { useDividends } from "@/hooks/useDividends";
import { usePreOpen } from "@/hooks/usePreOpen";
import { useSmartMoney } from "@/hooks/useSmartMoney";
import { listedNameFor } from "@/lib/listedCompanies";
import { holdDisplayedRows, nextDisplayWake, type HeldRow } from "@/lib/radarHold";
import type { UnderWatchRow } from "@/lib/underWatch";
import { parseShariahFilter, passesShariahFilter } from "@/lib/shariah";
import { useTasiTone } from "@/hooks/useTasiTone";
import { useDashboardVisibility } from "@/hooks/useDashboardVisibility";
import { ar } from "@/lib/ar";

type PrimaryTab = "home" | "opportunities" | "tools";
type ToolId = "preopen" | "funds" | "analysts" | "recovery" | "dividends" | "ranking";

const toolVisibility: Record<ToolId, "toolPreopen" | "toolFunds" | "toolAnalysts" | "toolRecovery" | "toolDividends" | "toolRanking"> = {
  preopen: "toolPreopen",
  funds: "toolFunds",
  analysts: "toolAnalysts",
  recovery: "toolRecovery",
  dividends: "toolDividends",
  ranking: "toolRanking",
};

function parseTool(value: string | null): ToolId | null {
  if (
    value === "preopen" ||
    value === "funds" ||
    value === "analysts" ||
    value === "recovery" ||
    value === "dividends" ||
    value === "ranking"
  ) {
    return value;
  }
  return null;
}

function parseView(tab: string | null, section: string | null): { primary: PrimaryTab; tool: ToolId | null } {
  if (tab === "daily" || tab === "opportunities" || section === "recommendations" || section === "flow") {
    return { primary: "opportunities", tool: null };
  }
  const tool = parseTool(tab) || parseTool(section);
  if (tool) return { primary: "tools", tool };
  if (tab === "tools") return { primary: "tools", tool: "preopen" };
  return { primary: "home", tool: null };
}

function DashboardShell() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { tone } = useTasiTone();
  const { map: visible, toggle: toggleVisible, reset: resetVisible } = useDashboardVisibility();
  const tablistId = useId();
  const view = parseView(searchParams.get("tab"), searchParams.get("section"));
  const activeTab = view.primary;
  const activeTool = view.tool;
  const selectedSector = searchParams.get("sector");
  const radarSymbol = searchParams.get("symbol");
  const radarName = searchParams.get("name");
  const { companies: radarCards, addCompany, removeCompany, ready: radarReady } = useMarketRadarList();
  const { rows: underWatchRows } = useUnderWatch();
  const heldWatchRef = useRef<HeldRow<UnderWatchRow>[]>([]);
  const [watchHoldTick, setWatchHoldTick] = useState(0);
  const shariahFilter = parseShariahFilter(searchParams.get("shariah"));
  const { rows: dividendRows, hint: dividendHint, asOf: dividendAsOf, error: dividendError, loading: dividendLoading } =
    useDividends(shariahFilter === "pure");
  const { payload: preopenPayload, loading: preopenLoading, error: preopenError } = usePreOpen();
  const { payload: fundsPayload, loading: fundsLoading, error: fundsError } = useSmartMoney();
  const { payload: dailyPayload, loading: dailyLoading, error: dailyError } = useDailyOpportunities(shariahFilter === "pure");
  const { payload: analystPayload, loading: analystLoading, error: analystError } = useAnalystConsensus(shariahFilter === "pure");
  const visibleRadarCards = useMemo(
    () => radarCards.filter((item) => passesShariahFilter(item.symbol, shariahFilter)),
    [radarCards, shariahFilter],
  );
  const visibleWatchRows = useMemo(() => {
    const incoming = underWatchRows.filter((row) => passesShariahFilter(row.symbol, shariahFilter));
    const fresh = new Map(incoming.map((row) => [row.symbol, row]));
    const eligible = heldWatchRef.current.filter((item) => passesShariahFilter(item.symbol, shariahFilter));
    const held = holdDisplayedRows(eligible, incoming, Date.now(), undefined, Number.POSITIVE_INFINITY);
    const next = held.map((item) => {
      const live = fresh.get(item.symbol);
      if (!live) return item;
      return { ...item, row: { ...item.row, price: live.price, change_percent: live.change_percent } };
    });
    heldWatchRef.current = next;
    return next.map((item) => item.row);
  }, [shariahFilter, underWatchRows, watchHoldTick]);
  const [watchOpen, setWatchOpen] = useState(false);
  const [watchSnapshot, setWatchSnapshot] = useState<UnderWatchRow[]>([]);
  const watchSymbols = useMemo(() => (watchOpen ? watchSnapshot.map((row) => row.symbol) : []), [watchOpen, watchSnapshot]);
  const watchPrices = useTapeLastPrices(watchSymbols);
  const watchRows = useMemo(
    () =>
      watchSnapshot.map((row) => ({
        ...row,
        price: watchPrices.get(row.symbol.toUpperCase()) ?? row.price,
      })),
    [watchPrices, watchSnapshot],
  );
  const place = `${activeTab}:${activeTool ?? ""}`;
  const placeRef = useRef(place);
  const tabs = useMemo(
    () =>
      [
        { id: "home" as const, label: ar.tabsHome, icon: "💧" },
        { id: "opportunities" as const, label: ar.tabsOpportunities, icon: "⚡" },
        { id: "tools" as const, label: ar.tabsTools, icon: "🧰" },
      ] satisfies { id: PrimaryTab; label: string; icon: string }[],
    [],
  );
  const tools = useMemo(
    () =>
      [
        { id: "preopen" as const, label: ar.tabsPreopen },
        { id: "funds" as const, label: ar.homeFunds },
        { id: "analysts" as const, label: ar.tabsAnalysts },
        { id: "recovery" as const, label: ar.tabsRecovery },
        { id: "dividends" as const, label: ar.tabsDividends },
        { id: "ranking" as const, label: ar.homeRanking },
      ] satisfies { id: ToolId; label: string }[],
    [],
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

  const closeWatch = useCallback(() => {
    setWatchOpen(false);
    setWatchSnapshot([]);
  }, []);

  const setActiveTab = useCallback(
    (id: PrimaryTab) => {
      closeWatch();
      if (id === "home") {
        replaceQuery({ tab: null, section: null, symbol: null, name: null });
        return;
      }
      if (id === "opportunities") {
        replaceQuery({ tab: "opportunities", section: null, sector: null, symbol: null, name: null });
        return;
      }
      replaceQuery({ tab: "tools", section: activeTool ?? "preopen", sector: null, symbol: null, name: null });
    },
    [activeTool, closeWatch, replaceQuery],
  );

  const revealWatch = useCallback(() => {
    if (visibleWatchRows.length === 0) return;
    setWatchSnapshot(visibleWatchRows);
    setWatchOpen(true);
  }, [visibleWatchRows]);

  useEffect(() => {
    const wait = nextDisplayWake(heldWatchRef.current, Date.now());
    if (wait == null) return;
    const timer = window.setTimeout(() => setWatchHoldTick((value) => value + 1), Math.max(wait, 0) + 30);
    return () => window.clearTimeout(timer);
  }, [visibleWatchRows]);

  useEffect(() => {
    if (placeRef.current === place) return;
    placeRef.current = place;
    setWatchOpen(false);
    setWatchSnapshot([]);
  }, [place]);

  const setTool = useCallback(
    (id: ToolId) => {
      closeWatch();
      replaceQuery({ tab: "tools", section: id, sector: null, symbol: null, name: null });
    },
    [closeWatch, replaceQuery],
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
      closeWatch();
      addCompany(company);
      replaceQuery({ tab: null, section: null, symbol: company.symbol, name: company.name, sector: null });
    },
    [addCompany, closeWatch, replaceQuery],
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
      {visible.notifications ? <NotificationCenter /> : null}
      <div className="flex w-full flex-col items-center gap-4 rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-5 text-center shadow-glow backdrop-blur-md sm:p-6">
        <div className="flex items-center gap-3">
          <RizgLogo iconClassName="h-12 w-12 sm:h-14 sm:w-14" withWordmark={false} title={ar.brand} tone={tone} />
          <h1 className="text-3xl font-black tracking-wide text-zinc-50">{ar.brand}</h1>
        </div>
          <DashboardControlPanel
            map={visible}
            onToggle={toggleVisible}
            onReset={resetVisible}
            trailing={<TasiIndexBadge />}
          />
        <div className="flex w-full flex-col items-center gap-3">
          <div className="flex flex-wrap items-center justify-center gap-3">
            {visible.shariah ? (
              <ShariahFilterBar
                value={shariahFilter}
                onChange={(next) => replaceQuery({ shariah: next === "pure" ? "pure" : null })}
              />
            ) : null}
            {visible.theme ? <ThemeToggle /> : null}
            {visible.install ? <InstallAppButton /> : null}
            {visible.auth ? <AuthControls /> : null}
          </div>
          <TickChartSyncChip
            showStream={visible.stream}
            showSearch={visible.search}
            showSession={visible.sessionRow}
            showStamp={visible.lastUpdate}
            onFollow={(company) => {
              closeWatch();
              addCompany(company);
              replaceQuery({ tab: null, section: null, symbol: company.symbol, name: null, sector: null });
            }}
          />
        </div>
      </div>

      {visible.tabs ? (
      <div
        role="tablist"
        aria-label={ar.brand}
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
              className={`flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-bold transition-colors ${
                selected
                  ? "bg-sky-600 text-white shadow-lg shadow-sky-900/30"
                  : "border border-zinc-800 bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"
              }`}
            >
              {tab.id === "home" && visibleWatchRows.length ? (
                <WatchPulse
                  explosive={visibleWatchRows.some((row) => row.explosive)}
                  hidden={visibleWatchRows.some((row) => row.hidden_accumulation)}
                />
              ) : tab.id === "tools" && preopenPayload?.in_window ? (
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
      ) : null}

      {visible.underWatch && visibleWatchRows.length ? (
        <UnderWatchBanner count={visibleWatchRows.length} active={watchOpen} onOpen={revealWatch} />
      ) : null}

      <div
        id={`${tablistId}-panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`${tablistId}-${activeTab}`}
        className="w-full animate-fadeIn"
      >
        {watchOpen && activeTab !== "home" ? (
          <UnderWatchSection rows={watchRows} onClose={closeWatch} />
        ) : null}

        {!watchOpen && activeTab === "opportunities" ? (
          <div className="space-y-6">
            <p className="text-center text-xs text-zinc-400">{ar.opportunitiesHint}</p>
            {visible.opportunitiesDaily ? (
              <DailyOpportunitiesCard
                payload={dailyPayload}
                loading={dailyLoading}
                error={dailyError}
                onOpenSymbol={openWatchedCompany}
              />
            ) : null}
            {visible.opportunitiesReco ? <RecommendationsCard shariahFilter={shariahFilter} /> : null}
            {visible.opportunitiesFlow ? (
              <DailyLiquidityCard
                shariahFilter={shariahFilter}
                onOpenSymbol={(company) => {
                  closeWatch();
                  addCompany(company);
                  replaceQuery({ tab: null, section: null, symbol: company.symbol, name: company.name, sector: null });
                }}
              />
            ) : null}
          </div>
        ) : null}

        {!watchOpen && activeTab === "tools" ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-center gap-2">
              {tools.filter((tool) => visible[toolVisibility[tool.id]]).map((tool) => {
                const selected = activeTool === tool.id;
                return (
                  <button
                    key={tool.id}
                    type="button"
                    onClick={() => setTool(tool.id)}
                    className={`inline-flex min-h-10 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-bold transition-colors ${
                      selected
                        ? "bg-zinc-100 text-zinc-950"
                        : "border border-zinc-800 bg-zinc-950 text-zinc-400 hover:text-zinc-100"
                    }`}
                  >
                    {tool.label}
                  </button>
                );
              })}
            </div>
            {activeTool === "preopen" && visible.toolPreopen ? (
              <PreOpenCard
                payload={preopenPayload}
                loading={preopenLoading}
                error={preopenError}
                shariahFilter={shariahFilter}
                onOpenSymbol={openWatchedCompany}
              />
            ) : null}
            {activeTool === "funds" && visible.toolFunds ? (
              <SmartMoneyCard
                payload={fundsPayload}
                loading={fundsLoading}
                error={fundsError}
                shariahFilter={shariahFilter}
                onOpenSymbol={openWatchedCompany}
              />
            ) : null}
            {activeTool === "analysts" && visible.toolAnalysts ? (
              <AnalystConsensusCard
                payload={analystPayload}
                loading={analystLoading}
                error={analystError}
                onOpenSymbol={openWatchedCompany}
              />
            ) : null}
            {activeTool === "recovery" && visible.toolRecovery ? <RecoveryCard shariahFilter={shariahFilter} onOpenSymbol={openWatchedCompany} /> : null}
            {activeTool === "dividends" && visible.toolDividends ? (
              <DividendsCalendarCard
                rows={dividendRows}
                loading={dividendLoading}
                error={dividendError}
                hint={dividendHint}
                asOf={dividendAsOf}
                onOpen={openWatchedCompany}
              />
            ) : null}
            {activeTool === "ranking" && visible.toolRanking ? <RankingRevealCard shariahFilter={shariahFilter} /> : null}
          </div>
        ) : null}

        {activeTab === "home" ? (
          <div className="space-y-6">
            {visible.heatmap || visible.followedRadar ? (
              <p className="text-center text-xs text-zinc-400">{ar.liveDashboardHint}</p>
            ) : null}
            {watchOpen ? <UnderWatchSection rows={watchRows} onClose={closeWatch} /> : null}
            {!watchOpen ? (
              <>
                {visible.matrix ? (
                  <InstitutionalMatrix
                    shariahFilter={shariahFilter}
                    funds={fundsPayload?.data ?? []}
                    fundsLoading={fundsLoading}
                    showEntry={visible.columnEntry}
                    showExit={visible.columnExit}
                    showAccumulation={visible.columnAccumulation}
                    showDistribution={visible.columnDistribution}
                    onOpen={openWatchedCompany}
                  />
                ) : null}
                {visible.heatmap ? (
                <SectorHeatmapCard
                  selectedSector={selectedSector}
                  radarSymbol={radarSymbol}
                  radarName={radarName}
                  shariahFilter={shariahFilter}
                  onSelectSector={(sector) => replaceQuery({ tab: null, section: null, sector, symbol: null, name: null })}
                  onOpenRadar={(company) =>
                    replaceQuery({
                      tab: null,
                      section: null,
                      sector: selectedSector,
                      symbol: company?.symbol ?? null,
                      name: company?.name ?? null,
                    })
                  }
                />
                ) : null}
                {visible.followedRadar ? (
                <div className="space-y-4">
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
              </>
            ) : null}
          </div>
        ) : null}
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
