import { copyFileSync, existsSync } from "node:fs";
import path from "node:path";

import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

function databaseUrl(): string {
  if (process.env.VERCEL) {
    const bundled = path.join(process.cwd(), "prisma", "dev.db");
    const writable = "/tmp/rizg-compliance.db";
    if (existsSync(bundled) && !existsSync(writable)) {
      copyFileSync(bundled, writable);
    }
    return `file:${writable}`;
  }
  return process.env.DATABASE_URL ?? "file:./dev.db";
}

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    datasources: { db: { url: databaseUrl() } },
    log: process.env.NODE_ENV === "development" ? ["error", "warn"] : ["error"],
  });

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
