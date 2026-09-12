"use client";

import { FormEvent, useState } from "react";

import { ar } from "@/lib/ar";
import { PIN_MAX_LENGTH } from "@/lib/auth/public-constants";

export function AuthControls() {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState("");
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/login");
  };

  const onChangePin = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch("/api/account/pin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current, pin, confirm }),
      });
      if (!response.ok) {
        setError(response.status === 401 ? ar.authWrongPin : ar.authChangeFailed);
        return;
      }
      setMessage(ar.authPinUpdated);
      setCurrent("");
      setPin("");
      setConfirm("");
    } catch {
      setError(ar.authChangeFailed);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        title={ar.authChangePin}
        className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-zinc-700 text-zinc-300 hover:border-emerald-500 hover:text-emerald-300"
      >
        <span className="sr-only">{ar.authChangePin}</span>
        <KeyIcon />
      </button>
      <button
        type="button"
        onClick={() => {
          void logout();
        }}
        title={ar.authLogout}
        className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-zinc-700 text-zinc-300 hover:border-rose-400 hover:text-rose-300"
      >
        <span className="sr-only">{ar.authLogout}</span>
        <LogoutIcon />
      </button>

      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form
            onSubmit={onChangePin}
            className="w-full max-w-sm rounded-2xl border border-zinc-800 bg-zinc-950 p-5 shadow-glow"
          >
            <h2 className="text-lg font-semibold text-zinc-100">{ar.authChangePin}</h2>
            <p className="mt-1 text-xs text-zinc-500">{ar.authChangePinHint}</p>
            <label className="mt-4 block text-sm text-zinc-300">
              {ar.authCurrentPinLabel}
              <input
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
                inputMode="numeric"
                maxLength={PIN_MAX_LENGTH}
                className="mt-1.5 w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 py-2 font-mono tracking-[0.3em] outline-none ring-emerald-500/40 focus:ring"
              />
            </label>
            <label className="mt-3 block text-sm text-zinc-300">
              {ar.authNewPinLabel}
              <input
                value={pin}
                onChange={(event) => setPin(event.target.value)}
                inputMode="numeric"
                maxLength={PIN_MAX_LENGTH}
                className="mt-1.5 w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 py-2 font-mono tracking-[0.3em] outline-none ring-emerald-500/40 focus:ring"
              />
            </label>
            <label className="mt-3 block text-sm text-zinc-300">
              {ar.authConfirmPinLabel}
              <input
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                inputMode="numeric"
                maxLength={PIN_MAX_LENGTH}
                className="mt-1.5 w-full rounded-xl border border-zinc-800 bg-zinc-900 px-3 py-2 font-mono tracking-[0.3em] outline-none ring-emerald-500/40 focus:ring"
              />
            </label>
            {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
            {message ? <p className="mt-3 text-sm text-emerald-300">{message}</p> : null}
            <div className="mt-4 flex gap-2">
              <button
                type="submit"
                disabled={busy}
                className="flex-1 rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-zinc-950 disabled:opacity-50"
              >
                {ar.authSavePin}
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-xl border border-zinc-700 px-4 py-2 text-sm text-zinc-300"
              >
                {ar.authClose}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </>
  );
}

function KeyIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
      <circle cx="8" cy="12" r="3.2" stroke="currentColor" strokeWidth="1.8" />
      <path d="M11 12h9l-2 2m0-4-2 2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function LogoutIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
      <path
        d="M14 17h3a4 4 0 0 0 4-4V7a4 4 0 0 0-4-4h-6a4 4 0 0 0-4 4v2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path d="M9 14H2m3-3-3 3 3 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
