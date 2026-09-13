"use client";

/**
 * r41（C1）批量批准卡：官方 HITLRequest（action_requests 列表）一卡 N 行一次 resume。
 * 四家合订 UX：
 * - NOVA：数量预校验（decisions 必须=N，别让官方 ValueError 炸到爸爸脸上）；
 *   reject 默认不带 message（官方带 reason 分支无"勿重试"文案——NOVA P0-1）。
 * - Cora：**高危行不进一键全批**（疲劳 20%→40% 的反面解药：给快但不给无差别快）。
 * - Eve：同工具多行时参数差异字段高亮（N 行长得一样=扫一眼党催化剂）。
 * - Lyra：每行独立三钮（approve/edit/reject）+ edit 展开参数编辑。
 * 决策state 按行索引；提交时按行序组装 decisions 数组。
 */

import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { AlertCircle, Check, X, Pencil, ShieldAlert, BookmarkPlus } from "lucide-react";
import { cn } from "@/lib/utils";
import { API, apiFetch } from "@/lib/apiBase";

type Decision =
  | { type: "approve" }
  | { type: "reject" }
  | { type: "edit"; edited_action: { name: string; args: Record<string, unknown> } };

interface HitlRow {
  name: string;
  args: Record<string, unknown>;
  description?: string;
}

interface BatchApprovalInterruptProps {
  actionRequests: HitlRow[];
  onResume: (value: any) => void;
  isLoading?: boolean;
}

// 高危工具名单（与后端 _NEEDS_EXTERNAL 同源语义；MCP 工具前缀一律算高危）
const HIGH_RISK = new Set([
  "execute", "delete", "email", "manage_departments", "start_async_task",
  "dispatch_to_xiaoquan", "task", "update_async_task", "cancel_async_task",
  "write_file", "edit_file", "edit_memory",
]);
const isHighRisk = (name: string) =>
  HIGH_RISK.has(name) || name.toLowerCase().startsWith("mcp__");

