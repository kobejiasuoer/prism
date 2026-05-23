import type { NextConfig } from "next";

const backendOrigin =
  process.env.PRISM_BACKEND_ORIGIN ??
  process.env.NEXT_PUBLIC_PRISM_BACKEND_ORIGIN ??
  "http://127.0.0.1:8001";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_PRISM_BACKEND_ORIGIN: backendOrigin,
  },
  async redirects() {
    return [
      {
        source: "/today",
        destination: "/",
        permanent: false,
      },
      {
        source: "/ask",
        has: [
          {
            type: "query",
            key: "q",
            value: "(?<code>\\d{6})",
          },
        ],
        destination: "/stock/:code",
        permanent: false,
      },
      {
        source: "/ask",
        destination: "/",
        permanent: false,
      },
      {
        source: "/watchlist",
        destination: "/portfolio",
        permanent: false,
      },
      {
        source: "/watchlist/:code(\\d{6})",
        destination: "/stock/:code",
        permanent: false,
      },
      {
        source: "/today/watchlist/:code(\\d{6})",
        destination: "/stock/:code",
        permanent: false,
      },
      {
        source: "/opportunities",
        destination: "/discovery",
        permanent: false,
      },
      {
        source: "/opportunities/batch/:kind",
        destination: "/discovery",
        permanent: false,
      },
      {
        source: "/opportunities/:code(\\d{6})",
        destination: "/stock/:code",
        permanent: false,
      },
      {
        source: "/review/detail",
        destination: "/review",
        permanent: false,
      },
      {
        source: "/today/candidates/:code(\\d{6})",
        destination: "/stock/:code",
        permanent: false,
      },
      {
        source: "/today/batch/:kind",
        destination: "/discovery",
        permanent: false,
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/api/:path*`,
      },
      {
        source: "/artifacts",
        destination: `${backendOrigin}/artifacts`,
      },
      {
        source: "/healthz",
        destination: `${backendOrigin}/healthz`,
      },
    ];
  },
};

export default nextConfig;
