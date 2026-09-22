"use client";

import { useMemo, useState, type FormEvent } from "react";

import { ar } from "@/lib/ar";
import { formatMoney, formatPercent, formatPrice } from "@/lib/liquidity";
import { listedNameFor, searchListedCompanies, type ListedCompany } from "@/lib/listedCompanies";
import { type RecoveryAllocation } from "@/lib/recovery";
import { passesShariahFilter, type ShariahFilter } from "@/lib/shariah";
import { useRecoveryPlan } from "@/hooks/useRecoveryPlan";

function PlanPrices({ entry, target, stop }: { entry: number; target: number; stop: number }) {
  return (
    <div className="font-mono text-xs leading-6" dir="ltr">
      <p className="text-zinc-200">
        {ar.recoveryEntry} {formatPrice(entry)}
      </p>
      <p className="text-emerald-300">
        {ar.recoveryTarget} {formatPrice(target)}
      </p>
      <p className="text-rose-300">
        {ar.recoveryStop} {formatPrice(stop)}
      </p>
    </div>
  );
}

function AllocationCard({
  row,
  onOpen,
}: {
  row: RecoveryAllocation;
  onOpen?: (company: { symbol: string; name: string }) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen?.({ symbol: row.symbol, name: row.name })}
      className="w-full rounded-2xl border border-cyan-500/20 bg-zinc-950/50 p-4 text-center transition hover:border-cyan-400/40"
    >
      <div className="flex flex-wrap items-center justify-center gap-2">
        <span className="font-bold text-zinc-50">{row.name}</span>
        <span className="font-mono text-xs text-zinc-400" dir="ltr">
          {row.symbol}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-1">
        {row.tags.map((tag) => (
          <span
            key={tag}
            className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-semibold text-cyan-100"
          >
            {tag}
          </span>
        ))}
      </div>
      <p className="mt-3 font-mono text-sm text-cyan-100" dir="ltr">
        {formatMoney(row.allocation)} · {row.shares} {ar.recoveryShares}
      </p>
      <div className="mt-2">
        <PlanPrices entry={row.entry} target={row.target} stop={row.stop} />
      </div>
    </button>
  );
}

