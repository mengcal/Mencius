import { Inter } from "next/font/google";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { Toaster } from "sonner";
import "./globals.css";
import { AuthGate } from "@/app/components/SetupWizard"; // R10.8e：全局登录闸门（client 组件）

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
          {/* R10.8e（管理员："401 死锁，找回入口在进不去的设置页里"）：
              全局登录闸门——所有页面（含 /settings）401 时弹登录层，凭证有效才放行 */}
          <AuthGate>{children}</AuthGate>
        </NuqsAdapter>
        <Toaster />
      </body>
    </html>
  );
}
