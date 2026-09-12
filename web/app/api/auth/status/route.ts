import { NextResponse } from "next/server";

import { RECOVERY_EMAIL } from "@/lib/auth";
import { readSessionToken } from "@/lib/auth/session";
import { isPinConfigured } from "@/lib/auth/store";
import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET() {
  const configured = await isPinConfigured();
  const authenticated = await readSessionToken((await cookies()).get(SESSION_COOKIE)?.value);
  return NextResponse.json({ configured, authenticated, recoveryEmail: RECOVERY_EMAIL });
}
