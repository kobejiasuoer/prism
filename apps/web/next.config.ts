import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
        destination: "http://localhost:8000/api/:path*",
      },
      {
        source: "/artifacts",
        destination: "http://localhost:8000/artifacts",
      },
      {
        source: "/healthz",
        destination: "http://localhost:8000/healthz",
      },
    ];
  },
};

export default nextConfig;
