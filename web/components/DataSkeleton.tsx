export function DataSkeleton({
  rows = 4,
  kind = "card",
}: {
  rows?: number;
  kind?: "card" | "table" | "chart" | "grid";
}) {
  if (kind === "table") {
    return (
      <div className="space-y-2 py-2" aria-hidden="true">
        {Array.from({ length: rows }, (_, index) => (
          <div key={index} className="h-9 animate-pulse rounded-lg bg-zinc-800/80" />
        ))}
      </div>
    );
  }
  if (kind === "chart") {
    return <div className="h-40 animate-pulse rounded-2xl bg-zinc-800/70" aria-hidden="true" />;
  }
  if (kind === "grid") {
    return (
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" aria-hidden="true">
        {Array.from({ length: rows }, (_, index) => (
          <div key={index} className="h-16 animate-pulse rounded-xl bg-zinc-800/80" />
        ))}
      </div>
    );
  }
  return (
    <div className="space-y-3 py-2" aria-hidden="true">
      <div className="mx-auto h-4 w-1/3 animate-pulse rounded bg-zinc-800 sm:mx-0" />
      <div className="h-16 animate-pulse rounded-xl bg-zinc-800/80" />
      <div className="h-10 animate-pulse rounded-xl bg-zinc-800/60" />
    </div>
  );
}
