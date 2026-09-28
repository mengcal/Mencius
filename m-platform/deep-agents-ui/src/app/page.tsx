"use client";

import React, { useState, useEffect, useCallback, Suspense } from "react";
import { useQueryState } from "nuqs";
import { getConfig, saveConfig, StandaloneConfig } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Assistant } from "@langchain/langgraph-sdk";
import { ClientProvider, useClient } from "@/providers/ClientProvider";
import { MessagesSquare, SquarePen, Bot } from "lucide-react";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { ThreadList } from "@/app/components/ThreadList";
import { ChatProvider } from "@/providers/ChatProvider";
import { ChatInterface } from "@/app/components/ChatInterface";
import { getSettings, postSettings, tokenStatus } from "@/lib/providerApi";
import { API, apiFetch } from "@/lib/apiBase";
import { authLogout } from "@/app/components/AuthPage";
import { CONFIRM_TIERS } from "@/lib/confirmTiers"; // r32 F18：四档单一真源（原本地 CONFIRM_LEVELS 与设置页各抄一份）

/** 顶栏快捷开关：确认分档 / 米娅管牛马 / 工具显隐——不进设置页直接切（2026-08-30 知夏）
 *  r35（爸爸点名"循环四档要点半天不科学"+逮到 off/full 枚举错位 bug）：
 *  循环按钮改下拉直选；档位值对齐后端合法四档 plan/strict/auto_edit/full
 *  （旧前端写 "off" 后端不认→fail-closed 回落 strict，按钮显示一直在撒谎）。
 *  r32（爸爸 09-26 裁决"个人平台管理员验证多此一举，等多用户版再考虑"）：
 *  顶栏四档自由切（原"放宽须到设置页验密、顶栏只收紧"限制整段撤除）。 */
