"use client";
/**
 * 米娅办公室 · 对话界面（骨架，原 891 行 → 壳 + chat/ 模块）
 * ------------------------------------------------------------------
 * 本文件保留：消息列表渲染 + 输入 form 骨架 + 上传/发送逻辑。
 * 拆分模块（见 chat/ 目录）：
 *   chatUtils.tsx        getStatusIcon + processMessages + buildAutoReportGroups 纯函数
 *   useModelSelection.ts 模型/思维档/联网开关 hook（localStorage 键名原样保留）
 *   useTaskAnnouncer.ts  R3/R64 后台任务轮询 + announced 持久化播报
 *   TasksFilesPanel.tsx  任务/文件侧板
 *   ModelPicker.tsx      模型选择弹窗
 *   ContextMeter.tsx     R53 上下文容量弹窗
 */
import React, {
  useState,
  useMemo,
  useRef,
  useCallback,
  FormEvent,
} from "react";
import { Button } from "@/components/ui/button";
import {
  Square,
  ArrowUp,
  Paperclip,
} from "lucide-react";
import { saveFile } from "@/lib/providerApi";
import { authHeaders } from "@/lib/providerApi";
import { API, apiFetch } from "@/lib/apiBase";

// r35（Qoder P2-30）：visionEndpoint() 连根拔——注入消息洗净后 ep 值已零消费者，
// 留着的正是"注释声称不写死、下一行写死 host.docker.internal"的双源本身；
// 识图端点真源=后端 /settings._runtime（env 单源），浏览器不需要知道它。
import { ChatMessage } from "@/app/components/ChatMessage";
import type {
  ActionRequest,
  ReviewConfig,
} from "@/app/types/types";
import type { Assistant } from "@langchain/langgraph-sdk";
import { useChatContext } from "@/providers/ChatProvider";
import { cn } from "@/lib/utils";
import { useStickToBottom } from "use-stick-to-bottom";
import { processMessages, buildAutoReportGroups } from "./chat/chatUtils";
import { useModelSelection } from "./chat/useModelSelection";
import { useTaskAnnouncer } from "./chat/useTaskAnnouncer";
import { TasksFilesPanel } from "./chat/TasksFilesPanel";
import { ModelPicker } from "./chat/ModelPicker";
import { ContextMeter } from "./chat/ContextMeter";

