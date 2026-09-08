"use client";

import React, { useState, useEffect, useCallback, Suspense } from "react";
import { useQueryState } from "nuqs";
import { getConfig, saveConfig, StandaloneConfig } from "@/lib/config";
import { ConfigDialog } from "@/app/components/ConfigDialog";
import { Button } from "@/components/ui/button";
import { Assistant } from "@langchain/langgraph-sdk";
import { ClientProvider, useClient } from "@/providers/ClientProvider";
import { Settings, MessagesSquare, SquarePen, Bot } from "lucide-react";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { ThreadList } from "@/app/components/ThreadList";
import { ChatProvider } from "@/providers/ChatProvider";
import { ChatInterface } from "@/app/components/ChatInterface";
import { getSettings, postSettings, tokenStatus } from "@/lib/providerApi";
import { SetupWizard, LoginGate } from "@/app/components/SetupWizard";

/** 顶栏快捷开关：确认分档 / 助手管工人岗 / 工具显隐——不进设置页直接切（2026-08-30 作者） */
function QuickToggles() {
  const [confirmLevel, setConfirmLevel] = useState<string>("…");
  const [miaManage, setMiaManage] = useState<boolean>(true);
  const [tools, setTools] = useState<boolean>(true);

  useEffect(() => {
    getSettings().then((s) => {
      setConfirmLevel(s?.general?.confirmLevel || "auto_edit");
      setMiaManage(s?.permissions?.miaManageAgents !== false);
    }).catch(() => {});
    setTools(localStorage.getItem("mia.showToolCalls") !== "false");
  }, []);

  const cycleConfirm = () => {
    // R47 四档（对齐 ZCode）：off 完全访问 → auto_edit 自动编辑 → strict 变更前确认 → plan 计划模式
    const order = ["off", "auto_edit", "strict", "plan"];
    const next = order[(order.indexOf(confirmLevel) + 1) % order.length];
    setConfirmLevel(next);
    postSettings("general", { confirmLevel: next });  // R66：分档挪家到 通用 节（旧默认值"standard"不是合法档，一并修正）
  };
  const toggleMia = () => {
    const next = !miaManage;
    setMiaManage(next);
    postSettings("permissions", { miaManageAgents: next });
  };
  const toggleTools = () => {
    const next = !tools;
    setTools(next);
    localStorage.setItem("mia.showToolCalls", String(next));
    window.dispatchEvent(new CustomEvent("mia-tool-visibility")); // R46 即时生效
  };
  const label =
    confirmLevel === "off" ? "🛡 完全访问" :
    confirmLevel === "strict" ? "🛡 变更前确认" :
    confirmLevel === "plan" ? "🛡 计划模式" : "🛡 自动编辑";
  return (
    <>
      <Button variant="outline" size="sm" onClick={cycleConfirm} title="确认分档（点击循环四档；改完即时生效，无需重启）">
        {label}
      </Button>
      <Button variant="outline" size="sm" onClick={toggleMia} title="允许助手管理工人岗（即时生效）">
        {miaManage ? "👑 助手有权" : "👑 助手无权"}
      </Button>
      <Button variant="outline" size="sm" onClick={toggleTools} title="对话里显示/隐藏工具调用卡片（刷新对话页生效）">
        {tools ? "🛠 工具:显" : "🛠 工具:隐"}
      </Button>
    </>
  );
}

