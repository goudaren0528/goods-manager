import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  output: "standalone",
  reactCompiler: true,
  async rewrites() {
    // Priority: INTERNAL_API_URL (runtime) > NEXT_PUBLIC_API_URL (build/runtime) > Default
    const rawUrl = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://server:8000";
    
    // Safety check: if rawUrl is empty or just whitespace, fallback to default
    const cleanUrl = (rawUrl.trim() === "" || rawUrl.trim() === "undefined") 
      ? "http://server:8000" 
      : rawUrl.replace(/^["'`]|["'`]$/g, "").trim();

    const destination = `${cleanUrl}/:path*`;
    
    console.log(`[Next.js Rewrite] Proxying /api requests to: ${destination}`);
    
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
