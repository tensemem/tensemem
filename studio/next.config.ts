import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const target = process.env.TENSEMEM_URL ?? "http://127.0.0.1:8080";
    return [{ source: "/v1/:path*", destination: `${target}/v1/:path*` }];
  },
};

export default nextConfig;
