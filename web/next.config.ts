import type { NextConfig } from "next";

// The browser calls /api/*; Next forwards it to the ANT-OS API, so no CORS is needed.
const apiUrl = process.env.ANTOS_API_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
        ],
      },
    ];
  },
};

export default config;
