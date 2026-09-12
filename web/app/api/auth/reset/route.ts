import { NextResponse } from "next/server";

import { isValidPin, normalizePin } from "@/lib/auth";
import { setSessionCookie } from "@/lib/auth/session";
import { consumeResetCode } from "@/lib/auth/store";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as {
    code?: unknown;
    pin?: unknown;
    confirm?: unknown;
  } | null;
  const code = String(body?.code ?? "").replace(/\D/g, "");
  const pin = normalizePin(String(body?.pin ?? ""));
  const confirm = normalizePin(String(body?.confirm ?? ""));
  if (code.length !== 6 || !isValidPin(pin) || pin !== confirm) {
    return NextResponse.json({ message: "invalid_reset" }, { status: 422 });
  }
  if (!(await consumeResetCode(code, pin))) {
    return NextResponse.json({ message: "invalid_code" }, { status: 401 });
  }
  await setSessionCookie();
  return NextResponse.json({ ok: true });
}
