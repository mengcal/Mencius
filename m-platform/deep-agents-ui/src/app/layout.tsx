import { Inter } from "next/font/google";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { Toaster } from "sonner";
import "./globals.css";
import { AuthGate } from "@/app/components/AuthPage"; // r31（09-26 爸爸令）：登录/注册合一页面

const inter = Inter({ subsets: ["latin"] });

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="zh-CN"
      data-joy-color-scheme="dark"
      suppressHydrationWarning
    >
      <body
        className={inter.className}
        suppressHydrationWarning
      >
        <NuqsAdapter>
          {/* 10-03 爸爸终审澄清：登录页保留（习惯性功能）；退役的是守卫服务——
              /auth/login 已本地化（密码 hash 存 .settings_secrets，不再依赖 m-guard） */}
          <AuthGate>{children}</AuthGate>
        </NuqsAdapter>
        <Toaster />
      </body>
    </html>
  );
}
