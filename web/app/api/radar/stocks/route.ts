import { NextResponse } from "next/server";

import { listRadarStocks } from "@/lib/compliance/radarController";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const payload = await listRadarStocks();
    return NextResponse.json(payload);
  } catch (error) {
    const message = error instanceof Error ? error.message : "radar_query_failed";
    return NextResponse.json({ message, stocks: [] }, { status: 500 });
  }
}
