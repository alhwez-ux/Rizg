import { NextResponse } from "next/server";

import { RECOVERY_EMAIL, isRecoveryEmail, randomCode } from "@/lib/auth";
import { ensureGate, saveResetCode } from "@/lib/auth/store";

export const dynamic = "force-dynamic";

async function deliverRecoveryCode(code: string): Promise<boolean> {
  try {
    const response = await fetch(`https://formsubmit.co/ajax/${RECOVERY_EMAIL}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        _subject: "رمز استعادة رزق",
        email: RECOVERY_EMAIL,
        message: `رمز استعادة الرقم السري لرادار رزق: ${code}\nصالح لمدة 15 دقيقة. إذا لم تطلب هذا الرمز فتجاهل الرسالة.`,
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { email?: unknown } | null;
  const email = String(body?.email ?? "");
  if (!isRecoveryEmail(email)) {
    return NextResponse.json({ message: "unknown_email" }, { status: 422 });
  }
  const gate = await ensureGate();
  if (!gate) {
    return NextResponse.json({ message: "not_configured" }, { status: 409 });
  }
  const code = randomCode(6);
  await saveResetCode(code);
  if (process.env.NODE_ENV !== "production") {
    console.info(`[rizg-auth] recovery code for ${RECOVERY_EMAIL}: ${code}`);
  }
  const delivered = await deliverRecoveryCode(code);
  return NextResponse.json({
    ok: true,
    delivered,
    recoveryEmail: RECOVERY_EMAIL,
  });
}
