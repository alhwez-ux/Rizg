"use client";

import { Component, useState, type ReactNode } from "react";

import { ar } from "@/lib/ar";

interface BoundaryProps {
  epoch: number;
  onRetry: () => void;
  children: ReactNode;
}

interface BoundaryState {
  error: Error | null;
}

class Boundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error };
  }

  componentDidUpdate(previous: BoundaryProps) {
    if (previous.epoch !== this.props.epoch && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div role="alert" className="rounded-2xl border border-rose-500/30 bg-zinc-950 px-4 py-6 text-center">
          <p className="text-sm font-semibold text-rose-200">{ar.panelError}</p>
          <p className="mt-1 text-xs text-zinc-500">{ar.panelErrorHint}</p>
          <button
            type="button"
            onClick={this.props.onRetry}
            className="mt-3 rounded-full border border-zinc-700 px-4 py-1.5 text-xs font-semibold text-zinc-200 hover:border-zinc-500"
          >
            {ar.panelRetry}
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export function PanelBoundary({ children }: { children: ReactNode }) {
  const [epoch, setEpoch] = useState(0);
  return (
    <Boundary epoch={epoch} onRetry={() => setEpoch((value) => value + 1)}>
      {children}
    </Boundary>
  );
}
