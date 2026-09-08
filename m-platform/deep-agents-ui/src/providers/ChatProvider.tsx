"use client";

import { ReactNode, createContext, useContext } from "react";
import { Assistant } from "@langchain/langgraph-sdk";
import { useChat } from "@/app/hooks/useChat";
import { useQueryState } from "nuqs";
import { API, apiFetch } from "@/lib/apiBase";
import { getAdminToken } from "@/lib/providerApi";

interface ChatProviderProps {
  children: ReactNode;
  activeAssistant: Assistant | null;
  onHistoryRevalidate?: () => void;
}

export function ChatProvider({
  children,
  activeAssistant,
  onHistoryRevalidate,
}: ChatProviderProps) {
  // R45 自动起名：对话流结束时请后端给新对话起标题（glm-4.5-air，静默失败不影响），再刷新侧栏
  // R59 修正：原 thread?.thread_id 读的是从未传入的 experimental_thread，运行时恒为 undefined
  //   （自动起名一直静默失效）；改读与 useChat 同源的 URL threadId，让功能真正生效
  const [threadId] = useQueryState("threadId");
  const handleRevalidate = () => {
    const tid = threadId;
    if (tid) {
      // R79（hy4 低危项入守）：/threads/title 进 token 门，写标题带上管理员密钥（管理员浏览器有；
      // 无 token 环境=标题不更新，静默失败不影响聊天本身，防任意人往线程灌垃圾标题+白烧 LLM）
      const t = getAdminToken();
      apiFetch(`${API}/threads/title`, {  // R68：相对路径在 dev(:3000) 打到 Next 自身=404（R57 同款坑复发），改走 API 基址；R10.5 改 apiFetch（带凭据，Cookie 过守卫）
        method: "POST",
        headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
        body: JSON.stringify({ thread_id: tid }),
      }).catch(() => {});
    }
    onHistoryRevalidate?.();
  };
  const chat = useChat({ activeAssistant, onHistoryRevalidate: handleRevalidate });
  return <ChatContext.Provider value={chat}>{children}</ChatContext.Provider>;
}

export type ChatContextType = ReturnType<typeof useChat>;

export const ChatContext = createContext<ChatContextType | undefined>(
  undefined
);

export function useChatContext() {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error("useChatContext must be used within a ChatProvider");
  }
  return context;
}
