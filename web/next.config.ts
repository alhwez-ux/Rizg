import type { NextConfig } from "next";

const backend = (process.env.API_PROXY_URL || "").replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  serverExternalPackages: ["@prisma/client", "prisma"],
  outputFileTracingIncludes: {
    "/api/radar/stocks": ["./prisma/dev.db"],
  },
  async headers() {
    const noStore = [
      { key: "Cache-Control", value: "private, no-store, no-cache, must-revalidate, max-age=0" },
      { key: "Pragma", value: "no-cache" },
      { key: "CDN-Cache-Control", value: "no-store" },
      { key: "Vercel-CDN-Cache-Control", value: "no-store" },
    ];
    return [
      { source: "/:path*", headers: noStore },
      { source: "/sw.js", headers: noStore },
      { source: "/version.json", headers: noStore },
    ];
  },
  async rewrites() {
    if (!backend) return [];
    return [
      { source: "/api/v1/:path*", destination: `${backend}/api/v1/:path*` },
      { source: "/health", destination: `${backend}/health` },
    ];
  },
};

export default nextConfig;
