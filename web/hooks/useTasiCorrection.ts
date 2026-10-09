"use client";

import { useEffect, useState } from "react";
import { fetchTasiCorrection, type TasiCorrectionPayload } from "@/lib/tasiCorrection";
import { sessionPollMs } from "@/lib/sessionPoll";

const QUIET_MS = 20_000;

export function useTasiCorrection(enabled = true): TasiCorrectionPayload | null {
  const [state, setState] = useState<TasiCorrectionPayload | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let timer = 0;

    const pull = async () => {
      try {
        const next = await fetchTasiCorrection();
        if (alive && next) setState(next);
      } catch {
        /* keep the last measured state; a failed poll must not flash a warning */
      } finally {
        if (alive) timer = window.setTimeout(pull, sessionPollMs(QUIET_MS));
      }
    };

    void pull();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [enabled]);

  return state;
}
