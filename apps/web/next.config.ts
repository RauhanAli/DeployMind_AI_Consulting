import type { NextConfig } from "next";

const api = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  transpilePackages: ["@deploymind/shared"],
  poweredByHeader: false,
  // Same-origin proxy to FastAPI: lets the httpOnly refresh cookie work without cross-site cookies.
  // Note: rewrites are resolved at build time; set API_INTERNAL_URL when running `next build`.
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${api}/api/v1/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