export function BatchApprovalInterrupt({
  actionRequests,
  onResume,
  isLoading,
}: BatchApprovalInterruptProps) {
  const [decisions, setDecisions] = useState<Record<number, Decision>>({});
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editedArgs, setEditedArgs] = useState<Record<string, unknown>>({});

  const n = actionRequests.length;
  const decided = Object.keys(decisions).length;
  const complete = decided === n;

  // Eve：同工具多行时，找出与首行参数不同的字段 key（轻量 diff）
  const diffKeysByRow = useMemo(() => {
    const firstByKey: Record<string, Record<string, unknown>> = {};
    const out: Record<number, Set<string>> = {};
    actionRequests.forEach((r, i) => {
      if (firstByKey[r.name] === undefined) {
        firstByKey[r.name] = r.args;
        out[i] = new Set();
        return;
      }
      const base = firstByKey[r.name];
      const keys = new Set<string>();
      const all = new Set([...Object.keys(base ?? {}), ...Object.keys(r.args ?? {})]);
      all.forEach((k) => {
        if (JSON.stringify((base ?? {})[k]) !== JSON.stringify((r.args ?? {})[k])) keys.add(k);
      });
      out[i] = keys;
    });
    return out;
  }, [actionRequests]);

  const safeCount = actionRequests.filter((r) => !isHighRisk(r.name)).length;
  const highCount = n - safeCount;

  const setDecision = (i: number, d: Decision) =>
    setDecisions((prev) => ({ ...prev, [i]: d }));

  const approveAllSafe = () => {
    const next: Record<number, Decision> = { ...decisions };
    actionRequests.forEach((r, i) => {
      if (!isHighRisk(r.name)) next[i] = { type: "approve" };
    });
    setDecisions(next);
  };

  const startEditing = (i: number) => {
    setEditingIdx(i);
    setEditedArgs(JSON.parse(JSON.stringify(actionRequests[i].args)));
  };

  const updateEditedArg = (key: string, value: string) => {
    try {
      const parsed =
        value.trim().startsWith("{") || value.trim().startsWith("[")
          ? JSON.parse(value)
          : value;
      setEditedArgs((prev) => ({ ...prev, [key]: parsed }));
    } catch {
      setEditedArgs((prev) => ({ ...prev, [key]: value }));
    }
  };

  const submit = () => {
    if (!complete) return;
    // 行序组装——官方按索引一一对应，数量不符官方 ValueError（前端先挡）
    const list = actionRequests.map((_, i) => decisions[i]);
    onResume({ decisions: list });
  };

  // r49 双钮："批准并记住这类"——先存精确规则（tool+规范化键）再按批准处理该行。
  // 记不住（网络/后端异常）也照样批准——不挡爸爸的活；规则在设置页可删。
  const rememberAndApprove = async (i: number) => {
    const r = actionRequests[i];
    try {
      await apiFetch(`${API}/remember-rules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tool: r.name, args: r.args }),
      });
    } catch {
      /* 静默——批准本身不受影响 */
    }
    setDecision(i, { type: "approve" });
  };

  return (
    <div className="w-full rounded-md border border-border bg-muted/30 p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-foreground">
        <AlertCircle size={16} className="text-yellow-600 dark:text-yellow-400" />
        <span className="text-xs font-semibold uppercase tracking-wider">
          Approval Required · {n} 项待批
        </span>
        {highCount > 0 && (
          <span className="flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
            <ShieldAlert size={13} /> 高危 {highCount} 项需逐项批示
          </span>
        )}
      </div>

      <div className="mb-3 flex flex-col gap-2">
        {actionRequests.map((r, i) => {
          const high = isHighRisk(r.name);
          const d = decisions[i];
          const isEditingRow = editingIdx === i;
          return (
            <div
              key={i}
              className={cn(
                "rounded-sm border bg-background p-3",
                high ? "border-red-400/70 dark:border-red-500/60" : "border-border"
              )}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="flex items-center gap-2">
                  <span className="font-mono text-sm font-medium text-foreground">
                    {r.name}
                  </span>
                  {high && (
                    <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-semibold text-red-700 dark:bg-red-900/40 dark:text-red-300">
                      高危
                    </span>
                  )}
                  {d && (
                    <span className="text-xs text-muted-foreground">
                      （已选：{d.type === "edit" ? "改后放行" : d.type === "approve" ? "批准" : "拒绝"}）
                    </span>
                  )}
                </span>
                {!d && !isEditingRow && (
                  <span className="flex gap-1.5">
                    {high && (
                      <Button variant="outline" size="sm" disabled={isLoading}
                        onClick={() => startEditing(i)} title="改参数后放行">
                        <Pencil size={13} />
                      </Button>
                    )}
                    <Button variant="outline" size="sm" disabled={isLoading}
                      className="text-destructive hover:bg-destructive/10"
                      onClick={() => setDecision(i, { type: "reject" })}>
                      <X size={13} /> 拒绝
                    </Button>
                    <Button size="sm" disabled={isLoading}
                      className="bg-green-600 text-white hover:bg-green-700 dark:bg-green-600 dark:hover:bg-green-700"
                      onClick={() => setDecision(i, { type: "approve" })}>
                      <Check size={13} /> 批准
                    </Button>
                    {!high && (
                      <Button variant="outline" size="sm" disabled={isLoading}
                        title="批准并记住这类：同工具同目标以后免卡（设置页可随时删）"
                        onClick={() => rememberAndApprove(i)}>
                        <BookmarkPlus size={13} /> 批准并记住
                      </Button>
                    )}
                  </span>
                )}
              </div>

              {isEditingRow ? (
                <div className="space-y-2">
                  {Object.entries(actionRequests[i].args ?? {}).map(([k, v]) => (
                    <div key={k}>
                      <label className="mb-1 block text-xs font-medium text-foreground">{k}</label>
                      <Textarea
                        value={
                          editedArgs[k] !== undefined
                            ? typeof editedArgs[k] === "string"
                              ? (editedArgs[k] as string)
                              : JSON.stringify(editedArgs[k], null, 2)
                            : typeof v === "string"
                              ? v
                              : JSON.stringify(v, null, 2)
                        }
                        onChange={(e) => updateEditedArg(k, e.target.value)}
                        className="font-mono text-xs"
                        rows={typeof v === "string" && v.length < 100 ? 2 : 4}
                        disabled={isLoading}
                      />
                    </div>
                  ))}
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" disabled={isLoading}
                      onClick={() => { setEditingIdx(null); setEditedArgs({}); }}>
                      取消
                    </Button>
                    <Button size="sm" disabled={isLoading}
                      className="bg-green-600 text-white hover:bg-green-700"
                      onClick={() => {
                        setDecision(i, { type: "edit", edited_action: { name: r.name, args: editedArgs } });
                        setEditingIdx(null);
                        setEditedArgs({});
                      }}>
                      <Check size={13} /> 存改并待批
                    </Button>
                  </div>
                </div>
              ) : (
                <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-sm border border-border bg-muted/40 p-2 font-mono text-xs text-foreground">
                  {JSON.stringify(r.args ?? {}, null, 2)}
                  {diffKeysByRow[i]?.size ? (
                    <span className="mt-1 block text-[11px] text-amber-600 dark:text-amber-400">
                      ⚠ 与同工具首行不同参数：{[...diffKeysByRow[i]].join("、")}
                    </span>
                  ) : null}
                </pre>
              )}
              {r.description && (
                <p className="mt-1 text-xs text-muted-foreground">{r.description}</p>
              )}
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {safeCount > 0 && (
          <Button variant="outline" size="sm" disabled={isLoading}
            onClick={approveAllSafe}
            title="一键批准全部安全项；高危项永远逐项批示">
            <Check size={13} /> 全部批准（安全 {safeCount} 项）
          </Button>
        )}
        <Button size="sm" disabled={!complete || isLoading}
          className="bg-green-600 text-white hover:bg-green-700 dark:bg-green-600 dark:hover:bg-green-700"
          onClick={submit}>
          <Check size={13} />
          {isLoading ? "提交中…" : complete ? `盖章放行（${n}/${n}）` : `还差 ${n - decided} 项未批示`}
        </Button>
        {decided > 0 && (
          <Button variant="ghost" size="sm" disabled={isLoading}
            onClick={() => setDecisions({})}>
            重选
          </Button>
        )}
      </div>
      {!complete && (
        <p className="mt-2 text-xs text-muted-foreground">
          每一行都要有个说法（批准/拒绝/改后放行），齐了才能盖章——这是防手滑，不是防您。
        </p>
      )}
    </div>
  );
}
