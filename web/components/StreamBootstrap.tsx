"use client";

import { useEffect } from "react";

import { armStreams, haltAllStreams, installStreamGuard, prepareStreams } from "@/lib/streamGuard";

installStreamGuard();

export function StreamBootstrap({ enabled }: { enabled: boolean }) {
  prepareStreams(enabled);
  useEffect(() => {
    if (enabled) armStreams();
    else haltAllStreams();
  }, [enabled]);

  return null;
}
