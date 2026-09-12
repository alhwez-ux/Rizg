import { NextRequest, NextResponse } from "next/server";

import { AUTH_VERSION, SESSION_COOKIE } from "@/lib/auth";
import { readSessionToken } from "@/lib/auth/session";

const PUBLIC_PATHS = ["/login", "/api/auth", "/sw.js", "/version.json"];
const STALE_COOKIES = ["rizg_session", "rizg_session_v3", "rizg_pin_cfg", "rizg_pin_cfg_v3"];

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
    const pass = NextResponse.next();
    pass.headers.set("x-rizg-build", AUTH_VERSION);
    for (const name of STALE_COOKIES) {
      if (request.cookies.has(name)) pass.cookies.set(name, "", { path: "/", maxAge: 0 });
    }
    return pass;
  }

  const ok = await readSessionToken(request.cookies.get(SESSION_COOKIE)?.value);
  if (ok) {
    const pass = NextResponse.next();
    pass.headers.set("x-rizg-build", AUTH_VERSION);
    return pass;
  }

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ message: "unauthorized" }, { status: 401 });
  }

  const login = request.nextUrl.clone();
  login.pathname = "/login";
  login.searchParams.set("next", pathname);
  const redirect = NextResponse.redirect(login);
  redirect.headers.set("x-rizg-build", AUTH_VERSION);
  for (const name of STALE_COOKIES) {
    if (request.cookies.has(name)) redirect.cookies.set(name, "", { path: "/", maxAge: 0 });
  }
  return redirect;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
