import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // R10.8e（管理员："401 死锁，找回入口在进不去的设置页里"）：
      // same-origin 代理——前端所有 API 调用走 /lg/*（same-origin），Cookie 自动携带，
      // 彻底消灭跨源 CORS/credentials/SameSite 问题。
      {
        source: "/lg/:path*",
        destination: "http://127.0.0.1:2024/:path*",
      },
    ];
  },
};

export default nextConfig;
