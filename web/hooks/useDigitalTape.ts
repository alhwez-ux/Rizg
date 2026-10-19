"use client";

import { useEffect, useRef, useState } from "react";
import { fetchDigitalTape, type DigitalTapeRow } from "@/lib/digitalDesk";
import { sessionPollMs } from "@/lib/sessionPoll";

const IDLE_MS = 12_000;

/**
 * Keeps the last successful market book. A failed poll never clears the table.
 */
export function useDigitalTape(enabled: boolean) {
  const [rows, setRows] = useState<DigitalTapeRow[]>([]);
  const [ready, setReady] = useState(false);
  const [stale, setStale] = useState(false);
  const held = useRef(false);

  useEffect(() => {
    let active = true;
    let timer = 0;

    const pull = async () => {
      const next = await fetchDigitalTape();
      if (!active) return;
      if (next.length) {
        held.current = true;
        setRows(next);
        setStale(false);
      } else if (held.current) {
        setStale(true);
      }
      setReady(true);
      if (enabled) timer = window.setTimeout(pull, sessionPollMs(IDLE_MS));
    };

    void pull();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [enabled]);

  return { rows, ready, stale };
}
