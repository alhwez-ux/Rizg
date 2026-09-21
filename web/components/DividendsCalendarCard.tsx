"use client";

import { ar } from "@/lib/ar";
import { formatRiyadhDate, type DividendRow } from "@/lib/dividends";

export function DividendsCalendarCard({
  rows,
  loading,
  error,
  hint,
  asOf,
  onOpen,
}: {
  rows: DividendRow[];
  loading?: boolean;
  error?: string | null;
  hint?: string;
  asOf?: string;
  onOpen?: (company: { symbol: string; name: string }) => void;
}) {
  return (
    <section className="rounded-2xl border border-zinc-800/80 bg-tape-panel/90 p-5 text-center text-zinc-100 shadow-glow sm:p-6">
      <div className="mb-5 border-b border-zinc-800 pb-4">
        <h2 className="text-xl font-bold text-zinc-50">{ar.dividendsTitle}</h2>
        <p className="mt-1 text-xs text-zinc-400">{ar.dividendsHint}</p>
        {asOf ? (
          <p className="mt-1 text-[11px] text-zinc-500">
            {ar.dividendsAsOf} <span dir="ltr">{formatRiyadhDate(asOf)}</span>
          </p>
        ) : null}
      </div>

      {error ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</p>
      ) : loading && rows.length === 0 ? (
        <p className="py-10 text-sm text-zinc-500">{ar.dividendsLoading}</p>
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-800 px-4 py-10 text-sm text-zinc-500">
          {ar.dividendsEmpty}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-start text-sm">
            <thead>
              <tr className="border-b border-zinc-800 text-xs text-zinc-500">
                <th className="p-3 font-medium">{ar.dividendsColCompany}</th>
                <th className="p-3 font-medium">{ar.dividendsColSymbol}</th>
                <th className="p-3 font-medium">{ar.dividendsColCash}</th>
                <th className="p-3 font-medium">{ar.dividendsColEligibility}</th>
                <th className="p-3 font-medium">{ar.dividendsColPayment}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800/60">
              {rows.map((row) => (
                <tr key={`${row.symbol}-${row.eligibility_date}`} className="hover:bg-zinc-950/40">
                  <td className="p-3">
                    <button
                      type="button"
                      onClick={() => onOpen?.({ symbol: row.symbol, name: row.name })}
                      className="text-start font-semibold text-zinc-100 hover:text-emerald-300"
                    >
                      {row.name}
                    </button>
                    <p className="mt-0.5 text-[11px] text-zinc-500">
                      {row.sector}
                      {row.shariah_label ? ` · ${row.shariah_label}` : ""}
                    </p>
                  </td>
                  <td className="p-3 font-mono text-zinc-200" dir="ltr">
                    {row.symbol}
                  </td>
                  <td className="p-3 font-mono font-semibold text-emerald-300" dir="ltr">
                    {row.cash_dividend.toFixed(2)} {ar.dividendsCurrency}
                  </td>
                  <td className="p-3 font-mono text-amber-200" dir="ltr">
                    {formatRiyadhDate(row.eligibility_date)}
                    {row.days_to_eligibility === 0 ? (
                      <span className="ms-2 text-[11px] text-amber-100">{ar.dividendsToday}</span>
                    ) : null}
                  </td>
                  <td className="p-3 font-mono text-zinc-200" dir="ltr">
                    {formatRiyadhDate(row.payment_date)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-4 text-xs leading-relaxed text-zinc-500">{hint || ar.dividendsDropHint}</p>
    </section>
  );
}
