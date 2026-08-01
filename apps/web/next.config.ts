import type { NextConfig } from "next";

function buildConnectSrc(): string {
  const sources = new Set(["'self'", "https:", "wss:"]);
  const publicApiUrl = process.env.NEXT_PUBLIC_API_URL;

  if (publicApiUrl) {
    try {
      sources.add(new URL(publicApiUrl).origin);
    } catch {
      // Ignore invalid env values here; app env validation handles them separately.
    }
  }

  if (process.env.ENVIRONMENT !== "production") {
    sources.add("http://localhost:8080");
    sources.add("http://127.0.0.1:8080");
  }

  return Array.from(sources).join(" ");
}

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: new URL("../../", import.meta.url).pathname,
  poweredByHeader: false,
  reactStrictMode: true,
  transpilePackages: ["@healthos/api-types", "@healthos/ui", "@healthos/utils"],
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          { key: "Cross-Origin-Resource-Policy", value: "same-origin" },
          {
            key: "Content-Security-Policy",
            value:
              `default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; object-src 'none'; img-src 'self' data: blob:; font-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src ${buildConnectSrc()}`,
          },
        ],
      },
      {
        source: "/(dashboard|profile|portal)/(.*)",
        headers: [
          { key: "Cache-Control", value: "private, no-store, max-age=0" },
        ],
      },
    ];
  },
};

export default nextConfig;
