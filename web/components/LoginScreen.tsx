"use client";

import { FormEvent, useState } from "react";

import { RizgLogo } from "@/components/RizgLogo";
import { ar } from "@/lib/ar";
import { AUTH_VERSION, PIN_MAX_LENGTH, RECOVERY_EMAIL } from "@/lib/auth/public-constants";

type Mode = "login" | "recover" | "reset";

export function LoginScreen() {
  const [mode, setMode] = useState<Mode>("login");
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const goHome = () => {
    const next = new URLSearchParams(window.location.search).get("next") || "/";
    const path = next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : "/";
    const url = new URL(path, window.location.origin);
    url.searchParams.set("v", AUTH_VERSION);
    window.location.replace(url.pathname + url.search);
  };

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
      goHome();
    } catch {
      setError(ar.authWrongPin);
    } finally {
      setBusy(false);
    }
  };

  const onRecover = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const response = await fetch("/api/auth/recover", {
        method: "POST",
        credentials: "include",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const payload = (await response.json().catch(() => null)) as { delivered?: boolean } | null;
      if (!response.ok) {
        setError(ar.authRecoverEmailMismatch);
        return;
      }
      setInfo(payload?.delivered ? ar.authRecoverSent : ar.authRecoverQueued);
      setMode("reset");
    } catch {
      setError(ar.authRecoverEmailMismatch);
    } finally {
      setBusy(false);
    }
  };

  const onReset = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/reset", {
        method: "POST",
        credentials: "include",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, pin, confirm }),
      });
      if (!response.ok) {
        setError(ar.authResetFailed);
        return;
      }
      goHome();
    } catch {
      setError(ar.authResetFailed);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-6 px-4 py-10">
      <div className="flex flex-col items-center text-center">
        <RizgLogo iconClassName="h-14 w-14" />
        <h1 className="mt-4 text-2xl font-semibold text-zinc-50">{ar.authTitle}</h1>
      </div>

      <section className="rounded-2xl border border-zinc-800 bg-tape-panel/90 p-5 shadow-glow">
        {mode === "login" ? (
          <form onSubmit={onLogin} className="flex flex-col gap-3">
            <label className="text-sm text-zinc-300">
              {ar.authPinLabel}
              <input
                value={pin}
                onChange={(event) => setPin(event.target.value)}
                inputMode="numeric"
                maxLength={PIN_MAX_LENGTH}
                autoComplete="current-password"
                className="mt-1.5 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2.5 font-mono text-center text-lg tracking-[0.4em] outline-none ring-emerald-500/40 focus:ring"
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-zinc-950 disabled:opacity-50"
            >
              <LoginIcon />
              {ar.authEnter}
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("recover");
                setError(null);
                setInfo(null);
              }}
              className="text-xs text-zinc-500 hover:text-emerald-300"
            >
              {ar.authForgot}
            </button>
          </form>
        ) : null}

        {mode === "recover" ? (
          <form onSubmit={onRecover} className="flex flex-col gap-3">
            <p className="text-sm text-zinc-400">
              {ar.authRecoverHint}{" "}
              <span className="font-mono text-zinc-200" dir="ltr">
                {RECOVERY_EMAIL}
              </span>
            </p>
            <label className="text-sm text-zinc-300">
              {ar.authEmailLabel}
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                type="email"
                dir="ltr"
                className="mt-1.5 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2.5 text-sm outline-none ring-emerald-500/40 focus:ring"
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-zinc-950 disabled:opacity-50"
            >
              {ar.authSendCode}
            </button>
            <button type="button" onClick={() => setMode("login")} className="text-xs text-zinc-500 hover:text-zinc-300">
              {ar.authBackToLogin}
            </button>
          </form>
        ) : null}

        {mode === "reset" ? (
          <form onSubmit={onReset} className="flex flex-col gap-3">
            <label className="text-sm text-zinc-300">
              {ar.authCodeLabel}
              <input
                value={code}
                onChange={(event) => setCode(event.target.value)}
                inputMode="numeric"
                maxLength={6}
                dir="ltr"
                className="mt-1.5 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2.5 font-mono text-center tracking-[0.4em] outline-none ring-emerald-500/40 focus:ring"
              />
            </label>
            <label className="text-sm text-zinc-300">
              {ar.authNewPinLabel}
              <input
                value={pin}
                onChange={(event) => setPin(event.target.value)}
                inputMode="numeric"
                maxLength={PIN_MAX_LENGTH}
                className="mt-1.5 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2.5 font-mono text-center tracking-[0.4em] outline-none ring-emerald-500/40 focus:ring"
              />
            </label>
            <label className="text-sm text-zinc-300">
              {ar.authConfirmPinLabel}
              <input
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                inputMode="numeric"
                maxLength={PIN_MAX_LENGTH}
                className="mt-1.5 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-3 py-2.5 font-mono text-center tracking-[0.4em] outline-none ring-emerald-500/40 focus:ring"
              />
            </label>
            <button
              type="submit"
              disabled={busy}
              className="rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-semibold text-zinc-950 disabled:opacity-50"
            >
              {ar.authSavePin}
            </button>
            <button type="button" onClick={() => setMode("login")} className="text-xs text-zinc-500 hover:text-zinc-300">
              {ar.authBackToLogin}
            </button>
          </form>
        ) : null}

        {error ? <p className="mt-3 text-sm text-rose-300">{error}</p> : null}
        {info ? <p className="mt-3 text-sm text-emerald-300">{info}</p> : null}
      </section>
    </main>
  );
}

function LoginIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
      <path
        d="M10 17H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4h6a4 4 0 0 1 4 4v2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path d="M15 14h7m-3-3 3 3-3 3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
