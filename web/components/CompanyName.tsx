import { displayCompanyTitle } from "@/lib/listedCompanies";

export function CompanyName({
  symbol,
  name,
  align = "center",
}: {
  symbol: string;
  name?: string | null;
  align?: "center" | "start";
}) {
  const title = displayCompanyTitle(symbol, name || "");
  return (
    <span className={`inline-flex min-w-0 flex-wrap items-center gap-2 ${align === "start" ? "justify-start" : "justify-center"}`}>
      {title ? <span className="font-bold text-zinc-50">{title}</span> : null}
      <span className="font-mono text-xs font-normal text-zinc-400" dir="ltr">
        {symbol}
      </span>
    </span>
  );
}
