import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  output: "standalone",
  reactCompiler: true,
  async rewrites() {
    const destination = process.env.INTERNAL_API_URL
      ? `${process.env.INTERNAL_API_URL}/:path*`
      : "http://server:8000/:path*";
    return {
      afterFiles: [
        { source: "/api/:path*", destination },
        { source: "/goods/:path*", destination },
        { source: "/run-scrape", destination },
        { source: "/run-scrape-partial", destination },
        { source: "/prepare-update", destination },
        { source: "/trigger-update", destination },
        { source: "/logs", destination },
        { source: "/task-status", destination },
        { source: "/stop-task", destination },
        { source: "/config", destination },
        { source: "/rent-curves/:path*", destination },
        { source: "/automation/:path*", destination },
        { source: "/export-excel", destination },
      ],
    };
  },
};

export default nextConfig;
