"use client";

import { useEffect } from "react";

import { AUTH_VERSION } from "@/lib/auth/public-constants";

const STORAGE_KEY = "rizg-build";

export function AppUpdateGuard() {
  useEffect(() => {
    const previous = window.localStorage.getItem(STORAGE_KEY);
    if (previous === AUTH_VERSION) {
      void navigator.serviceWorker?.register("/sw.js").catch(() => undefined);
      return;
    }

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
      window.localStorage.setItem(STORAGE_KEY, AUTH_VERSION);
      if (previous) {
        window.location.reload();
        return;
      }
      void navigator.serviceWorker?.register("/sw.js").catch(() => undefined);
    })();
  }, []);

  return null;
}
