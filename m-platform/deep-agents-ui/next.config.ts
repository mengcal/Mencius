import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // R10.312（爸爸"全力搞这个模式"）：移动端 Tailscale 直连 dev 服务器必需——
  // Next 16 默认只信任 localhost 的 dev 资源请求，手机经 Tailscale IP/域名访问会被拦成白屏。
  // R10.416（09-23 晚，爸爸手机白屏实锤）：家里 WiFi 直连也走同一道闸——
  // dev log 点名 "add it to allowedDevOrigins: 192.168.1.6"，补局域网段。
  allowedDevOrigins: ["127.0.0.1", "localhost", "*.ts.net", "192.168.1.6", "192.168.1.*"],
  async rewrites() {
    return [
      // R10.8e（爸爸："401 死锁，找回入口在进不去的设置页里"）：
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
