"use client";

import React, { useState, useMemo, useCallback, useEffect } from "react";
import { useQueryState } from "nuqs";
import { API, apiFetch } from "@/lib/apiBase";
import { authHeaders } from "@/lib/providerApi";  // R10（评审E P1-1）：/approvals 在 token 门内，批准按钮必须带 Bearer
import {
  ChevronDown,
  ChevronUp,
  Terminal,
  AlertCircle,
  Loader2,
  CircleCheckBigIcon,
  StopCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ToolCall, ActionRequest, ReviewConfig } from "@/app/types/types";
import { cn } from "@/lib/utils";
import { LoadExternalComponent } from "@langchain/langgraph-sdk/react-ui";
import { ToolApprovalInterrupt } from "@/app/components/ToolApprovalInterrupt";

interface ToolCallBoxProps {
  toolCall: ToolCall;
  uiComponent?: any;
  stream?: any;
  graphId?: string;
  actionRequest?: ActionRequest;
  reviewConfig?: ReviewConfig;
  onResume?: (value: any) => void;
  isLoading?: boolean;
}

export const ToolCallBox = React.memo<ToolCallBoxProps>(
  ({
    toolCall,
    uiComponent,
    stream,
    graphId,
    actionRequest,
    reviewConfig,
    onResume,
    isLoading,
  }) => {
    const [isExpanded, setIsExpanded] = useState(
      // R10.8e（前端审查子代理）：含 ⛔ 拦截的工具默认展开——用户必须看到批准按钮，
      // 不应该藏在折叠层里点两次才找到。
      // R10.11（评审E P3-6 修正）：原写法在第 53 行解构 `result` 之前就引用它（TDZ 静默
      // 风险）——改从 props 的 toolCall.result 取，声明顺序无关、语义不变。
      () => !!uiComponent || !!actionRequest
        || (typeof toolCall?.result === "string" && toolCall.result.includes("⛔"))
    );
    const [expandedArgs, setExpandedArgs] = useState<Record<string, boolean>>(
      {}
    );

    const { name, args, result, status } = useMemo(() => {
      return {
        name: toolCall.name || "Unknown Tool",
        args: toolCall.args || {},
        result: toolCall.result,
        status: toolCall.status || "completed",
      };
    }, [toolCall]);

    // 确认门拦截卡自动展开修复：isExpanded 是挂载时初始值，历史线程加载时 result 尚未挂上、
    // 拦截内容到达后不会重算，批准按钮会藏在折叠层里。result 含 ⛔ 时补一次强制展开。
    const blocked = typeof result === "string" && result.includes("⛔");
    useEffect(() => {
      if (blocked) setIsExpanded(true);
    }, [blocked]);

    const statusIcon = useMemo(() => {
      if (blocked) {
        return (
          <StopCircle
            size={14}
            className="text-orange-500"
          />
        );
      }
      switch (status) {
        case "completed":
          return <CircleCheckBigIcon />;
        case "error":
          return (
            <AlertCircle
              size={14}
              className="text-destructive"
            />
          );
        case "pending":
          return (
            <Loader2
              size={14}
              className="animate-spin"
            />
          );
        case "interrupted":
          return (
            <StopCircle
              size={14}
              className="text-orange-500"
            />
          );
        default:
          return (
            <Terminal
              size={14}
              className="text-muted-foreground"
            />
          );
      }
    }, [status, blocked]);

    const toggleExpanded = useCallback(() => {
      setIsExpanded((prev) => !prev);
    }, []);

    const toggleArgExpanded = useCallback((argKey: string) => {
      setExpandedArgs((prev) => ({
        ...prev,
        [argKey]: !prev[argKey],
      }));
    }, []);

    const hasContent = result || Object.keys(args).length > 0;

    return (
      <div
        className={cn(
          "w-full overflow-hidden rounded-lg border-none shadow-none outline-none transition-colors duration-200 hover:bg-accent",
          isExpanded && hasContent && "bg-accent"
        )}
      >
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleExpanded}
          className={cn(
            "flex w-full items-center justify-between gap-2 border-none px-2 py-2 text-left shadow-none outline-none focus-visible:ring-0 focus-visible:ring-offset-0 disabled:cursor-default"
          )}
          disabled={!hasContent}
        >
          <div className="flex w-full items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {statusIcon}
              <span className="text-[15px] font-medium tracking-[-0.6px] text-foreground">
                {name}
                {blocked && (
                  <span className="ml-2 rounded bg-orange-500/15 px-1.5 py-0.5 text-[10px] font-medium text-orange-500">
                    ⛔ 待批准
                  </span>
                )}
              </span>
            </div>
            {hasContent &&
              (isExpanded ? (
                <ChevronUp
                  size={14}
                  className="shrink-0 text-muted-foreground"
                />
              ) : (
                <ChevronDown
                  size={14}
                  className="shrink-0 text-muted-foreground"
                />
              ))}
          </div>
        </Button>

        {isExpanded && hasContent && (
          <div className="px-4 pb-4">
            {uiComponent && stream && graphId ? (
              <div className="mt-4">
                <LoadExternalComponent
                  key={uiComponent.id}
                  stream={stream}
                  message={uiComponent}
                  namespace={graphId}
                  meta={{ status, args, result: result ?? "No Result Yet" }}
                />
              </div>
            ) : actionRequest && onResume ? (
              // Show tool approval UI when there's an action request but no GenUI
              <div className="mt-4">
                <ToolApprovalInterrupt
                  actionRequest={actionRequest}
                  reviewConfig={reviewConfig}
                  onResume={onResume}
                  isLoading={isLoading}
                />
              </div>
            ) : (
              <>
                {Object.keys(args).length > 0 && (
                  <div className="mt-4">
                    <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Arguments
                    </h4>
                    <div className="space-y-2">
                      {Object.entries(args).map(([key, value]) => (
                        <div
                          key={key}
                          className="rounded-sm border border-border"
                        >
                          <button
                            onClick={() => toggleArgExpanded(key)}
                            className="flex w-full items-center justify-between bg-muted/30 p-2 text-left text-xs font-medium transition-colors hover:bg-muted/50"
                          >
                            <span className="font-mono">{key}</span>
                            {expandedArgs[key] ? (
                              <ChevronUp
                                size={12}
                                className="text-muted-foreground"
                              />
                            ) : (
                              <ChevronDown
                                size={12}
                                className="text-muted-foreground"
                              />
                            )}
                          </button>
                          {expandedArgs[key] && (
                            <div className="border-t border-border bg-muted/20 p-2">
                              <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs leading-6 text-foreground">
                                {typeof value === "string"
                                  ? value
                                  : JSON.stringify(value, null, 2)}
                              </pre>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {result && (
                  <div className="mt-4">
                    <h4 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Result
                    </h4>
                    <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-all rounded-sm border border-border bg-muted/40 p-2 font-mono text-xs leading-7 text-foreground">
                      {typeof result === "string"
                        ? result
                        : JSON.stringify(result, null, 2)}
                    </pre>
                    {/* R69 确认门 v2：⛔ 拦截结果上挂「批准」按钮（管理员免敲 curl） */}
                    {typeof result === "string" && result.includes("⛔ 确认档") && (
                      <GateApproveButton
                        // R73（评审B🔴1 假通过修复）：工具名现用「」框住，取「」内内容；
                        // 旧 (\S+) 遇中文无空格会把整句吞进工具名→批准到错工具。
                        toolName={(result.match(/已拦截工具「([^」]+)」/) || [])[1] || ""}
                        // R10.3（评审B 🟡A 时窗调包）：把拦截消息里的参数指纹原样带回——
                        // 后端比对"管理员看到的那条"与"登记的那条"，不符=拒绝，不静默重绑。
                        fp={(result.match(/〔fp:([0-9a-f]+)〕/) || [])[1] || ""}
                      />
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    );
  }
);

ToolCallBox.displayName = "ToolCallBox";

/** R69 批准按钮：对 ⛔ 软门拦截调 POST /approvals——模型之外的一次性批准，
 *  点完让助手重试这一步即放行（office.api_approve / approvals.py 的正门 UI 化）。
 *  R10.5（评审B ⚪E 补 UI）：旁挂「撤销」——误点后悔药，DELETE /approvals 同 payload。
 *  r25（管理员裁决）：X-By 常数头作废，请求只带 Bearer/Cookie 真钥匙。 */
function GateApproveButton({ toolName, fp }: { toolName: string; fp?: string }) {
  const [threadId] = useQueryState("threadId");
  const [state, setState] = useState<"idle" | "sending" | "ok" | "fail">("idle");
  const [revoked, setRevoked] = useState<"idle" | "sending" | "ok" | "fail">("idle");
  if (!toolName || !threadId) return null;
  const revoke = async () => {
    setRevoked("sending");
    try {
      const r = await apiFetch(`${API}/approvals`, {
        method: "DELETE",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ thread_id: threadId, tool: toolName, fp: fp || "" }),
      });
      const j = await r.json();
      setRevoked(j?.ok ? "ok" : "fail");
      if (j?.ok) setState("idle");  // 撤销成功=批准收回，可重新批
    } catch {
      setRevoked("fail");
    }
  };
  return (
    <div className="mt-2 flex items-center gap-2">
      <Button
        size="sm"
        variant="outline"
        disabled={state !== "idle"}
        onClick={async () => {
          setState("sending");
          try {
            const r = await apiFetch(`${API}/approvals`, {
              method: "POST",
              headers: authHeaders({ "Content-Type": "application/json" }),
              // R10.3（评审B 🟡A）：fp 随批带上（时窗调包防）；缺 fp=后端直接拒并指路（fp 必填）
              body: JSON.stringify({ thread_id: threadId, tool: toolName, fp: fp || "" }),
            });
            const j = await r.json();
            setState(j?.ok ? "ok" : "fail");
          } catch {
            setState("fail");
          }
        }}
      >
        {state === "sending" ? "批准中…" : `✅ 批准 ${toolName}（一次性）`}
      </Button>
      <Button size="sm" variant="ghost" disabled={revoked !== "idle" || state === "sending"} onClick={revoke}>
        {revoked === "sending" ? "撤销中…" : "撤销"}
      </Button>
      {state === "ok" && (
        <span className="text-xs text-green-600 dark:text-green-400">
          已批准{revoked === "ok" ? "（已撤销，可重新批）" : "——让助手重试这一步即放行"}
        </span>
      )}
      {state === "fail" && <span className="text-xs text-red-500">批准失败（检查后端）</span>}
      {revoked === "fail" && <span className="text-xs text-red-500">撤销失败（可能已消费/无登记）</span>}
    </div>
  );
}
