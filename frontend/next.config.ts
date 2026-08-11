import type { NextConfig } from "next";

/**
 * Si NEXT_PUBLIC_API_URL está vacío, el browser habla con /api same-origin
 * y Next reescribe al backend. Así las cookies HttpOnly (path=/api) funcionan
 * en desarrollo sin localStorage.
 */
const proxyTarget = (
  process.env.API_PROXY_TARGET ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    if ((process.env.NEXT_PUBLIC_API_URL || "").trim()) {
      return [];
    }
    return [
      {
        source: "/api/:path*",
        destination: `${proxyTarget}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${proxyTarget}/health`,
      },
      {
        source: "/ready",
        destination: `${proxyTarget}/ready`,
      },
    ];
  },
};

export default nextConfig;