// r36j（09-28）：对话区工作区徽章——爸要的"看得见自己在哪个区干活"。
// 数据源=后端 _runtime.workspace（settings.workspace.containerRoot 单源）。
// 宿主工作区（完全访问档的电脑本体）等爸定夺一等公民化后再进选项列表。
function WorkspaceBadge() {
  // r36q（若若 P1-a/b + Eve/Veda/Cora 竣工票）：徽章跟**当前对话的工作区**走——
  // 读 localStorage 初值 + 监听选择器派发的 mia-workspace 事件；宿主机=橙色警示。
  // 文案矛盾消除：旧版徽章写"尚未开通"而选择器已开放=两套话，现统一为已开通实况（两轴正交）。
  const [ws, setWs] = useState<{ root: string; mode: string } | null>(null);
  useEffect(() => {
    import("@/lib/providerApi").then(({ getSettings }) => {
      getSettings().then((s: any) => {
        const w = s?._runtime?.workspace;
        if (w?.containerRoot) {
          let cur = "container";
          try { cur = localStorage.getItem("mia.workspace") || "container"; } catch {}
          setWs({ root: String(w.containerRoot), mode: cur });
        }
      }).catch(() => {});
    });
    const onWs = (ev: Event) => {
      const d = (ev as CustomEvent).detail as string;
      setWs((prev) => (prev ? { ...prev, mode: d } : prev));
    };
    window.addEventListener("mia-workspace", onWs);
    return () => window.removeEventListener("mia-workspace", onWs);
  }, []);
  if (!ws) return null;
  const host = ws.mode === "host";
  return (
    <span
      title={host
        ? "当前对话工作区=宿主机（您的电脑，经宿主执行器）。高危操作仍按当前档位请示；档位管问不问，这里管在哪干。"
        : "当前对话工作区=容器（数据目录 / " + ws.root + "）。换工作区用输入框右侧下拉；两轴正交。"}
      className={"rounded-md border px-2 py-1 text-xs " + (host ? "border-orange-500/60 text-orange-600 dark:text-orange-400" : "border-border text-muted-foreground")}
    >
      工作区：{host ? "宿主机" : "容器 · " + ws.root}
    </span>
  );
}
function QuickToggles() {
  const [confirmLevel, setConfirmLevel] = useState<string>("strict");
  const [miaManage, setMiaManage] = useState<boolean>(true);
  const [tools, setTools] = useState<boolean>(true);
  const [rev, setRev] = useState<number>(0); // _rev：GET /settings 回传的版本号，保存时回传（r32 F1 顶栏补带）

  const refreshRev = () => {
    getSettings().then((s: any) => {
      setConfirmLevel(s?.general?.confirmLevel || "strict");
      setRev(Number(s?._rev || 0));
    }).catch(() => {});
  };

  useEffect(() => {
    getSettings().then((s: any) => {
      // 后端 _level() 对未配置/非法值 fail-closed 回落 strict——前端默认同步，不再谎报 auto_edit
      setConfirmLevel(s?.general?.confirmLevel || "strict");
      setMiaManage(s?.permissions?.miaManageAgents !== false);
      setRev(Number(s?._rev || 0));
    }).catch(() => {});
    setTools(localStorage.getItem("mia.showToolCalls") !== "false");
  }, []);

  const pickConfirm = async (v: string) => {
    // r32：四档直选无方向限制（爸爸裁决撤密码门）；_rev 防撞车；成功后刷新 rev
    // 防"保存后 mtime 已变、下次保存必 409"的陈旧版本死循环（Qoder P3#20）。
    const prev = confirmLevel;
    setConfirmLevel(v);
    try {
      const r = await apiFetch(`${API}/settings/confirm-level`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level: v, _rev: rev }),
      });
      const j = await r.json().catch(() => ({}));
      if (j?.ok) { refreshRev(); }
      else {
        setConfirmLevel(j?.previous || prev);
        window.alert(j?.error || "档位切换失败");
        if (j?.conflict) refreshRev(); // 409：拿到最新版本号，改完即可再存
      }
    } catch { setConfirmLevel(prev); window.alert("无法连接后端"); }
  };
  const toggleMia = () => {
    const next = !miaManage;
    setMiaManage(next);
    // r32 F1：顶栏保存补 _rev（此前唯一裸奔的 permissions 写面）
    postSettings("permissions", { miaManageAgents: next, _rev: rev }).then((j: any) => {
      if (j?.ok) refreshRev();
      else if (j?.conflict) { window.alert(j?.error || "设置已被后台修改，请刷新页面后重试"); refreshRev(); }
      else if (j?.error) window.alert(j.error);
    });
  };
  const toggleTools = () => {
    const next = !tools;
    setTools(next);
    localStorage.setItem("mia.showToolCalls", String(next));
    window.dispatchEvent(new CustomEvent("mia-tool-visibility")); // R46 即时生效
  };
  return (
    <>
      <Select value={confirmLevel} onValueChange={pickConfirm}>
        <SelectTrigger className="h-8 w-52 gap-1 border-gray-200 bg-white text-xs dark:border-gray-700 dark:bg-gray-900" title="确认分档（四档直选；改完即时生效，无需重启）">
          <SelectValue placeholder="🛡 确认分档" />
        </SelectTrigger>
        <SelectContent>
          {CONFIRM_TIERS.map((l) => (
            <SelectItem key={l.v} value={l.v} className="text-xs">{l.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button variant="outline" size="sm" onClick={toggleMia} title="允许米娅管理牛马（即时生效）">
        {miaManage ? "👑 米娅有权" : "👑 米娅无权"}
      </Button>
      <Button variant="outline" size="sm" onClick={toggleTools} title="对话里显示/隐藏工具调用卡片（刷新对话页生效）">
        {tools ? "🛠 工具:显" : "🛠 工具:隐"}
      </Button>
    </>
  );
}

interface HomePageInnerProps {
  config: StandaloneConfig;
  // r39（NOVA R37-P0 统一修法）：URL 助手 id 独立传递，不回灌 config 本体——
  // config 永远保持 localStorage 态，围炉/圆桌链接永不进保存链/回写链。
  urlAssistantId?: string | null;
}
function HomePageInner({
  config,
  urlAssistantId,
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
  // r39（NOVA 统一修法）：有效助手=URL 值优先，否则 localStorage 配置值；config 本体不再被回灌
  const effAssistantId = urlAssistantId || config.assistantId;
  const fetchAssistant = useCallback(async () => {
    const isUUID =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        effAssistantId
      );
    if (isUUID) {
      // We should try to fetch the assistant directly with this UUID
      try {
        const data = await client.assistants.get(effAssistantId);
        setAssistant(data);
      } catch (error) {
        console.error("Failed to fetch assistant:", error);
        setAssistant({
          assistant_id: effAssistantId,
          graph_id: effAssistantId,
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
          graphId: effAssistantId,
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
          assistant_id: effAssistantId,
          graph_id: effAssistantId,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          config: {},
          metadata: {},
          version: 1,
          name: effAssistantId,
          context: {},
        });
      }
    }
  }, [client, effAssistantId]);
  useEffect(() => {
    fetchAssistant();
  }, [fetchAssistant]);
  return (
    <>
      <div className="flex h-screen flex-col">
        <header className="flex h-16 items-center justify-between border-b border-border px-6">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-semibold">米娅的办公室</h1>
            {!sidebar && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSidebar("1")}
                className="rounded-md border border-border bg-card p-3 text-foreground hover:bg-accent"
              >
                <MessagesSquare className="mr-2 h-4 w-4" />
                对话
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
              <span className="font-medium">当前助手:</span>{" "}
              {/* 页头随图显示（r38 小瑕；r39 换 effAssistantId 与入口同一供体） */}
              {effAssistantId === "hearth"
                ? "围炉夜话"
                : effAssistantId === "roundtable"
                  ? "圆桌"
                  : "米娅"}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => (window.location.href = "/settings")}
            >
              <Bot className="mr-2 h-4 w-4" />
              办公室设置
            </Button>
            <WorkspaceBadge />
            <QuickToggles />
            <Button
              variant="outline"
              size="sm"
              onClick={() => setThreadId(null)}
              disabled={!threadId}
              className="border-[#2F6868] bg-[#2F6868] text-white hover:bg-[#2F6868]/80"
            >
              <SquarePen className="mr-2 h-4 w-4" />
              新对话
            </Button>
            {/* r31：退出登录（爸爸令"看看 OWUI"）——顶栏右侧，点了清 cookie 回登录页。
                r32 F5/F7（CB/Qoder）：本地裸跑模式（无守卫）登录通道不存在=登出即自锁，
                故 !guard 时整个按钮不渲染；authLogout 读响应，失败出声不再谎报登出。 */}
            <LogoutButton />
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
/** r32 F5/F7：退出按钮自持组件——查 /settings/token/status 的 guard 标志，
 * 本地裸跑模式（guard:false）不渲染（登录通道不存在，登出=自锁死路）；
 * 登出动作统一走 AuthPage 的 authLogout()（读响应、失败出声），消灭第二份内联实现。 */
function LogoutButton() {
  const [guard, setGuard] = useState<boolean | null>(null);
  useEffect(() => {
    tokenStatus().then((s: any) => setGuard(s?.guard !== false)).catch(() => setGuard(null));
  }, []);
  if (guard === false) return null;
  return (
    <Button variant="outline" size="sm" onClick={() => void authLogout()}
      className="text-muted-foreground hover:text-foreground">
      退出登录
    </Button>
  );
}

function HomePageContent() {
  const [config, setConfig] = useState<StandaloneConfig | null>(null);
  // r32 F11（CB/Qoder/Veda 三路同锤）：本地闸门整套拆除——layout 层 AuthGate 已全局接管
  // （未配置→注册页、无凭证→登录页、已配置→放行），本组件挂载时必已过闸；
  // 此前的 setupNeeded 探针 / loginNeeded 死变量 / 两处 AuthPage 分支 = 与全局闸门
  // 职责重复的死代码（console.log 调试残留一并清，Cora P4-1）。
  // fail-open 语义注记（NOVA/Cora 观察项）：AuthGate 对非 401 错误放行渲染是"后端挂
  // 优先出界面"的取舍，数据请求会失败但页面不锁死——有意为之，勿改回 fail-closed 黑屏。
  // 界面字号（爸爸老花眼友好）：读 interface.uiZoom（百分比），应用到 body zoom
  useEffect(() => {
    // R10（千问 P1-1）：GET /settings 在 token 门内——裸 fetch 换统一封装 getSettings（自带 Bearer），
    // 全前端不再留第二把门把手
    getSettings().then(async (s: any) => {
      // r35（Qoder P1-10）：删 `?? 100` 字面量第三老家——settings 无此值时现读
      // /settings/schema 的登记默认（单一真源）；schema 也拿不到才按浏览器原样不缩放
      let z0 = s?.interface?.uiZoom;
      if (z0 == null) {
        try {
          const sc = await fetch(`${window.location.origin}/lg/settings/schema`).then((r) => r.json());
          z0 = sc?.["interface.uiZoom"]?.default;
        } catch { /* 拿不到=不缩放（与 100% 等效），不再自造第二份默认 */ }
      }
      const z = Number(z0);
      // 缩放加在 html 根元素：vh 视口单位随之补偿，h-screen 布局不会被撑出滚动条
      if (z && z !== 100) document.documentElement.style.zoom = String(z / 100);
    }).catch(() => {});
  }, []);
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
      // r34（CB 7.1 P1）：首用/换浏览器/无痕不再弹全英文 LangGraph Cloud 配置框——
      // 自建同源场景这框是误导（填的 Deployment URL 根本不被使用，下方已自动 origin/lg）。
      // 自动写入默认配置直达主界面；围炉/圆桌链接仍走 URL assistantId 参数不受影响。
      const def: StandaloneConfig = {
        deploymentUrl: `${window.location.origin}/lg`,
        assistantId: "agent",
        langsmithApiKey: "",
      };
      saveConfig(def);
      setConfig(def);
      if (!assistantId) setAssistantId("agent");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // If config changes, update the assistantId
  useEffect(() => {
    if (config && !assistantId) {
      setAssistantId(config.assistantId);
    }
  }, [config, assistantId, setAssistantId]);
  // r36→r39：URL 权威入口改由 urlAssistantId prop 直供 HomePageInner（NOVA P0-1/P0-2 根治），
  // 不再 setConfig 回灌——旧回灌与上方回写 effect 相咬（删 URL 逃不出围炉）、
  // （r35：ConfigDialog.tsx 死文件已物理删除；此段保留的是 localStorage 保存链的隔离规矩本身。）
  const langsmithApiKey =
    config?.langsmithApiKey || process.env.NEXT_PUBLIC_LANGSMITH_API_KEY || "";
  // r32 F11：原 setupNeeded/loginNeeded 三行闸门分支整段删除（见 HomePageContent 头注释）
  if (!config) {
    // r35（Qoder P2-35/P3-18）：全英文"Welcome to Standalone Chat"+手填 Deployment URL 的
    // 兜底页连根拔——r34 自动 provision 后 config 挂载即就绪，这个窗口只闪一瞬；
    // 保留手填入口反而能填一个不被使用的地址并污染 localStorage（见 :394 注释的围炉劫持史）。
    return <div className="flex h-screen items-center justify-center"><p className="text-muted-foreground">正在连上平台…</p></div>;
  }
  return (
    <ClientProvider
      deploymentUrl={typeof window !== 'undefined' ? `${window.location.origin}/lg` : config.deploymentUrl}
      apiKey={langsmithApiKey}
    >
      <HomePageInner
        config={config}
        urlAssistantId={assistantId}
      />
    </ClientProvider>
  );
}
export default function HomePage() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen items-center justify-center">
          <p className="text-muted-foreground">正在加载…</p>
        </div>
      }
    >
      <HomePageContent />
    </Suspense>
  );
}
