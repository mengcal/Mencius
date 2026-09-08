'use client';

/**
 * components/chat/chatUtils.tsx —— 对话消息处理纯函数（原 ChatInterface.tsx 迁出）
 * ------------------------------------------------------------------
 * - getStatusIcon：TODO 状态图标（completed/in_progress/默认）
 * - processMessages：把 LangGraph 消息流折叠成 { message, toolCalls, showAvatar } 数组
 *   （1. 遍历所有消息；2. AI 消息连同 tool_calls 入 messageMap；3. tool 消息回填对应 tool call 的状态与输出）
 * - buildAutoReportGroups：R59 自动汇报折叠——把 "[工作者调度·自动汇报]" 指令 + 紧随的助手回复合并成一组
 *
 * 注意：计划名为 chatUtils.ts，因 getStatusIcon 返回 JSX（React 元素），.ts 无法承载，故用 .tsx。
 */

import { CheckCircle, Clock, Circle } from "lucide-react";
import type { Message } from "@langchain/langgraph-sdk";
import type { TodoItem, ToolCall } from "@/app/types/types";
import { extractStringFromMessageContent } from "@/app/utils/utils";
import { cn } from "@/lib/utils";

export const getStatusIcon = (status: TodoItem["status"], className?: string) => {
  switch (status) {
    case "completed":
      return (
        <CheckCircle
          size={16}
          className={cn("text-success/80", className)}
        />
      );
    case "in_progress":
      return (
        <Clock
          size={16}
          className={cn("text-warning/80", className)}
        />
      );
    default:
      return (
        <Circle
          size={16}
          className={cn("text-tertiary/70", className)}
        />
      );
  }
};

export type ProcessedMessage = {
  message: Message;
  toolCalls: ToolCall[];
  showAvatar: boolean;
};

export function processMessages(
  messages: Message[],
  interrupt: any
): ProcessedMessage[] {
  /*
   1. Loop through all messages
   2. For each AI message, add the AI message, and any tool calls to the messageMap
   3. For each tool message, find the corresponding tool call in the messageMap and update the status and output
  */
  const messageMap = new Map<
    string,
    { message: Message; toolCalls: ToolCall[] }
  >();
  messages.forEach((message: Message) => {
    if (message.type === "ai") {
      const toolCallsInMessage: Array<{
        id?: string;
        function?: { name?: string; arguments?: unknown };
        name?: string;
        type?: string;
        args?: unknown;
        input?: unknown;
      }> = [];
      if (
        message.additional_kwargs?.tool_calls &&
        Array.isArray(message.additional_kwargs.tool_calls)
      ) {
        toolCallsInMessage.push(...message.additional_kwargs.tool_calls);
      } else if (message.tool_calls && Array.isArray(message.tool_calls)) {
        toolCallsInMessage.push(
          ...message.tool_calls.filter(
            (toolCall: { name?: string }) => toolCall.name !== ""
          )
        );
      } else if (Array.isArray(message.content)) {
        const toolUseBlocks = message.content.filter(
          (block: { type?: string }) => block.type === "tool_use"
        );
        toolCallsInMessage.push(...toolUseBlocks);
      }
      const toolCallsWithStatus = toolCallsInMessage.map(
        (toolCall: {
          id?: string;
          function?: { name?: string; arguments?: unknown };
          name?: string;
          type?: string;
          args?: unknown;
          input?: unknown;
        }) => {
          const name =
            toolCall.function?.name ||
            toolCall.name ||
            toolCall.type ||
            "unknown";
          const args =
            toolCall.function?.arguments ||
            toolCall.args ||
            toolCall.input ||
            {};
          return {
            id: toolCall.id || `tool-${Math.random()}`,
            name,
            args,
            status: interrupt ? "interrupted" : ("pending" as const),
          } as ToolCall;
        }
      );
      messageMap.set(message.id!, {
        message,
        toolCalls: toolCallsWithStatus,
      });
    } else if (message.type === "tool") {
      const toolCallId = message.tool_call_id;
      if (!toolCallId) {
        return;
      }
      for (const [, data] of messageMap.entries()) {
        const toolCallIndex = data.toolCalls.findIndex(
          (tc: ToolCall) => tc.id === toolCallId
        );
        if (toolCallIndex === -1) {
          continue;
        }
        data.toolCalls[toolCallIndex] = {
          ...data.toolCalls[toolCallIndex],
          status: "completed" as const,
          result: extractStringFromMessageContent(message),
        };
        break;
      }
    } else if (message.type === "human") {
      messageMap.set(message.id!, {
        message,
        toolCalls: [],
      });
    }
  });
  const processedArray = Array.from(messageMap.values());
  return processedArray.map((data, index) => {
    const prevMessage = index > 0 ? processedArray[index - 1].message : null;
    return {
      ...data,
      showAvatar: data.message.type !== prevMessage?.type,
    };
  });
}

/** R59 自动汇报折叠：把 "[工作者调度·自动汇报]" 指令 + 紧随的助手回复合并成一组，
 *    对话流里默认折成一行（点开才展开）——官方 expandedSubAgents 同款 state+toggle 范式 */
export function buildAutoReportGroups(
  processedMessages: ProcessedMessage[]
): {
  groups: Map<string, { tid: string; done: boolean; bodyContent: string }>;
  bodyToHead: Map<string, string>;
} {
  const groups = new Map<
    string,
    { tid: string; done: boolean; bodyContent: string }
  >();
  const bodyToHead = new Map<string, string>();
  for (let i = 0; i < processedMessages.length - 1; i++) {
    const cur = processedMessages[i].message;
    if (cur.type !== "human") continue;
    const content = extractStringFromMessageContent(cur);
    if (!content.startsWith("[工作者调度·自动汇报]")) continue;
    const body = processedMessages[i + 1].message;
    if (body.type !== "ai") continue;
    groups.set(cur.id!, {
      tid: (content.match(/任务\s*(bk_\d+)/) || [])[1] || "",
      done: content.includes("已完成"),
      bodyContent: extractStringFromMessageContent(body),
    });
    bodyToHead.set(body.id!, cur.id!);
  }
  return { groups, bodyToHead };
}
