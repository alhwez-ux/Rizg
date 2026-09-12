import { NextResponse } from "next/server";

import { applyClearedSessionCookie } from "@/lib/auth/session";

export const dynamic = "force-dynamic";

export async function POST() {
  return applyClearedSessionCookie(NextResponse.json({ ok: true }));
}
