import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

function loadEnvFile(filename: string): void {
  const path = resolve(process.cwd(), filename);
  if (!existsSync(path)) return;

  for (const rawLine of readFileSync(path, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (!process.env[key]) process.env[key] = value;
  }
}

loadEnvFile(".env.local");
loadEnvFile(".env");

async function main(): Promise<void> {
  const { getActiveStocksForRadar, getStockHistory, seedRadarStocks } = await import(
    "../lib/firebase"
  );

  const seeded = await seedRadarStocks();
  console.log("Seeded radar stocks:", seeded);

  const active = await getActiveStocksForRadar();
  console.log(
    "Radar-eligible stocks (PROHIBITED excluded):",
    active.map((stock) => `${stock.symbol} ${stock.companyNameAr} [${stock.currentStatus}]`),
  );

  for (const stock of active) {
    const history = await getStockHistory(stock.symbol);
    console.log(`${stock.symbol} history:`, history);
  }
}

main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
