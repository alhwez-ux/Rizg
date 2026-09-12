import { NextResponse } from "next/server";

import { isValidPin, normalizePin } from "@/lib/auth";
import { setSessionCookie } from "@/lib/auth/session";
import { verifyPin } from "@/lib/auth/store";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { pin?: unknown } | null;
  const pin = normalizePin(String(body?.pin ?? ""));
  if (!isValidPin(pin)) {
    return NextResponse.json({ message: "invalid_pin" }, { status: 422 });
  }
  if (!(await verifyPin(pin))) {
    return NextResponse.json({ message: "wrong_pin" }, { status: 401 });
  }
  await setSessionCookie();
  return NextResponse.json({ ok: true });
}
