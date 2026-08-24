import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  transpilePackages: ["@mecha/api-client"],
  experimental: {
    // TypeScript 7 (tsgo) has no in-process compiler API; use its CLI.
    useTypeScriptCli: true,
  },
  async rewrites() {
    // The browser talks to one origin; Next proxies /api/* to FastAPI.
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
