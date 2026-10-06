"use client";

import { FormEvent, useEffect, useState } from "react";

import { ar } from "@/lib/ar";
import { CLIENT_BUILD, PIN_MAX_LENGTH } from "@/lib/auth/public-constants";

export function PinDock() {
  const [needed, setNeeded] = useState(false);
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/auth/status", { cache: "no-store", credentials: "include" })
      .then((response) => response.json())
      .then((payload: { authenticated?: boolean }) => {
        if (alive) setNeeded(payload?.authenticated !== true);
      })
      .catch(() => {
        if (alive) setNeeded(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const onLogin = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "include",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
      });
      if (!response.ok) {
        setError(ar.authWrongPin);
        return;
      }
      const url = new URL(window.location.href);
      url.searchParams.set("v", CLIENT_BUILD);
      window.location.replace(url.pathname + url.search);
    } catch {
      setError(ar.authWrongPin);
    } finally {
      setBusy(false);
    }
  };

  if (!needed) return null;

  return (
    <section className="w-full max-w-sm rounded-2xl border border-zinc-800 bg-zinc-950/90 p-3 text-start shadow-glow">
      <form onSubmit={onLogin} className="flex flex-col gap-2">
        <label className="text-xs text-zinc-400">
          {ar.authPinLabel}
          <input
            value={pin}
            onChange={(event) => setPin(event.target.value)}
            inputMode="numeric"
            maxLength={PIN_MAX_LENGTH}
            autoComplete="current-password"
            className="mt-1 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-center text-base tracking-[0.35em] outline-none ring-emerald-500/40 focus:ring"
          />
        </label>
        <div className="flex items-center justify-between gap-2">
          <button
            type="submit"
            disabled={busy}
            className="rounded-xl bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-zinc-950 disabled:opacity-50"
          >
            {ar.authEnter}
          </button>
          <a href="/login" className="text-[11px] text-zinc-500 hover:text-emerald-300">
            {ar.authForgot}
          </a>
        </div>
        {error ? <p className="text-xs text-rose-300">{error}</p> : null}
      </form>
    </section>
  );
}
