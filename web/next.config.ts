import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  output: "standalone",
  reactCompiler: true,
  async rewrites() {
    return {
      afterFiles: [
        {
          source: '/api/:path*',
          destination: process.env.INTERNAL_API_URL 
            ? `${process.env.INTERNAL_API_URL}/:path*` 
            : 'http://server:8000/:path*', // Proxy to backend
        },
      ],
      fallback: [
        {
          source: '/:path*',
          destination: process.env.INTERNAL_API_URL 
            ? `${process.env.INTERNAL_API_URL}/:path*` 
            : 'http://server:8000/:path*', // Proxy all other requests to backend
        },
      ],
    }
  },
};

export default nextConfig;
