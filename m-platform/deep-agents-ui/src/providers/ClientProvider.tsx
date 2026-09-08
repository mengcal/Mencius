"use client";

import { createContext, useContext, useMemo, ReactNode } from "react";
import { Client } from "@langchain/langgraph-sdk";
import { getAdminToken } from "@/lib/providerApi";

interface ClientContextValue {
  client: Client;
}

const ClientContext = createContext<ClientContextValue | null>(null);

interface ClientProviderProps {
  children: ReactNode;
  deploymentUrl: string;
  apiKey: string;
}

export function ClientProvider({
  children,
  deploymentUrl,
  apiKey,
}: ClientProviderProps) {
  const client = useMemo(() => {
    // R80（评审C b 纵深）：langgraph 原生 API 进 auth 模块（Bearer=管理员密钥）——
    // 浏览器主 SDK 客户端带上钥匙；无钥匙=聊天页 401（fail-closed 首部署引导）。
    // R10.5 XSS L2：onRequest 注入 credentials:'include'——原生 API 也走 HttpOnly Cookie，
    // localStorage 不再是钥匙存放地（apiKey 头保留读取兼容，迁移期后自然为空）。
    const t = getAdminToken();
    return new Client({
      apiUrl: deploymentUrl,
      defaultHeaders: {
        "Content-Type": "application/json",
        "X-Api-Key": apiKey,
        ...(t ? { Authorization: `Bearer ${t}` } : {}),
      },
      onRequest: (_url, init) => ({ ...init, credentials: "include" }),
    });
  }, [deploymentUrl, apiKey]);

  const value = useMemo(() => ({ client }), [client]);

  return (
    <ClientContext.Provider value={value}>{children}</ClientContext.Provider>
  );
}

export function useClient(): Client {
  const context = useContext(ClientContext);

  if (!context) {
    throw new Error("useClient must be used within a ClientProvider");
  }
  return context.client;
}
