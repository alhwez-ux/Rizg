import { NextResponse } from "next/server";

import { isValidPin, normalizePin } from "@/lib/auth";
import { savePin, verifyPin } from "@/lib/auth/store";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as {
    current?: unknown;
    pin?: unknown;
    confirm?: unknown;
  } | null;
  const current = normalizePin(String(body?.current ?? ""));
  const pin = normalizePin(String(body?.pin ?? ""));
  const confirm = normalizePin(String(body?.confirm ?? ""));
  if (!isValidPin(current) || !isValidPin(pin) || pin !== confirm) {
    return NextResponse.json({ message: "invalid_pin" }, { status: 422 });
  }
  if (!(await verifyPin(current))) {
    return NextResponse.json({ message: "wrong_pin" }, { status: 401 });
  }
  await savePin(pin);
  return NextResponse.json({ ok: true });
}
