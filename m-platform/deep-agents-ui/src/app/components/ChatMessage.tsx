"use client";

import React, { useMemo, useState, useCallback, useEffect } from "react";
import { SubAgentIndicator } from "@/app/components/SubAgentIndicator";
import { ToolCallBox } from "@/app/components/ToolCallBox";
import { MarkdownContent } from "@/app/components/MarkdownContent";
import type {
  SubAgent,
  ToolCall,
  ActionRequest,
  ReviewConfig,
} from "@/app/types/types";
import { Message } from "@langchain/langgraph-sdk";
import {
  extractSubAgentContent,
  extractStringFromMessageContent,
} from "@/app/utils/utils";
import { cn } from "@/lib/utils";

// R64 消息时间戳格式化：UTC ISO → 北京时间 HH:MM（前端渲染，零令牌）
const fmtBJ = (iso?: string) => {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString("zh-CN", {
      timeZone: "Asia/Shanghai",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  } catch {
    return "";
  }
};

interface ChatMessageProps {
  message: Message;
  toolCalls: ToolCall[];
  isLoading?: boolean;
  actionRequestsMap?: Map<string, ActionRequest>;
  reviewConfigsMap?: Map<string, ReviewConfig>;
  ui?: any[];
  stream?: any;
  onResumeInterrupt?: (value: any) => void;
  graphId?: string;
  // R64 消息时间戳（checkpoint created_at，UTC ISO）——前端渲染，不烧令牌
  createdAt?: string;
  // R59 自动汇报折叠：父层把 "[工作者调度·自动汇报]" 指令 + 助手回复合并成一组传入
  autoReport?: {
    tid: string;
    done: boolean;
    bodyContent: string;
    open: boolean;
    onToggle: () => void;
  };
}

export const ChatMessage = React.memo<ChatMessageProps>(
  ({
    message,
    toolCalls,
    isLoading,
    actionRequestsMap,
    reviewConfigsMap,
    ui,
    stream,
    onResumeInterrupt,
    graphId,
    createdAt,
    autoReport,
  }) => {
    const isUser = message.type === "human";
    const messageContent = extractStringFromMessageContent(message);
    const hasContent = messageContent && messageContent.trim() !== "";
    const hasToolCalls = toolCalls.length > 0;
    const [toolsOpen, setToolsOpen] = useState(false); // R54 工人岗进程折叠：默认收起，想看才展开
    // R46 工具显隐即时生效：状态化 + 监听 storage/自定义事件（原先每渲染直读 localStorage，切开关不刷新就无效）
    const [showTools, setShowTools] = useState(
      typeof window !== "undefined" ? localStorage.getItem("mia.showToolCalls") !== "false" : true
    );
    useEffect(() => {
      const read = () => setShowTools(localStorage.getItem("mia.showToolCalls") !== "false");
      read();
      window.addEventListener("storage", read);
      window.addEventListener("mia-tool-visibility", read);
      return () => {
        window.removeEventListener("storage", read);
        window.removeEventListener("mia-tool-visibility", read);
      };
    }, []);
    const subAgents = useMemo(() => {
      return toolCalls
        .filter((toolCall: ToolCall) => {
          return (
            toolCall.name === "task" &&
            toolCall.args["subagent_type"] &&
            toolCall.args["subagent_type"] !== "" &&
            toolCall.args["subagent_type"] !== null
          );
        })
        .map((toolCall: ToolCall) => {
          const subagentType = (toolCall.args as Record<string, unknown>)[
            "subagent_type"
          ] as string;
          return {
            id: toolCall.id,
            name: toolCall.name,
            subAgentName: subagentType,
            input: toolCall.args,
            output: toolCall.result ? { result: toolCall.result } : undefined,
            status: toolCall.status,
          } as SubAgent;
        });
    }, [toolCalls]);

    const [expandedSubAgents, setExpandedSubAgents] = useState<
      Record<string, boolean>
    >({});
    const isSubAgentExpanded = useCallback(
      (id: string) => expandedSubAgents[id] ?? true,
      [expandedSubAgents]
    );
    const toggleSubAgent = useCallback((id: string) => {
      setExpandedSubAgents((prev) => ({
        ...prev,
        [id]: prev[id] === undefined ? false : !prev[id],
      }));
    }, []);

    // R59 自动汇报折叠：整组（指令 + 助手回复）默认折成一行，点开才展开。
    // 官方 expandedSubAgents 同款范式（state + toggle + 条件渲染），样式对齐 R54 工具折叠行
    if (autoReport) {
      return (
        <div className="flex w-full max-w-full overflow-x-hidden">
          <div className="w-full">
            <button
              type="button"
              onClick={autoReport.onToggle}
              className="flex w-full items-center gap-2 rounded-md border border-gray-100 bg-gray-50 px-2 py-1 text-left text-[0.6875rem] text-gray-500 transition-colors hover:bg-accent dark:border-gray-900 dark:bg-gray-900 dark:hover:bg-accent"
            >
              <span>{autoReport.open ? "▾" : "▸"}</span>
              <span>
                🐂 后台任务 {autoReport.tid}{" "}
                {autoReport.done ? "已完成" : "已结束"}
                {createdAt && (
                  <span className="ml-1 text-muted-foreground/60">
                    🕐 {fmtBJ(createdAt)}
                  </span>
                )}
                {!autoReport.open && (
                  <span className="ml-1 opacity-70">助手汇报 · 点击展开</span>
                )}
              </span>
            </button>
            {autoReport.open && (
              <div className="mt-2 flex w-full flex-col gap-3 rounded-md border border-border bg-background p-3">
                <div className="whitespace-pre-wrap break-words text-xs text-muted-foreground">
                  {messageContent}
                </div>
                <MarkdownContent content={autoReport.bodyContent} />
              </div>
            )}
          </div>
        </div>
      );
    }

    return (
      <div
        className={cn(
          "flex w-full max-w-full overflow-x-hidden",
          isUser && "flex-row-reverse"
        )}
      >
        <div
          className={cn(
            "min-w-0 max-w-full",
            isUser ? "max-w-[70%]" : "w-full"
          )}
        >
          {hasContent && (
            <div className={cn("relative flex items-end gap-0")}>
              <div
                className={cn(
                  "mt-4 overflow-hidden break-words text-sm font-normal leading-[150%]",
                  isUser
                    ? "rounded-xl rounded-br-none border border-border px-3 py-2 text-foreground"
                    : "text-primary"
                )}
                style={
                  isUser
                    ? { backgroundColor: "var(--color-user-message-bg)" }
                    : undefined
                }
              >
                {isUser && messageContent.startsWith("[工作者调度·自动汇报]") ? (
                  // R57 后台任务汇报折叠：自动汇报原文默认收起，想看才展开
                  <details className="w-full text-xs text-muted-foreground">
                    <summary className="cursor-pointer select-none">
                      📣 后台任务汇报原文（点击展开）
                    </summary>
                    <pre className="mt-1 whitespace-pre-wrap break-words rounded bg-gray-900 p-2 text-[0.6875rem] text-gray-300">
                      {messageContent}
                    </pre>
                  </details>
                ) : isUser ? (
                  <p className="m-0 whitespace-pre-wrap break-words text-sm leading-relaxed">
                    {messageContent}
                  </p>
                ) : hasContent ? (
                  <MarkdownContent content={messageContent} />
                ) : null}
              </div>
            </div>
          )}
          {/* R64 消息时间戳：北京时间 HH:MM，前端渲染零令牌 */}
          {hasContent && createdAt && (
            <div
              className={cn(
                "mt-1 text-[0.625rem] text-muted-foreground/70",
                isUser ? "text-right" : "text-left"
              )}
            >
              🕐 {fmtBJ(createdAt)}
            </div>
          )}
          {hasToolCalls && showTools && (
            <div className="mt-4 flex w-full flex-col">
              {(() => {
                // R54 工人岗进程折叠：工具调用默认收成一行摘要，点击展开详情（想看才看，不混淆对话流）
                const visible = toolCalls.filter(
                  (toolCall: ToolCall) => toolCall.name !== "task"
                );
                if (visible.length === 0) return null;
                const done = visible.filter(
                  (t: ToolCall) => (t.status || "completed") === "completed"
                ).length;
                const names = Array.from(
                  new Set(visible.map((t: ToolCall) => t.name))
                ).slice(0, 3);
                return (
                  <>
                    <button
                      type="button"
                      onClick={() => setToolsOpen(!toolsOpen)}
                      className="flex w-full items-center gap-2 rounded-md border border-gray-100 bg-gray-50 px-2 py-1 text-left text-[0.6875rem] text-gray-500 transition-colors hover:bg-accent dark:border-gray-900 dark:bg-gray-900 dark:hover:bg-accent"
                    >
                      <span>{toolsOpen ? "▾" : "▸"}</span>
                      <span>
                        🔧 工人岗执行了 {visible.length} 个工具调用
                        {done === visible.length ? "（已完成）" : "（进行中）"}
                        {!toolsOpen && names.length > 0 && (
                          <span className="ml-1 opacity-70">
                            {names.join(" / ")}
                            {names.length >= 3 ? " …" : ""}
                          </span>
                        )}
                      </span>
                    </button>
                    {toolsOpen && (
                      <div className="flex w-full flex-col">
                        {toolCalls.map((toolCall: ToolCall) => {
                          if (toolCall.name === "task") return null;
                          const toolCallGenUiComponent = ui?.find(
                            (u) => u.metadata?.tool_call_id === toolCall.id
                          );
                          const actionRequest =
                            actionRequestsMap?.get(toolCall.name);
                          const reviewConfig =
                            reviewConfigsMap?.get(toolCall.name);
                          return (
                            <ToolCallBox
                              key={toolCall.id}
                              toolCall={toolCall}
                              uiComponent={toolCallGenUiComponent}
                              stream={stream}
                              graphId={graphId}
                              actionRequest={actionRequest}
                              reviewConfig={reviewConfig}
                              onResume={onResumeInterrupt}
                              isLoading={isLoading}
                            />
                          );
                        })}
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          )}
          {!isUser && subAgents.length > 0 && (
            <div className="flex w-fit max-w-full flex-col gap-4">
              {subAgents.map((subAgent) => (
                <div
                  key={subAgent.id}
                  className="flex w-full flex-col gap-2"
                >
                  <div className="flex items-end gap-2">
                    <div className="w-[calc(100%-100px)]">
                      <SubAgentIndicator
                        subAgent={subAgent}
                        onClick={() => toggleSubAgent(subAgent.id)}
                        isExpanded={isSubAgentExpanded(subAgent.id)}
                      />
                    </div>
                  </div>
                  {isSubAgentExpanded(subAgent.id) && (
                    <div className="w-full max-w-full">
                      <div className="bg-surface border-border-light rounded-md border p-4">
                        <h4 className="text-primary/70 mb-2 text-xs font-semibold uppercase tracking-wider">
                          Input
                        </h4>
                        <div className="mb-4">
                          <MarkdownContent
                            content={extractSubAgentContent(subAgent.input)}
                          />
                        </div>
                        {subAgent.output && (
                          <>
                            <h4 className="text-primary/70 mb-2 text-xs font-semibold uppercase tracking-wider">
                              Output
                            </h4>
                            <MarkdownContent
                              content={extractSubAgentContent(subAgent.output)}
                            />
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }
);

ChatMessage.displayName = "ChatMessage";
