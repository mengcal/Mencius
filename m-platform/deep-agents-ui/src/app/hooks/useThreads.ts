import useSWRInfinite from "swr/infinite";
import type { Thread } from "@langchain/langgraph-sdk";
import { Client } from "@langchain/langgraph-sdk";
import { getConfig } from "@/lib/config";
import { getAdminToken } from "@/lib/providerApi";  // R10（千问 P1-3）：threads.search 走 langgraph 原生 API，auth 模块要 Bearer

export interface ThreadItem {
  id: string;
  updatedAt: Date;
  status: Thread["status"];
  title: string;
  description: string;
  assistantId?: string;
  pinned?: boolean;
}

const DEFAULT_PAGE_SIZE = 20;

export function useThreads(props: {
  status?: Thread["status"];
  limit?: number;
}) {
  const pageSize = props.limit || DEFAULT_PAGE_SIZE;

  return useSWRInfinite(
    (pageIndex: number, previousPageData: ThreadItem[] | null) => {
      const config = getConfig();
      const apiKey =
        config?.langsmithApiKey ||
        process.env.NEXT_PUBLIC_LANGSMITH_API_KEY ||
        "";

      if (!config) {
        return null;
      }

      // If the previous page returned no items, we've reached the end
      if (previousPageData && previousPageData.length === 0) {
        return null;
      }

      return {
        kind: "threads" as const,
        pageIndex,
        pageSize,
        deploymentUrl: config.deploymentUrl,
        assistantId: config.assistantId,
        apiKey,
        status: props?.status,
      };
    },
    async ({
      deploymentUrl,
      assistantId,
      apiKey,
      status,
      pageIndex,
      pageSize,
    }: {
      kind: "threads";
      pageIndex: number;
      pageSize: number;
      deploymentUrl: string;
      assistantId: string;
      apiKey: string;
      status?: Thread["status"];
    }) => {
      const _t = getAdminToken();
      // R10.8e（爸爸"401 死锁"）：裸 Client 也走同源 /lg 代理——Cookie 自动携带（same-origin），
      // 不再直连 2024 跨源（SameSite=Strict cookie 跨源 fetch 不发送=必 401）
      const client = new Client({
        apiUrl: `${window.location.origin}/lg`,
        defaultHeaders: { ...(apiKey ? { "X-Api-Key": apiKey } : {}), ...(_t ? { Authorization: `Bearer ${_t}` } : {}) },
        onRequest: (_url, init) => ({ ...init, credentials: "include" }),
      });

      // Check if assistantId is a UUID (deployed) or graph name (local)
      const isUUID =
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
          assistantId
        );

      const threads = await client.threads.search({
        limit: pageSize,
        offset: pageIndex * pageSize,
        sortBy: "updated_at" as const,
        sortOrder: "desc" as const,
        status,
        // Only filter by assistant_id metadata for deployed graphs (UUIDs)
        // Local dev graphs don't set this metadata
        ...(isUUID ? { metadata: { assistant_id: assistantId } } : {}),
      });

      // R57：牛马任务线程（后台派活的执行线程）不进对话历史侧栏，在牛马进程面板看
      const normal = threads.filter(
        (t: any) => !((t.metadata as any)?.cow_task === true)
      );
      const items = normal.map((thread): ThreadItem => {
        let title = "Untitled Thread";
        let description = "";

        try {
          if (thread.values && typeof thread.values === "object") {
            const values = thread.values as any;
            const firstHumanMessage = values.messages.find(
              (m: any) => m.type === "human"
            );
            if (firstHumanMessage?.content) {
              const content =
                typeof firstHumanMessage.content === "string"
                  ? firstHumanMessage.content
                  : firstHumanMessage.content[0]?.text || "";
              // 换行/连续空白压成单空格再截断——多行消息原样截取会撑破单行布局
              const flat = content.replace(/\s+/g, " ").trim();
              title = flat.slice(0, 50) + (flat.length > 50 ? "..." : "");
            }
            const firstAiMessage = values.messages.find(
              (m: any) => m.type === "ai"
            );
            if (firstAiMessage?.content) {
              const content =
                typeof firstAiMessage.content === "string"
                  ? firstAiMessage.content
                  : firstAiMessage.content[0]?.text || "";
              description = content.slice(0, 100);
            }
          }
        } catch {
          // Fallback to thread ID
          title = `Thread ${thread.thread_id.slice(0, 8)}`;
        }
        // 用户自定义标题（对话"改名"）优先
        const customTitle = (thread.metadata as any)?.custom_title;
        if (typeof customTitle === "string" && customTitle.trim()) {
          title = customTitle;
        }

        return {
          id: thread.thread_id,
          updatedAt: new Date(thread.updated_at),
          status: thread.status,
          title,
          description,
          assistantId,
          pinned: (thread.metadata as any)?.pinned === true,
        };
      });
      // r32（爸爸 09-26"后台任务怎么还在左侧对话框里"）：AsyncSubAgent 派活线程由官方件
      // 裸 threads.create()（deepagents/middleware/async_subagents.py:263，无元数据可标），
      // 其首条消息=派活文本、固定带"后台任务"前缀（米娅派活口径）——按标题前缀滤出，
      // 任务状态在任务面板看，不占对话历史侧栏。
      return items.filter((t) => !t.title.startsWith("后台任务"));
    },
    {
      revalidateFirstPage: true,
      revalidateOnFocus: true,
    }
  );
}
