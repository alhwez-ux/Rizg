"use client";

import { useEffect } from "react";

import { CLIENT_BUILD } from "@/lib/auth/public-constants";

const STORAGE_KEY = "rizg-build";

export function AppUpdateGuard() {
  useEffect(() => {
    void (async () => {
      try {
        if ("serviceWorker" in navigator) {
          const registrations = await navigator.serviceWorker.getRegistrations();
          await Promise.all(registrations.map((registration) => registration.unregister()));
        }
        if ("caches" in window) {
          const keys = await caches.keys();
          await Promise.all(keys.map((key) => caches.delete(key)));
        }
      } catch {
        /* ignore */
      }

      let remote = CLIENT_BUILD;
      try {
        const response = await fetch(`/api/version?cb=${Date.now()}`, { cache: "no-store" });
        const payload = (await response.json().catch(() => null)) as { build?: string } | null;
        if (payload?.build) remote = String(payload.build);
      } catch {
        try {
          const fallback = await fetch(`/version.json?cb=${Date.now()}`, { cache: "no-store" });
          const payload = (await fallback.json().catch(() => null)) as { build?: string } | null;
          if (payload?.build) remote = String(payload.build);
        } catch {
          /* keep the HTML build id */
        }
      }

      const latest = newerBuild(remote, CLIENT_BUILD);
      const previous = window.localStorage.getItem(STORAGE_KEY);
      const url = new URL(window.location.href);
      const currentQuery = url.searchParams.get("v");
      window.localStorage.setItem(STORAGE_KEY, latest);
      if (previous !== latest || currentQuery !== latest) {
        url.searchParams.set("v", latest);
        window.location.replace(url.pathname + url.search);
      }
    })();
  }, []);

  return null;
}

function newerBuild(left: string, right: string): string {
  const leftNum = Number(left);
  const rightNum = Number(right);
  if (Number.isFinite(leftNum) && Number.isFinite(rightNum)) {
    return leftNum >= rightNum ? left : right;
  }
  return left >= right ? left : right;
}
