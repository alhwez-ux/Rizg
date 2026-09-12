import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { AUTH_VERSION, SESSION_COOKIE, SESSION_DAYS, signValue, verifySigned } from "@/lib/auth";

function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.VERCEL === "1" || process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  };
}

export async function createSessionToken(): Promise<string> {
  const expires = Date.now() + SESSION_DAYS * 86_400_000;
  return signValue(`ok.${AUTH_VERSION}.${expires}`);
}

export async function readSessionToken(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  const value = await verifySigned(token);
  const prefix = `ok.${AUTH_VERSION}.`;
  if (!value?.startsWith(prefix)) return false;
  const expires = Number(value.slice(prefix.length));
  return Number.isFinite(expires) && expires > Date.now();
}

export function applySessionCookie(response: NextResponse, token: string): NextResponse {
  response.cookies.set(SESSION_COOKIE, token, cookieOptions(SESSION_DAYS * 86_400));
  return response;
}

export async function setSessionCookie(): Promise<string> {
  const token = await createSessionToken();
  (await cookies()).set(SESSION_COOKIE, token, cookieOptions(SESSION_DAYS * 86_400));
  return token;
}

export async function clearSessionCookie(): Promise<void> {
  const jar = await cookies();
  jar.set(SESSION_COOKIE, "", cookieOptions(0));
}

export function applyClearedSessionCookie(response: NextResponse): NextResponse {
  response.cookies.set(SESSION_COOKIE, "", cookieOptions(0));
  return response;
}
