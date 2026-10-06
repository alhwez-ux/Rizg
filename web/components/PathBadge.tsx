import { PATH_DOWN_LABEL, PATH_UP_LABEL, sessionPath } from "@/lib/sessionPath";

export function PathBadge({
  price,
  vwap,
  change,
}: {
  price?: number | null;
  vwap?: number | null;
  change?: number | null;
}) {
  const path = sessionPath({ price, vwap, change });
  if (!path) return null;
  const up = path === "up";
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-bold ${
        up
          ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-200"
          : "border-rose-400/40 bg-rose-500/15 text-rose-200"
      }`}
    >
      {up ? PATH_UP_LABEL : PATH_DOWN_LABEL}
    </span>
  );
}
