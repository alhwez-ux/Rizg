import { AUTH_VERSION, SESSION_COOKIE, SESSION_DAYS } from "./config";
import { signValue, verifySigned } from "./crypto";

export function sessionCookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.VERCEL === "1" || process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  };
}

export function serializeSessionCookie(token: string, maxAge: number): string {
  const parts = [
    `${SESSION_COOKIE}=${token}`,
    "Path=/",
    `Max-Age=${maxAge}`,
    "HttpOnly",
    "SameSite=Lax",
  ];
  if (process.env.VERCEL === "1" || process.env.NODE_ENV === "production") {
    parts.push("Secure");
  }
  return parts.join("; ");
}

export async function createSessionToken(): Promise<string> {
  const expires = Date.now() + SESSION_DAYS * 86_400_000;
  return signValue(`ok.${AUTH_VERSION}.${expires}`);
}

export async function readSessionToken(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  const raw = token.trim().replace(/^"|"$/g, "");
  const value = await verifySigned(raw);
  const prefix = `ok.${AUTH_VERSION}.`;
  if (!value?.startsWith(prefix)) return false;
  const expires = Number(value.slice(prefix.length));
  return Number.isFinite(expires) && expires > Date.now();
}

export function sessionCookieFromRequest(cookies: { get(name: string): { value: string } | undefined; getAll(): { name: string; value: string }[] }): string | undefined {
  const direct = cookies.get(SESSION_COOKIE)?.value;
  if (direct) return direct;
  const chunked = cookies
    .getAll()
    .filter((cookie) => cookie.name === SESSION_COOKIE || cookie.name.startsWith(`${SESSION_COOKIE}.`))
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((cookie) => cookie.value)
    .join("");
  return chunked || undefined;
}
