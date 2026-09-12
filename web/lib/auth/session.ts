import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { SESSION_COOKIE, SESSION_DAYS } from "./config";
import {
  createSessionToken,
  sessionCookieOptions,
} from "./token";

export { createSessionToken, readSessionToken, sessionCookieOptions, serializeSessionCookie } from "./token";

export function applySessionCookie(response: NextResponse, token: string): NextResponse {
  response.cookies.set(SESSION_COOKIE, token, sessionCookieOptions(SESSION_DAYS * 86_400));
  return response;
}

export async function setSessionCookie(): Promise<string> {
  const token = await createSessionToken();
  (await cookies()).set(SESSION_COOKIE, token, sessionCookieOptions(SESSION_DAYS * 86_400));
  return token;
}

export async function clearSessionCookie(): Promise<void> {
  const jar = await cookies();
  jar.set(SESSION_COOKIE, "", sessionCookieOptions(0));
}

export function applyClearedSessionCookie(response: NextResponse): NextResponse {
  response.cookies.set(SESSION_COOKIE, "", sessionCookieOptions(0));
  return response;
}
