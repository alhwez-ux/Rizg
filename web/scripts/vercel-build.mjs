import { existsSync, unlinkSync } from "node:fs";
import { spawnSync } from "node:child_process";

process.env.DATABASE_URL ||= "file:./dev.db";

// Prisma 6 errors when DATABASE_URL exists in both `.env` (Vercel) and `prisma/.env`.
if (existsSync("prisma/.env")) {
  unlinkSync("prisma/.env");
}

const steps = [
  ["prisma", ["generate"]],
  ["prisma", ["db", "push"]],
  ["tsx", ["prisma/seed.ts"]],
  ["next", ["build"]],
];

for (const [cmd, args] of steps) {
  const result = spawnSync(cmd, args, { stdio: "inherit", env: process.env, shell: true });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