interface HomePageInnerProps {
  config: StandaloneConfig;
  configDialogOpen: boolean;
  setConfigDialogOpen: (open: boolean) => void;
  handleSaveConfig: (config: StandaloneConfig) => void;
}
function HomePageInner({
  config,
  configDialogOpen,
  setConfigDialogOpen,
  handleSaveConfig,
}: HomePageInnerProps) {
  const client = useClient();
  const [threadId, setThreadId] = useQueryState("threadId");
  // 线程 404 兜底：URL 恢复出的 threadId 若已不存在（如对话被删），静默清除，不弹 404
  useEffect(() => {
    if (!threadId) return;
    let alive = true;
    client.threads.get(threadId).catch(() => {
      if (alive) void setThreadId(null);
    });
    return () => { alive = false; };
  }, [threadId, client, setThreadId]);
  const [sidebar, setSidebar] = useQueryState("sidebar");
  const [mutateThreads, setMutateThreads] = useState<(() => void) | null>(null);
  const [interruptCount, setInterruptCount] = useState(0);
  const [assistant, setAssistant] = useState<Assistant | null>(null);
  const fetchAssistant = useCallback(async () => {
    const isUUID =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        config.assistantId
      );
    if (isUUID) {
      // We should try to fetch the assistant directly with this UUID
      try {
        const data = await client.assistants.get(config.assistantId);
        setAssistant(data);
      } catch (error) {
        console.error("Failed to fetch assistant:", error);
        setAssistant({
          assistant_id: config.assistantId,
          graph_id: config.assistantId,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          config: {},
          metadata: {},
          version: 1,
          name: "Assistant",
          context: {},
        });
      }
    } else {
      try {
        // We should try to list out the assistants for this graph, and then use the default one.
        // TODO: Paginate this search, but 100 should be enough for graph name
        const assistants = await client.assistants.search({
          graphId: config.assistantId,
          limit: 100,
        });
        const defaultAssistant = assistants.find(
          (assistant) => assistant.metadata?.["created_by"] === "system"
        );
        if (defaultAssistant === undefined) {
          throw new Error("No default assistant found");
        }
        setAssistant(defaultAssistant);
      } catch (error) {
        console.error(
          "Failed to find default assistant from graph_id: try setting the assistant_id directly:",
          error
        );
        setAssistant({
          assistant_id: config.assistantId,
          graph_id: config.assistantId,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          config: {},
          metadata: {},
          version: 1,
          name: config.assistantId,
          context: {},
        });
      }
    }
  }, [client, config.assistantId]);
  useEffect(() => {
    fetchAssistant();
  }, [fetchAssistant]);
  return (
    <>
      <ConfigDialog
        open={configDialogOpen}
        onOpenChange={setConfigDialogOpen}
        onSave={handleSaveConfig}
        initialConfig={config}
      />
      <div className="flex h-screen flex-col">
        <header className="flex h-16 items-center justify-between border-b border-border px-6">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-semibold">Deep Agent UI</h1>
            {!sidebar && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSidebar("1")}
                className="rounded-md border border-border bg-card p-3 text-foreground hover:bg-accent"
              >
                <MessagesSquare className="mr-2 h-4 w-4" />
                Threads
                {interruptCount > 0 && (
                  <span className="ml-2 inline-flex min-h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] text-destructive-foreground">
                    {interruptCount}
                  </span>
                )}
              </Button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="text-sm text-muted-foreground">
              <span className="font-medium">Assistant:</span>{" "}
              助手
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => (window.location.href = "/settings")}
            >
              <Bot className="mr-2 h-4 w-4" />
              办公室设置
            </Button>
            <QuickToggles />
            <Button
              variant="outline"
              size="sm"
              onClick={() => setConfigDialogOpen(true)}
            >
              <Settings className="mr-2 h-4 w-4" />
              Settings
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setThreadId(null)}
              disabled={!threadId}
              className="border-[#2F6868] bg-[#2F6868] text-white hover:bg-[#2F6868]/80"
            >
              <SquarePen className="mr-2 h-4 w-4" />
              New Thread
            </Button>
          </div>
        </header>
        <div className="flex-1 overflow-hidden">
          <ResizablePanelGroup
            direction="horizontal"
            autoSaveId="standalone-chat"
          >
            {sidebar && (
              <>
                <ResizablePanel
                  id="thread-history"
                  order={1}
                  defaultSize={20}
                  minSize={12}
                  className="relative min-w-[260px]"
                >
                  <ThreadList
                    onThreadSelect={async (id) => {
                      try {
                        await client.threads.get(id);
                        await setThreadId(id);
                      } catch {
                        // 线程已被删除（404）：清掉引用回到新对话，不报错
                        await setThreadId(null);
                      }
                    }}
                    onMutateReady={(fn) => setMutateThreads(() => fn)}
                    onClose={() => setSidebar(null)}
                    onInterruptCountChange={setInterruptCount}
                  />
                </ResizablePanel>
                <ResizableHandle />
              </>
            )}
            <ResizablePanel
              id="chat"
              className="relative flex flex-col"
              order={2}
            >
              <ChatProvider
                activeAssistant={assistant}
                onHistoryRevalidate={() => mutateThreads?.()}
              >
                <ChatInterface assistant={assistant} />
              </ChatProvider>
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      </div>
    </>
  );
}
function HomePageContent() {
  const [config, setConfig] = useState<StandaloneConfig | null>(null);
  // R10.7（管理员："发布后要有管理员注册页面，这个一定要有"）：未配置密钥时全屏展示注册向导
  const [setupNeeded, setSetupNeeded] = useState<boolean | null>(null);
  // R10.8e（管理员："401 死锁，找回入口在进不去的设置页里"）：已配置但本浏览器无有效凭证 → 登录层
  // r24 lint 清账：AuthGate 全局闸门（layout 层）接管后，本地登录层只读不再置位——setter 是死变量
  const [loginNeeded] = useState(false);
  useEffect(() => {
    console.log("[gate] probe start");
    tokenStatus().then((s) => {
      console.log("[gate] tokenStatus:", JSON.stringify(s));
      // R10.8g（管理员登录后黑屏真凶）：configured=true 分支此前不落定 setupNeeded——
      // 它永远卡 null，被下方 `if (setupNeeded === null) return null` 永久挡住，登录成功也黑屏。
      if (s.configured) { setSetupNeeded(false); return; }
      setSetupNeeded(true);
    }).catch(() => setSetupNeeded(false));
  }, []);
  useEffect(() => {
    console.log("[gate] render state:", JSON.stringify({ setupNeeded, loginNeeded, hasConfig: !!config }));
  }, [setupNeeded, loginNeeded, config]);
  // 界面字号（管理员老花眼友好）：读 interface.uiZoom（百分比），应用到 body zoom
  useEffect(() => {
    // R10（评审E P1-1）：GET /settings 在 token 门内——裸 fetch 换统一封装 getSettings（自带 Bearer），
    // 全前端不再留第二把门把手
    getSettings().then((s: any) => {
      const z = Number(s?.interface?.uiZoom ?? 100);
      // 缩放加在 html 根元素：vh 视口单位随之补偿，h-screen 布局不会被撑出滚动条
      if (z && z !== 100) document.documentElement.style.zoom = String(z / 100);
    }).catch(() => {});
  }, []);
  const [configDialogOpen, setConfigDialogOpen] = useState(false);
  const [assistantId, setAssistantId] = useQueryState("assistantId");
  // On mount, check for saved config, otherwise show config dialog
  useEffect(() => {
    const savedConfig = getConfig();
    if (savedConfig) {
      setConfig(savedConfig);
      if (!assistantId) {
        setAssistantId(savedConfig.assistantId);
      }
    } else {
      setConfigDialogOpen(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // If config changes, update the assistantId
  useEffect(() => {
    if (config && !assistantId) {
      setAssistantId(config.assistantId);
    }
  }, [config, assistantId, setAssistantId]);
  const handleSaveConfig = useCallback((newConfig: StandaloneConfig) => {
    saveConfig(newConfig);
    setConfig(newConfig);
  }, []);
  const langsmithApiKey =
    config?.langsmithApiKey || process.env.NEXT_PUBLIC_LANGSMITH_API_KEY || "";
  // R10.7：管理员注册向导（未配置密钥=首部署 → 全屏引导；检测中短暂空白）
  // R10.8e（bug 修复）：loginNeeded=true 时 setupNeeded 仍是 null（configured=true 从不设置它）——
  // 空值检查必须放 loginNeeded 之后，否则登录层永远被 return null 挡住（管理员"页面看不到"真凶）。
  if (loginNeeded) return <LoginGate onDone={() => window.location.reload()} />;
  if (setupNeeded === null) return null;
  if (setupNeeded) return <SetupWizard onDone={() => window.location.reload()} />;
  if (!config) {
    return (
      <>
        <ConfigDialog
          open={configDialogOpen}
          onOpenChange={setConfigDialogOpen}
          onSave={handleSaveConfig}
        />
        <div className="flex h-screen items-center justify-center">
          <div className="text-center">
            <h1 className="text-2xl font-bold">Welcome to Standalone Chat</h1>
            <p className="mt-2 text-muted-foreground">
              Configure your deployment to get started
            </p>
            <Button
              onClick={() => setConfigDialogOpen(true)}
              className="mt-4"
            >
              Open Configuration
            </Button>
          </div>
        </div>
      </>
    );
  }
  return (
    <ClientProvider
      deploymentUrl={typeof window !== 'undefined' ? `${window.location.origin}/lg` : config.deploymentUrl}
      apiKey={langsmithApiKey}
    >
      <HomePageInner
        config={config}
        configDialogOpen={configDialogOpen}
        setConfigDialogOpen={setConfigDialogOpen}
        handleSaveConfig={handleSaveConfig}
      />
    </ClientProvider>
  );
}
export default function HomePage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center">
          <p className="text-muted-foreground">Loading...</p>
        </div>
      }
    >
      <HomePageContent />
    </Suspense>
  );
}
