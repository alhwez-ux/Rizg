"use client";

import { useEffect } from "react";

import { CLIENT_BUILD } from "@/lib/auth/public-constants";

const STORAGE_KEY = "rizg-build";

export function AppUpdateGuard() {
  useEffect(() => {
    const previous = window.localStorage.getItem(STORAGE_KEY);
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
      window.localStorage.setItem(STORAGE_KEY, CLIENT_BUILD);
      if (previous && previous !== CLIENT_BUILD) {
        const url = new URL(window.location.href);
        url.searchParams.set("v", CLIENT_BUILD);
        window.location.replace(url.pathname + url.search);
      }
    })();
  }, []);

  return null;
}
