import { cookies } from "next/headers";

import { SESSION_COOKIE, SESSION_DAYS, signValue, verifySigned } from "@/lib/auth";

export async function createSessionToken(): Promise<string> {
  const expires = Date.now() + SESSION_DAYS * 86_400_000;
  return signValue(`ok.${expires}`);
}

export async function readSessionToken(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  const value = await verifySigned(token);
  if (!value?.startsWith("ok.")) return false;
  const expires = Number(value.slice(3));
  return Number.isFinite(expires) && expires > Date.now();
}

export async function setSessionCookie(): Promise<void> {
  const jar = await cookies();
  jar.set(SESSION_COOKIE, await createSessionToken(), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.VERCEL === "1" || process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_DAYS * 86_400,
  });
}

export async function clearSessionCookie(): Promise<void> {
  const jar = await cookies();
  jar.set(SESSION_COOKIE, "", { httpOnly: true, sameSite: "lax", path: "/", maxAge: 0 });
}

export async function hasSessionFromRequest(cookieHeader: string | null): Promise<boolean> {
  if (!cookieHeader) return false;
  const match = cookieHeader.split(";").map((part) => part.trim()).find((part) => part.startsWith(`${SESSION_COOKIE}=`));
  const token = match?.slice(SESSION_COOKIE.length + 1);
  return readSessionToken(token);
}
