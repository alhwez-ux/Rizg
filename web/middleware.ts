import { NextRequest, NextResponse } from "next/server";

import { CLIENT_BUILD, SESSION_COOKIE } from "@/lib/auth/config";
import { readSessionToken, sessionCookieFromRequest } from "@/lib/auth/token";

const PUBLIC_PATHS = ["/login", "/api/auth", "/api/version", "/sw.js", "/version.json"];
const STALE_COOKIES = [
  "rizg_session",
  "rizg_session_v3",
  "rizg_session_v4",
  "rizg_session_v5",
  "rizg_session_v6",
  "rizg_pin_cfg",
  "rizg_pin_cfg_v3",
  "rizg_pin_cfg_v4",
  "rizg_pin_cfg_v5",
  "rizg_pin_cfg_v6",
];

function withNoStore(response: NextResponse, auth: string): NextResponse {
  response.headers.set("x-rizg-build", CLIENT_BUILD);
  response.headers.set("x-rizg-auth", auth);
  response.headers.set("Cache-Control", "private, no-store, no-cache, must-revalidate, max-age=0");
  response.headers.set("Pragma", "no-cache");
  response.headers.set("CDN-Cache-Control", "no-store");
  response.headers.set("Vercel-CDN-Cache-Control", "no-store");
  return response;
}

function clearStale(request: NextRequest, response: NextResponse): void {
  for (const name of STALE_COOKIES) {
    if (name !== SESSION_COOKIE && request.cookies.has(name)) {
      response.cookies.set(name, "", { path: "/", maxAge: 0 });
    }
  }
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/icons") ||
    pathname === "/favicon.ico" ||
    pathname === "/manifest.webmanifest" ||
    pathname === "/sw.js" ||
    pathname === "/version.json" ||
    PUBLIC_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`))
  ) {
    const pass = withNoStore(NextResponse.next(), "public");
    clearStale(request, pass);
    return pass;
  }

  const token = sessionCookieFromRequest(request.cookies);
  const ok = await readSessionToken(token);
  if (ok) {
    return withNoStore(NextResponse.next(), "ok");
  }

  if (pathname.startsWith("/api/")) {
    return withNoStore(NextResponse.json({ message: "unauthorized" }, { status: 401 }), token ? "invalid" : "missing");
  }

  const login = request.nextUrl.clone();
  login.pathname = "/login";
  const next = `${pathname}${request.nextUrl.search}`;
  login.searchParams.set("next", next.startsWith("/") ? next : pathname);
  login.searchParams.set("v", CLIENT_BUILD);
  const redirect = withNoStore(NextResponse.redirect(login), token ? "invalid" : "missing");
  clearStale(request, redirect);
  return redirect;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