interface ChatInterfaceProps {
  assistant: Assistant | null;
}
export const ChatInterface = React.memo<ChatInterfaceProps>(({ assistant }) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [input, setInput] = useState("");
  // r36k（爸令完整分区）：工作区=对话级"在哪干"（container 沙箱域 / host 宿主执行器域），
  // 与档位"问不问"正交；持久化到 localStorage，开聊即见（对话头部下拉）。
  const [workspace, setWorkspace] = useState<string>(() => {
    try { return localStorage.getItem("mia.workspace") || "container"; } catch { return "container"; }
  });
  // ── OWUI 式输入框：左下角联网开关+思维档位，右下角模型选择（2026-08-29 知夏；r25 空壳🔧按钮已随爸爸令拔除）──
  const {
    // r32b：webSearchOn/setWebSearchOn 随联网按钮退役（恒传 true，见 handleSubmit）
    thinking,
    setThinking,
    models,
    selectedModel,
    selectedProvider,
    pickModel,
    tidNow,
  } = useModelSelection();
  const { scrollRef, contentRef } = useStickToBottom();
  const {
    stream,
    messages,
    todos,
    files,
    ui,
    setFiles,
    isLoading,
    isThreadLoading,
    interrupt,
    sendMessage,
    stopStream,
    resumeInterrupt,
    getMessagesMetadata,
  } = useChatContext();
  const submitDisabled = isLoading || !assistant;
  // R3 闭环：轮询后台任务，完成且未播报的 → 自动让米娅读结果汇报给爸爸（R64 持久化见 useTaskAnnouncer）
  useTaskAnnouncer(isLoading, sendMessage);
  // 上传：文本进 files 通道；图片存 base64 并自动请米娅派 visual 识图（R3）
  // r36x（爸 19:0x 令）：粘贴图片与文件选择共用同一条上传链——
  // 此前只有文件选择按钮，Ctrl+V 粘贴截图静默无效（米娅平台一直没有这个功能，不是坏了）。
  const processFiles = useCallback(
    async (list: FileList | File[] | null) => {
      if (!list?.length) return;
      const next: Record<string, string> = { ...files };
      const images: string[] = [];
      const texts: string[] = [];
      for (const f of Array.from(list)) {
        if (f.type.startsWith("image/")) {
          // 图片：落盘到平台（/files/save），visual 用路径调 /vision——绕开沙箱文件隔离
          const b64 = await new Promise<string>((res) => {
            const r = new FileReader();
            r.onload = () => res(String(r.result).split(",")[1] || "");
            r.readAsDataURL(f);
          });
          const saved = await saveFile(f.name, b64);
          next[f.name] = saved.path
            ? `已落盘：${saved.path}（识图请用 image_path 调 /vision）`
            : `data:${f.type};base64,${b64}`;
          images.push(saved.path ? saved.path : f.name);
        } else {
          try {
            next[f.name] = await f.text();
            texts.push(f.name);
          } catch {
            next[f.name] = "（二进制文件，内容未读取）";
          }
        }
      }
      await setFiles(next);
      // 自动派活提示（走 enqueue 队列，不卡聊天）
      if (images.length) {
        sendMessage(
          `爸爸上传了图片：${images.join("、")}。图片已落盘（files 里有确切路径），请按流程派 visual 牛马识图，把结果汇总告诉爸爸。`,
          { webSearch: undefined }
        );
      } else if (texts.length) {
        sendMessage(`爸爸上传了文件：${texts.join("、")}（在对话文件 files 里），请查收并告诉我你看到了什么。`);
      }
      setInput("");
    },
    [files, setFiles, sendMessage, setInput]
  );

  const handleFileUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      await processFiles(e.target.files);
      e.target.value = "";
    },
    [processFiles]
  );

  // 粘贴：截图（clipboardData.items 的 image）与复制的文件都进同一条链
  const handlePaste = useCallback(
    async (e: React.ClipboardEvent) => {
      const dt = e.clipboardData;
      if (!dt) return;
      const picked: File[] = [];
      for (const it of Array.from(dt.items)) {
        if (it.kind === "file") {
          const f = it.getAsFile();
          if (f) picked.push(f);
        }
      }
      if (picked.length) {
        e.preventDefault();
        await processFiles(picked);
      }
    },
    [processFiles]
  );
  const handleSubmit = useCallback(
    (e?: FormEvent) => {
      if (e) {
        e.preventDefault();
      }
      const messageText = input.trim();
      if (!messageText || isLoading || submitDisabled) return;
      sendMessage(messageText, {
        model: selectedModel || undefined,
        provider: selectedProvider || undefined,
        workspace: workspace || "container",
        // r32b（爸爸裁决"默认米娅可以联网搜索"）：恒传 true——按钮已退役，
        // 老的 localStorage 关闭态（webSearchOn=false）不再生效；后端缺省本就 True
        webSearch: true,
        thinking: thinking || undefined,
      });
      setInput("");
    },
    [input, isLoading, sendMessage, setInput, submitDisabled, selectedModel, selectedProvider, thinking, workspace]
  );
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (submitDisabled) return;
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit, submitDisabled]
  );
  // 消息流处理（纯函数见 chat/chatUtils.tsx）
  const processedMessages = useMemo(
    () => processMessages(messages, interrupt),
    [messages, interrupt]
  );
  // R59 自动汇报折叠：指令 + 米娅回复合并成一组（点开才展开）
  const autoReportGroup = useMemo(
    () => buildAutoReportGroups(processedMessages),
    [processedMessages]
  );
  const [autoReportOpen, setAutoReportOpen] = useState<
    Record<string, boolean>
  >({});
  // Parse out any action requests or review configs from the interrupt
  const actionRequestsMap: Map<string, ActionRequest> | null = useMemo(() => {
    const actionRequests =
      interrupt?.value && (interrupt.value as any)["action_requests"];
    if (!actionRequests) return new Map<string, ActionRequest>();
    return new Map(actionRequests.map((ar: ActionRequest) => [ar.name, ar]));
  }, [interrupt]);
  const reviewConfigsMap: Map<string, ReviewConfig> | null = useMemo(() => {
    const reviewConfigs =
      interrupt?.value && (interrupt.value as any)["review_configs"];
    if (!reviewConfigs) return new Map<string, ReviewConfig>();
    return new Map(
      reviewConfigs.map((rc: ReviewConfig) => [rc.actionName, rc])
    );
  }, [interrupt]);
  // r41（C1）：批量批准——官方 HITLRequest 的 action_requests 列表原样下传
  const actionRequestsList: ActionRequest[] = useMemo(() => {
    const arr = interrupt?.value && (interrupt.value as any)["action_requests"];
    return Array.isArray(arr) ? arr : [];
  }, [interrupt]);
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div
        className="flex-1 overflow-y-auto overflow-x-hidden overscroll-contain"
        ref={scrollRef}
      >
        <div
          className="mx-auto w-full max-w-[1024px] px-6 pb-6 pt-4"
          ref={contentRef}
        >
          {isThreadLoading ? (
            <div className="flex items-center justify-center p-8">
              <p className="text-muted-foreground">加载中…</p>
            </div>
          ) : (
            <>
              {processedMessages.map((data, index) => {
                // R59：米娅的回复并入自动汇报折叠行，不再单条显示
                if (autoReportGroup.bodyToHead.has(data.message.id!)) {
                  return null;
                }
                const autoReport = autoReportGroup.groups.get(
                  data.message.id!
                );
                const messageUi = ui?.filter(
                  (u: any) => u.metadata?.message_id === data.message.id
                );
                // R64 消息时间戳：官方 getMessagesMetadata → firstSeenState.created_at
                //（checkpoint 时间，零令牌——时间戳是前端渲染的活，不该让米娅烧钱写）
                const createdAt: string | undefined =
                  (getMessagesMetadata?.(data.message, index)?.firstSeenState
                    ?.created_at as string | undefined) ?? undefined;
                const isLastMessage = index === processedMessages.length - 1;
                return (
                  <ChatMessage
                    key={data.message.id}
                    message={data.message}
                    toolCalls={data.toolCalls}
                    isLoading={isLoading}
                    createdAt={createdAt}
                    actionRequestsMap={
                      isLastMessage ? actionRequestsMap : undefined
                    }
                    reviewConfigsMap={
                      isLastMessage ? reviewConfigsMap : undefined
                    }
                    actionRequestsList={
                      isLastMessage ? actionRequestsList : undefined
                    }
                    ui={messageUi}
                    stream={stream}
                    onResumeInterrupt={resumeInterrupt}
                    graphId={assistant?.graph_id}
                    autoReport={
                      autoReport
                        ? {
                            ...autoReport,
                            open: !!autoReportOpen[data.message.id!],
                            onToggle: () =>
                              setAutoReportOpen((prev) => ({
                                ...prev,
                                [data.message.id!]: !prev[data.message.id!],
                              })),
                          }
                        : undefined
                    }
                  />
                );
              })}
            </>
          )}
        </div>
      </div>
      <div className="flex-shrink-0 bg-background">
        <div
          className={cn(
            "mx-4 mb-6 flex flex-shrink-0 flex-col overflow-hidden rounded-xl border border-border bg-background",
            "mx-auto w-[calc(100%-32px)] max-w-[1024px] transition-colors duration-200 ease-in-out"
          )}
        >
          <TasksFilesPanel
            todos={todos}
            files={files}
            setFiles={setFiles}
            isLoading={isLoading}
            interrupt={interrupt}
          />
          <form
            onSubmit={handleSubmit}
            className="flex flex-col"
          >
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              onPaste={(e) => void handlePaste(e)}
              placeholder={isLoading ? "米娅正在干活…（点右侧停止可打断）" : "跟米娅说什么…（可直接 Ctrl+V 粘贴截图）"}
              className="font-inherit field-sizing-content min-h-[64px] flex-1 resize-none border-0 bg-transparent px-[18px] pb-[13px] pt-[14px] text-sm leading-7 text-primary outline-none placeholder:text-tertiary"
              rows={2}
            />
            <div className="flex items-center justify-between gap-2 p-3">
              <div className="flex items-center gap-1">
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="hidden"
                  onChange={(e) => void handleFileUpload(e)}
                />
                <button
                  type="button"
                  title="上传文件（文本类直接可读，米娅收到后可用 execute 处理）"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isLoading}
                  className="rounded-lg p-2 text-tertiary transition-colors hover:bg-accent hover:text-primary disabled:opacity-50"
                >
                  <Paperclip size={16} />
                </button>
                {/* r32b（爸爸 09-26 裁决）：联网搜索按钮退役——对齐主流（豆包/清言/ZCode 无此按钮=默认能联网）。
                    后端 web_search 本就缺省 True（run_config.py），模型内置搜索（qwen3.8-flash 系）
                    或搜索工具（tavily/秘塔/博查/searxng）都默认可用，无需爸爸选。 */}
                <select
                  title="思维档位（随消息生效）"
                  value={thinking}
                  onChange={(e) => setThinking(e.target.value)}
                  className="rounded-lg bg-gray-900 text-gray-300 px-1 py-1 text-xs outline-none transition-colors hover:bg-gray-800 border border-gray-800"
                  style={{ colorScheme: 'dark' }}
                >
                  <option value="">🧠 默认</option>
                  <option value="off">🧠 关闭</option>
                  <option value="low">🧠 低</option>
                  <option value="medium">🧠 中</option>
                  <option value="high">🧠 高</option>
                </select>
              </div>
              <div className="flex items-center gap-2">
                {/* 模型选择（OWUI 同款：输入框右下角） */}
                {/* r36k 工作区选择器（对话头部，开聊即选——爸定标准：不在设置页） */}
                <select
                  className="h-8 rounded-md border border-border bg-background px-1.5 text-xs text-foreground"
  style={{ colorScheme: "dark" }}
                  value={workspace}
                  onChange={(e) => { setWorkspace(e.target.value); try { localStorage.setItem('mia.workspace', e.target.value); } catch {}
    try { window.dispatchEvent(new CustomEvent('mia-workspace', { detail: e.target.value })); } catch {} }}
                  title="工作区=米娅在哪台机器上干活。容器=隔离沙箱（默认）；宿主机=您的电脑本体（经宿主执行器，高危操作仍按当前档位请示）。"
                >
                  <option value="container">工作区：容器</option>
                  <option value="host">工作区：宿主机</option>
                </select>
                <ModelPicker
                  models={models}
                  selectedModel={selectedModel}
                  selectedProvider={selectedProvider}
                  onPick={pickModel}
                />
                {/* R53 上下文容量（ZCode 同款）：点击弹出当前对话的容量条与构成 */}
                <ContextMeter tidNow={tidNow} />
                <Button
                  type={isLoading ? "button" : "submit"}
                  variant={isLoading ? "destructive" : "default"}
                  onClick={isLoading ? stopStream : handleSubmit}
                  disabled={!isLoading && (submitDisabled || !input.trim())}
                >
                  {isLoading ? (
                    <>
                      <Square size={14} />
                      <span>停止</span>
                    </>
                  ) : (
                    <>
                      <ArrowUp size={18} />
                      <span>发送</span>
                    </>
                  )}
                </Button>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
});
ChatInterface.displayName = "ChatInterface";
