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
      ],
    };
  },
};

export default nextConfig;
