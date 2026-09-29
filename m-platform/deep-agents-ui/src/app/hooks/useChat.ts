"use client";

import { useCallback } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import {
  type Message,
  type Assistant,
  type Checkpoint,
} from "@langchain/langgraph-sdk";
import { v4 as uuidv4 } from "uuid";
import type { UseStreamThread } from "@langchain/langgraph-sdk/react";
import type { TodoItem } from "@/app/types/types";
import { useClient } from "@/providers/ClientProvider";
import { useQueryState } from "nuqs";

export type StateType = {
  messages: Message[];
  todos: TodoItem[];
  files: Record<string, string>;
  email?: {
    id?: string;
    subject?: string;
    page_content?: string;
  };
  ui?: any;
};

export function useChat({
  activeAssistant,
  onHistoryRevalidate,
  thread,
}: {
  activeAssistant: Assistant | null;
  onHistoryRevalidate?: () => void;
  thread?: UseStreamThread<StateType>;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const client = useClient();

  const stream = useStream<StateType>({
    assistantId: activeAssistant?.assistant_id || "",
    client: client ?? undefined,
    reconnectOnMount: true,
    threadId: threadId ?? null,
    onThreadId: setThreadId,
    defaultHeaders: { "x-auth-scheme": "langsmith" },
    // 切线程只拉最近 50 个检查点（官方分页上限）：全量拉取会随对话变长越来越卡（R38 提速）
    fetchStateHistory: { limit: 50 },
    // Revalidate thread list when stream finishes, errors, or creates new thread
    onFinish: onHistoryRevalidate,
    onError: onHistoryRevalidate,
    onCreated: onHistoryRevalidate,
    experimental_thread: thread,
  });

  const sendMessage = useCallback(
    (
      content: string,
      runOpts?: { model?: string; provider?: string; webSearch?: boolean; thinking?: string; workspace?: string }
    ) => {
      const newMessage: Message = { id: uuidv4(), type: "human", content };
      // 运行级配置随消息走官方 state 通道（run_config.py 中间件消费）
      // R79⑦（NOVA：model/provider/thinking 同 web_search 病只修了一半）：通道按键合并，
      // 条件写=上一轮的旧值粘死（这轮选了模型、下轮"不选"仍用上轮的）。四键恒写；
      // 空串在后端=不换脑/思维档走回退链（run_config._thinking_for），语义闭环。
      const miaConfig: Record<string, unknown> = {
        model: runOpts?.model ?? "",
        provider: runOpts?.provider ?? "",
        web_search: runOpts?.webSearch ?? true,
        thinking: runOpts?.thinking ?? "",
      };
      const input: Record<string, unknown> = { messages: [newMessage], mia_config: miaConfig };
      stream.submit(
        input as any,
        {
          optimisticValues: (prev) => ({
            messages: [...(prev.messages ?? []), newMessage],
          }),
          // r36k（爸令工作区分区）：workspace 随 run 走官方 configurable 通道——
          // 后端 sandbox._route 据此选域（container=沙箱 / host=宿主执行器）；档位只管问不问，两轴正交。
          // r39c（09-29 递归爆案）：100=米娅排障长工具循环必撞墙（当日实测打满 100 层 run 死）→300
          config: { ...(activeAssistant?.config ?? {}), recursion_limit: 300, configurable: { workspace: runOpts?.workspace || "container" } },
          // R3：干活时爸爸再发消息 → 排队接续，不打断后台任务（官方 multitask 机制）
          multitaskStrategy: "enqueue",
        }
      );
      // Update thread list immediately when sending a message
      onHistoryRevalidate?.();
    },
    [stream, activeAssistant?.config, onHistoryRevalidate]
  );

  const runSingleStep = useCallback(
    (
      messages: Message[],
      checkpoint?: Checkpoint,
      isRerunningSubagent?: boolean,
      optimisticMessages?: Message[]
    ) => {
      if (checkpoint) {
        stream.submit(undefined, {
          ...(optimisticMessages
            ? { optimisticValues: { messages: optimisticMessages } }
            : {}),
          config: activeAssistant?.config,
          checkpoint: checkpoint,
          ...(isRerunningSubagent
            ? { interruptAfter: ["tools"] }
            : { interruptBefore: ["tools"] }),
        });
      } else {
        stream.submit(
          { messages },
          { config: activeAssistant?.config, interruptBefore: ["tools"] }
        );
      }
    },
    [stream, activeAssistant?.config]
  );

  const setFiles = useCallback(
    async (files: Record<string, string>) => {
      if (!threadId) return;
      // TODO: missing a way how to revalidate the internal state
      // I think we do want to have the ability to externally manage the state
      await client.threads.updateState(threadId, { values: { files } });
    },
    [client, threadId]
  );

  // r39h（爸令消息编辑）：官方 updateState 原语按同 id 覆盖用户消息文本——
  // langgraph 每轮从 state 重建模型输入，米娅下一轮读到的就是修正版（打错字根治）。
  // 不截断历史不重跑：改完想让她重做，补一句即可（可控>自动）。
  const editMessage = useCallback(
    async (messageId: string, newText: string) => {
      if (!threadId || !messageId || !newText.trim()) return;
      await client.threads.updateState(threadId, {
        values: { messages: [{ type: "human", content: newText, id: messageId }] },
      });
      onHistoryRevalidate?.();
    },
    [client, threadId, onHistoryRevalidate]
  );

  const continueStream = useCallback(
    (hasTaskToolCall?: boolean) => {
      stream.submit(undefined, {
        config: {
          ...(activeAssistant?.config || {}),
          recursion_limit: 300, // r39c 同病补刀：批准续跑路也吃 100 上限（发送路已修，这漏了）
        },
        ...(hasTaskToolCall
          ? { interruptAfter: ["tools"] }
          : { interruptBefore: ["tools"] }),
      });
      // Update thread list when continuing stream
      onHistoryRevalidate?.();
    },
    [stream, activeAssistant?.config, onHistoryRevalidate]
  );

  const markCurrentThreadAsResolved = useCallback(() => {
    stream.submit(null, { command: { goto: "__end__", update: null } });
    // Update thread list when marking thread as resolved
    onHistoryRevalidate?.();
  }, [stream, onHistoryRevalidate]);

  const resumeInterrupt = useCallback(
    (value: any) => {
      stream.submit(null, { command: { resume: value } });
      // Update thread list when resuming from interrupt
      onHistoryRevalidate?.();
    },
    [stream, onHistoryRevalidate]
  );

  const stopStream = useCallback(() => {
    stream.stop();
  }, [stream]);

  return {
    stream,
    todos: stream.values.todos ?? [],
    files: stream.values.files ?? {},
    email: stream.values.email,
    ui: stream.values.ui,
    setFiles,
    editMessage,
    messages: stream.messages,
    isLoading: stream.isLoading,
    isThreadLoading: stream.isThreadLoading,
    interrupt: stream.interrupt,
    getMessagesMetadata: stream.getMessagesMetadata,
    sendMessage,
    runSingleStep,
    continueStream,
    stopStream,
    markCurrentThreadAsResolved,
    resumeInterrupt,
  };
}
