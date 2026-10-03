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
          {/* 10-03 登录页退役（爸爸裁决：本地软件登录页只是习惯无安全价值，OWUI/ZCode/DSH 均无此物）：
              AuthGate 全局闸门拆除——打开即用。AuthPage.tsx 文件暂留（authLogout 仍被引用），下次清理。 */}
          {children}
        </NuqsAdapter>
        <Toaster />
      </body>
    </html>
  );
}
