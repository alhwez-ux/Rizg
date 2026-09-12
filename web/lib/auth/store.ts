import { cookies } from "next/headers";

import { prisma } from "@/lib/prisma";
import {
  PIN_SETUP_COOKIE,
  RECOVERY_EMAIL,
  RESET_MINUTES,
  defaultAccessPin,
  hashSecret,
  normalizePin,
  signValue,
  verifySecret,
  verifySigned,
} from "@/lib/auth";

type GateRecord = {
  pinHash: string;
  pinSalt: string;
  recoveryEmail: string;
  resetCodeHash: string | null;
  resetSalt: string | null;
  resetExpires: Date | null;
};

function asRecord(value: unknown): GateRecord | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  if (typeof row.pinHash !== "string" || typeof row.pinSalt !== "string") return null;
  return {
    pinHash: row.pinHash,
    pinSalt: row.pinSalt,
    recoveryEmail: typeof row.recoveryEmail === "string" ? row.recoveryEmail : RECOVERY_EMAIL,
    resetCodeHash: typeof row.resetCodeHash === "string" ? row.resetCodeHash : null,
    resetSalt: typeof row.resetSalt === "string" ? row.resetSalt : null,
    resetExpires: row.resetExpires ? new Date(String(row.resetExpires)) : null,
  };
}

async function readCookieGate(): Promise<GateRecord | null> {
  const raw = (await cookies()).get(PIN_SETUP_COOKIE)?.value;
  if (!raw) return null;
  const value = await verifySigned(raw);
  if (!value) return null;
  try {
    return asRecord(JSON.parse(value));
  } catch {
    return null;
  }
}

async function writeCookieGate(record: GateRecord): Promise<void> {
  const token = await signValue(
    JSON.stringify({
      ...record,
      resetExpires: record.resetExpires ? record.resetExpires.toISOString() : null,
    }),
  );
  (await cookies()).set(PIN_SETUP_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.VERCEL === "1" || process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
  });
}

async function readDbGate(): Promise<GateRecord | null> {
  try {
    const row = await prisma.appAuth.findUnique({ where: { id: "gate" } });
    return asRecord(row);
  } catch {
    return null;
  }
}

export async function getGate(): Promise<GateRecord | null> {
  return (await readDbGate()) ?? (await readCookieGate());
}

export async function isPinConfigured(): Promise<boolean> {
  return true;
}

export async function verifyPin(pin: string): Promise<boolean> {
  const secret = normalizePin(pin);
  if (secret === normalizePin(defaultAccessPin())) return true;
  const gate = await getGate();
  if (!gate) return false;
  return verifySecret(secret, gate.pinHash, gate.pinSalt);
}

export async function ensureGate(): Promise<GateRecord | null> {
  const existing = await getGate();
  if (existing) return existing;
  await savePin(defaultAccessPin());
  return getGate();
}

export async function savePin(pin: string): Promise<void> {
  const hashed = await hashSecret(normalizePin(pin));
  const record: GateRecord = {
    pinHash: hashed.hash,
    pinSalt: hashed.salt,
    recoveryEmail: RECOVERY_EMAIL,
    resetCodeHash: null,
    resetSalt: null,
    resetExpires: null,
  };
  try {
    await prisma.appAuth.upsert({
      where: { id: "gate" },
      update: {
        pinHash: record.pinHash,
        pinSalt: record.pinSalt,
        recoveryEmail: RECOVERY_EMAIL,
        resetCodeHash: null,
        resetSalt: null,
        resetExpires: null,
      },
      create: {
        id: "gate",
        pinHash: record.pinHash,
        pinSalt: record.pinSalt,
        recoveryEmail: RECOVERY_EMAIL,
      },
    });
  } catch {
    /* cookie backup on read-only / missing table */
  }
  await writeCookieGate(record);
}

export async function saveResetCode(code: string): Promise<void> {
  const gate = await ensureGate();
  if (!gate) return;
  const hashed = await hashSecret(code);
  const expires = new Date(Date.now() + RESET_MINUTES * 60_000);
  const next: GateRecord = {
    ...gate,
    resetCodeHash: hashed.hash,
    resetSalt: hashed.salt,
    resetExpires: expires,
  };
  try {
    await prisma.appAuth.update({
      where: { id: "gate" },
      data: { resetCodeHash: hashed.hash, resetSalt: hashed.salt, resetExpires: expires },
    });
  } catch {
    /* cookie backup */
  }
  await writeCookieGate(next);
}

export async function consumeResetCode(code: string, nextPin: string): Promise<boolean> {
  const gate = await getGate();
  if (!gate?.resetCodeHash || !gate.resetSalt || !gate.resetExpires) return false;
  if (gate.resetExpires.getTime() < Date.now()) return false;
  const ok = await verifySecret(code, gate.resetCodeHash, gate.resetSalt);
  if (!ok) return false;
  await savePin(nextPin);
  return true;
}
