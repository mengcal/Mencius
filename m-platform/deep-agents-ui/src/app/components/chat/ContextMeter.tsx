'use client';

/**
 * components/chat/ContextMeter.tsx —— R53 上下文容量（ZCode 同款）→ r39d 重修（爸 09-29"不好用"案）
 * ------------------------------------------------------------------
 * 照 ZCode 版式：大字总量/窗口+占比 → 进度条 → 明细行（基线/消息/轮次/累计输出/模型）。
 * 数据源 GET /context/threads（管理员 Bearer）；当前对话无记录时列出最近对话容量榜（不再一句干话）。
 * ZCode 的"消息/工具/MCP 分区"依赖其内部 prompt 构成统计，M 平台 usage.jsonl 无此维度——不造假，只报真实可算项。
 * ZCode 的"今日余额"=客户端调智谱额度 API；M 平台同款=二期聚合各服务商余额接口（方案已报爸）。
 */

import { useState } from "react";
import { API, apiFetch } from "@/lib/apiBase";
import { authHeaders } from "@/lib/providerApi";

const fmt = (n: any) => Math.round(Number(n) || 0).toLocaleString();

export function ContextMeter({ tidNow }: { tidNow: string }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [data, setData] = useState<any>(null);
  return (
    <div className="relative">
      <button
        type="button"
        onClick={async (e) => {
          const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
          setPos({ x: r.right, y: r.top });
          const next = !open;
          setOpen(next);
          if (next) {
            setData(null);
            try {
              const j = await apiFetch(`${API}/context/threads`, { headers: authHeaders() }).then((x) => x.json());
              setData(j);
            } catch { setData({ error: "读取失败" }); }
          }
        }}
        className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-tertiary transition-colors hover:bg-accent hover:text-primary"
        title="上下文容量（ZCode 同款显示图）"
      >
        📐
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="fixed z-50 w-80 rounded-lg border border-border bg-popover p-3 shadow-md text-xs" style={{ bottom: window.innerHeight - pos.y + 6, left: Math.max(pos.x - 320, 8) }}>
            <div className="mb-2 font-medium">上下文容量</div>
            {(() => {
              if (!data || data.error) return <div className="text-tertiary">{data?.error || "加载中…"}</div>;
              const threads: any[] = data.threads || [];
              const mine = threads.find((t) => t.thread === tidNow);
              const row = (k: string, v: string, cls = "text-muted-foreground") => (
                <div className={`flex justify-between ${cls}`}><span>{k}</span><span>{v}</span></div>
              );
              if (!mine) return (
                <div>
                  <div className="mb-2 text-tertiary">本对话首轮完成后出记录（数据源=每次模型调用流水）。最近对话：</div>
                  {threads.length === 0 && <div className="text-tertiary">暂无任何记录</div>}
                  {threads.slice(0, 5).map((t) => (
                    <button key={t.thread} className="mb-1 flex w-full justify-between rounded px-1 py-0.5 hover:bg-accent" onClick={() => setOpen(false)}>
                      <span className="truncate">{(t.ts || "").slice(5, 16)} · {t.model}</span>
                      <span className={t.pct > 80 ? "text-orange-400" : ""}>{fmt(t.input)} tok{t.pct ? ` · ${t.pct}%` : ""}</span>
                    </button>
                  ))}
                </div>
              );
              const pct = mine.pct || 0;
              const msgs = Math.max(mine.input - mine.baseline, 0);
              return (
                <>
                  <div className="mb-1 flex items-baseline justify-between">
                    <span className="text-sm font-medium">{fmt(mine.input)} / {mine.limit != null ? fmt(mine.limit) : "未知"}</span>
                    <span className={pct > 80 ? "text-orange-400" : "text-tertiary"}>{pct}%{mine.limit == null && "（去模型页补窗口表）"}</span>
                  </div>
                  <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-gray-700">
                    <div className={pct > 80 ? "bg-orange-400" : "bg-blue-400"} style={{ width: `${Math.min(pct, 100)}%`, height: "100%" }} />
                  </div>
                  {row("系统提示词+工具（基线）", `~${fmt(mine.baseline)} tok`)}
                  {row("对话消息", `~${fmt(msgs)} tok`)}
                  {row("调用轮次", `${mine.calls ?? "?"} 次`)}
                  {row("累计输出", `${fmt(mine.out_total)} tok`)}
                  {row("最近活动", (mine.ts || "").slice(5, 16))}
                  {row("模型", `${mine.model}${mine.limit != null ? ` · 窗口 ${fmt(mine.limit)}` : ""}`)}
                </>
              );
            })()}
          </div>
        </>
      )}
    </div>
  );
}
