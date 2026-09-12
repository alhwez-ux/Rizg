import type { NextConfig } from "next";

const backend = (process.env.API_PROXY_URL || "").replace(/\/$/, "");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  serverExternalPackages: ["@prisma/client", "prisma"],
  outputFileTracingIncludes: {
    "/api/radar/stocks": ["./prisma/dev.db"],
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
