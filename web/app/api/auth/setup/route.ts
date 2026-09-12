import { NextResponse } from "next/server";

import { isValidPin, normalizePin } from "@/lib/auth";
import { setSessionCookie } from "@/lib/auth/session";
import { isPinConfigured, savePin } from "@/lib/auth/store";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (await isPinConfigured()) {
    return NextResponse.json({ message: "pin_already_set" }, { status: 409 });
  }
  const body = (await request.json().catch(() => null)) as { pin?: unknown; confirm?: unknown } | null;
  const pin = normalizePin(String(body?.pin ?? ""));
  const confirm = normalizePin(String(body?.confirm ?? ""));
  if (!isValidPin(pin) || pin !== confirm) {
    return NextResponse.json({ message: "invalid_pin" }, { status: 422 });
  }
  await savePin(pin);
  await setSessionCookie();
  return NextResponse.json({ ok: true });
}