export function RecoveryCard({
  shariahFilter = "all",
  onOpenSymbol,
}: {
  shariahFilter?: ShariahFilter;
  onOpenSymbol?: (company: { symbol: string; name: string }) => void;
}) {
  const { payload, error, loading, calculate } = useRecoveryPlan();
  const [symbol, setSymbol] = useState("");
  const [quantity, setQuantity] = useState("");
  const [avgPrice, setAvgPrice] = useState("");
  const [suggestions, setSuggestions] = useState<ListedCompany[]>([]);

  const visible = useMemo(() => {
    const rows = payload?.data ?? [];
    return rows.filter((row) => passesShariahFilter(row.symbol, shariahFilter));
  }, [payload, shariahFilter]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const ticker = symbol.trim().toUpperCase();
    const qty = Number(quantity);
    const avg = Number(avgPrice);
    if (!/^\d{4}$/.test(ticker) || !(qty > 0) || !(avg > 0)) return;
    try {
      await calculate({ symbol: ticker, quantity: qty, avg_price: avg });
    } catch {
      /* error state is set by the hook */
    }
  }

  const position = payload?.position ?? null;
  const loss = Boolean(position?.in_loss);

  return (
    <section className="rounded-2xl border border-cyan-500/25 bg-tape-panel/90 p-5 text-center text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 border-b border-zinc-800 pb-4">
        <h2 className="text-xl font-bold text-zinc-50">{ar.recoveryTitle}</h2>
        <p className="mt-1 text-xs text-zinc-400">{ar.recoveryHint}</p>
      </div>

      <form onSubmit={onSubmit} className="mx-auto grid max-w-3xl gap-3 sm:grid-cols-4">
        <div className="relative sm:col-span-2">
          <label className="mb-1 block text-[11px] text-zinc-500">{ar.recoverySymbol}</label>
          <input
            value={symbol}
            onChange={(event) => {
              const next = event.target.value;
              setSymbol(next);
              setSuggestions(searchListedCompanies(next, 6));
            }}
            placeholder={ar.tickchartSymbolPlaceholder}
            autoComplete="off"
            className="min-h-11 w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 text-sm text-zinc-100 outline-none ring-cyan-500/40 placeholder:text-zinc-500 focus:ring-2"
          />
          {suggestions.length ? (
            <ul className="absolute z-20 mt-1 max-h-52 w-full overflow-auto rounded-xl border border-zinc-800 bg-zinc-950 py-1 text-start shadow-lg">
              {suggestions.map((item) => (
                <li key={item.symbol}>
                  <button
                    type="button"
                    onClick={() => {
                      setSymbol(item.symbol);
                      setSuggestions([]);
                    }}
                    className="flex w-full items-center justify-between gap-3 px-3 py-2 text-sm text-zinc-200 hover:bg-cyan-500/15"
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
        <div>
          <label className="mb-1 block text-[11px] text-zinc-500">{ar.recoveryQty}</label>
          <input
            value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
            inputMode="decimal"
            className="min-h-11 w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 font-mono text-sm text-zinc-100 outline-none ring-cyan-500/40 focus:ring-2"
            dir="ltr"
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-zinc-500">{ar.recoveryAvg}</label>
          <input
            value={avgPrice}
            onChange={(event) => setAvgPrice(event.target.value)}
            inputMode="decimal"
            className="min-h-11 w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 font-mono text-sm text-zinc-100 outline-none ring-cyan-500/40 focus:ring-2"
            dir="ltr"
          />
        </div>
        <div className="sm:col-span-4">
          <button
            type="submit"
            disabled={loading}
            className="min-h-11 rounded-xl bg-cyan-600 px-6 text-sm font-bold text-white transition hover:bg-cyan-500 disabled:opacity-50"
          >
            {loading ? ar.recoveryLoading : ar.recoverySubmit}
          </button>
        </div>
      </form>

      {error ? (
        <p className="mt-4 rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>
      ) : null}

      {position ? (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <div className="rounded-2xl border border-zinc-800 bg-zinc-950/40 p-4">
              <p className="text-[11px] text-zinc-500">{ar.recoveryLast}</p>
              <p className="mt-1 font-mono text-lg text-zinc-50" dir="ltr">
                {formatPrice(position.last_price)}
              </p>
              <p className="mt-1 text-xs text-zinc-400">
                {position.name || listedNameFor(position.symbol)} ·{" "}
                <span className="font-mono" dir="ltr">
                  {position.symbol}
                </span>
              </p>
            </div>
            <div
              className={`rounded-2xl border p-4 ${
                loss ? "border-rose-500/30 bg-rose-500/10" : "border-emerald-500/30 bg-emerald-500/10"
              }`}
            >
              <p className="text-[11px] text-zinc-500">{ar.recoveryPnl}</p>
              <p className={`mt-1 font-mono text-lg ${loss ? "text-rose-200" : "text-emerald-200"}`} dir="ltr">
                {formatMoney(position.unrealized_pnl)}
              </p>
              <p className={`mt-1 font-mono text-sm ${loss ? "text-rose-300" : "text-emerald-300"}`} dir="ltr">
                {formatPercent(position.pnl_pct)}
              </p>
            </div>
            <div className="rounded-2xl border border-zinc-800 bg-zinc-950/40 p-4">
              <p className="text-[11px] text-zinc-500">{ar.recoveryValue}</p>
              <p className="mt-1 font-mono text-lg text-zinc-50" dir="ltr">
                {formatMoney(position.market_value)}
              </p>
              <p className="mt-1 text-xs text-zinc-500">
                {ar.recoveryCost}{" "}
                <span className="font-mono" dir="ltr">
                  {formatMoney(position.cost_basis)}
                </span>
              </p>
            </div>
          </div>

          <p className="mt-4 rounded-xl border border-cyan-500/20 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100">
            {payload?.stance_label}
          </p>

          {payload?.averaging ? (
            <div className="mt-4 rounded-2xl border border-indigo-500/25 bg-indigo-500/10 p-4">
              <h3 className="text-sm font-bold text-indigo-100">{ar.recoveryAverageTitle}</h3>
              <p className="mt-1 text-xs text-zinc-400">{payload.averaging.reason}</p>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <p className="text-xs text-zinc-300">
                  {ar.recoveryExtraQty}:{" "}
                  <span className="font-mono" dir="ltr">
                    {payload.averaging.extra_quantity}
                  </span>
                </p>
                <p className="text-xs text-zinc-300">
                  {ar.recoveryNewAvg}:{" "}
                  <span className="font-mono" dir="ltr">
                    {formatPrice(payload.averaging.new_avg_price)}
                  </span>
                </p>
                <PlanPrices
                  entry={payload.averaging.entry}
                  target={payload.averaging.target}
                  stop={payload.averaging.stop}
                />
              </div>
            </div>
          ) : null}

          {visible.length ? (
            <div className="mt-6">
              <div className="mb-3 flex flex-wrap items-center justify-center gap-3 text-xs text-zinc-400">
                <span>
                  {ar.recoveryBudget}:{" "}
                  <span className="font-mono text-cyan-100" dir="ltr">
                    {formatMoney(payload?.rotation_budget ?? 0)}
                  </span>
                </span>
                <span>
                  {ar.recoveryCover}:{" "}
                  <span className="font-mono text-emerald-200" dir="ltr">
                    {formatMoney(payload?.expected_recovery ?? 0)} · {(payload?.cover_pct ?? 0).toFixed(0)}%
                  </span>
                </span>
              </div>
              <h3 className="mb-3 text-sm font-bold text-zinc-100">{ar.recoveryAllocTitle}</h3>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
                {visible.map((row) => (
                  <AllocationCard key={row.symbol} row={row} onOpen={onOpenSymbol} />
                ))}
              </div>
              <div className="hidden overflow-x-auto lg:block">
                <table className="w-full min-w-[960px] border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-zinc-800 text-xs text-zinc-500">
                      <th className="p-3 font-medium">{ar.recoveryColCompany}</th>
                      <th className="p-3 font-medium">{ar.recoveryColTag}</th>
                      <th className="p-3 font-medium">{ar.recoveryColAlloc}</th>
                      <th className="p-3 font-medium">{ar.recoveryColPlan}</th>
                      <th className="p-3 font-medium">{ar.recoveryColGain}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {visible.map((row) => (
                      <tr
                        key={row.symbol}
                        className="cursor-pointer hover:bg-zinc-950/40"
                        onClick={() => onOpenSymbol?.({ symbol: row.symbol, name: row.name })}
                      >
                        <td className="p-3 text-center">
                          <span className="font-bold text-zinc-50">{row.name}</span>
                          <p className="mt-0.5 font-mono text-[11px] text-zinc-400" dir="ltr">
                            {row.symbol}
                          </p>
                        </td>
                        <td className="p-3 text-center">
                          <div className="flex flex-wrap justify-center gap-1">
                            {row.tags.map((tag) => (
                              <span
                                key={tag}
                                className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] text-cyan-100"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="p-3 text-center font-mono text-cyan-100" dir="ltr">
                          {formatMoney(row.allocation)}
                          <p className="text-[11px] text-zinc-500">
                            {row.shares} · {row.weight_pct.toFixed(0)}%
                          </p>
                        </td>
                        <td className="p-3 text-center">
                          <PlanPrices entry={row.entry} target={row.target} stop={row.stop} />
                        </td>
                        <td className="p-3 text-center font-mono text-emerald-300" dir="ltr">
                          {formatMoney(row.expected_gain)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : payload && loss ? (
            <p className="mt-4 text-sm text-zinc-500">{ar.recoveryEmptyAlts}</p>
          ) : null}
        </>
      ) : loading ? (
        <p className="mt-6 text-sm text-zinc-500">{ar.recoveryLoading}</p>
      ) : (
        <p className="mt-6 text-sm text-zinc-500">{ar.recoveryIdle}</p>
      )}

      <p className="mt-4 text-xs leading-relaxed text-zinc-500">{payload?.hint || ar.recoveryHint}</p>
    </section>
  );
}

export default RecoveryCard;
