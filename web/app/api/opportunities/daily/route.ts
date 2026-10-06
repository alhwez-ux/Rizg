import { NextRequest, NextResponse } from "next/server";

import { API_BASE } from "@/lib/api";
import { lockScaledPlan } from "@/lib/liveEntryPlan";
import { isValidLongPlan } from "@/lib/tradeGeometry";
import { fetchYahooLasts } from "@/lib/yahooLast";
import { riyadhToday } from "@/lib/analystBook";

export const dynamic = "force-dynamic";

const HINT =
  "يُقفل الدخول على آخر سعر لحظة الإشارة، ويُحسب الهدف والوقف من ذلك الدخول بحيث يبقى الهدف أعلى من الدخول والوقف تحته.";

export async function GET(request: NextRequest) {
  const pureOnly = request.nextUrl.searchParams.get("pure_only") === "true";
  const upstreamPhase = await loadUpstreamPayload(pureOnly);
  const upstream = upstreamPhase.rows;
  const symbols = upstream.map((row) => String(row.symbol || "")).filter((symbol) => /^\d{4}$/.test(symbol));
  const lastPrices = symbols.length ? await fetchYahooLasts(symbols) : {};
  const today = riyadhToday();
  const data = upstream.map((row) => bindRow(row, lastPrices, today)).filter((row) => row != null);
  const phase = String(upstreamPhase.session_phase || "live");
  return NextResponse.json({
    success: true,
    session_phase: phase,
    session_label: String(upstreamPhase.session_label || ""),
    source: "live",
    count: data.length,
    min_reward_ratio: 1.5,
    hint: String(upstreamPhase.hint || HINT),
    scanned_at: new Date().toISOString(),
    data,
  });
}

async function loadUpstreamPayload(pureOnly: boolean): Promise<{
  rows: Record<string, unknown>[];
  session_phase: string;
  session_label: string;
  hint: string;
}> {
  try {
    const response = await fetch(`${API_BASE}/api/v1/opportunities/daily?pure_only=${pureOnly ? "true" : "false"}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return { rows: [], session_phase: "", session_label: "", hint: "" };
    const body = (await response.json()) as {
      data?: unknown;
      session_phase?: unknown;
      session_label?: unknown;
      hint?: unknown;
    };
    const rows = Array.isArray(body.data)
      ? body.data.filter((row): row is Record<string, unknown> => !!row && typeof row === "object")
      : [];
    return {
      rows,
      session_phase: String(body.session_phase || ""),
      session_label: String(body.session_label || ""),
      hint: String(body.hint || ""),
    };
  } catch {
    return { rows: [], session_phase: "", session_label: "", hint: "" };
  }
}

function bindRow(row: Record<string, unknown>, lastPrices: Record<string, number>, today: string): Record<string, unknown> | null {
  const symbol = String(row.symbol || "").trim().toUpperCase();
  const quoted = Number(row.last_price);
  const live = lastPrices[symbol] ?? (Number.isFinite(quoted) && quoted > 0 ? quoted : undefined);
  const templateEntry = priceText(row.entry_price) ?? (live != null ? String(live) : null);
  const templateTarget = priceText(row.target_price);
  const templateStop = priceText(row.stop_loss);
  if (!/^\d{4}$/.test(symbol) || live == null || !isValidLongPlan(templateEntry, templateTarget, templateStop)) {
    return null;
  }
  const locked = lockScaledPlan(
    "daily",
    symbol,
    today,
    String(templateEntry),
    String(templateTarget),
    String(templateStop),
    live,
    1.5,
  );
  if (!locked || locked.reward_ratio < 1.5) return null;
  return {
    ...row,
    symbol,
    last_price: Number(live.toFixed(2)),
    target_price: locked.target_price,
    stop_loss: locked.stop_loss,
    entry_price: locked.entry_price,
    reward_ratio: locked.reward_ratio,
    entry_locked_at: locked.locked_at,
  };
}

function priceText(value: unknown): string | null {
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "string" && value.trim()) return value.trim();
  return null;
}
