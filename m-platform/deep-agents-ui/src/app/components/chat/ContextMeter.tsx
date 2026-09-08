'use client';

/**
 * components/chat/ContextMeter.tsx —— R53 上下文容量（ZCode 同款）（原 ChatInterface.tsx L813-864 迁出）
 * ------------------------------------------------------------------
 * 点击 📐 按钮弹出当前对话的容量条与构成（系统提示词+工具基线 / 对话消息 / 模型），
 * 数据来自 GET /context/threads（带管理员密钥 Bearer）。
 * 开合/位置/数据由本组件自持；tidNow 用于在 threads 列表里定位当前对话。
 */

import { useState } from "react";
import { API, apiFetch } from "@/lib/apiBase";
import { authHeaders } from "@/lib/providerApi";

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
          setOpen(!open);
          setData(null);
          if (!open) {
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
              const mine = (data.threads || []).find((t: any) => t.thread === tidNow);
              if (!mine) return <div className="text-tertiary">本对话还没有 token 记录（首轮完成后显示）</div>;
              const pct = mine.pct || 0;
              const baseline = mine.baseline || 0;
              const msgs = Math.max(mine.input - baseline, 0);
              return (
                <>
                  <div className="mb-1 flex justify-between">
                    <span>{Math.round(mine.input).toLocaleString()} / {mine.limit.toLocaleString()} tokens</span>
                    <span className={pct > 80 ? "text-orange-400" : "text-tertiary"}>{pct}%</span>
                  </div>
                  <div className="mb-2 h-2 w-full overflow-hidden rounded-full bg-gray-700">
                    <div className={pct > 80 ? "bg-orange-400" : "bg-blue-400"} style={{ width: `${Math.min(pct, 100)}%`, height: "100%" }} />
                  </div>
                  <div className="flex justify-between text-gray-400"><span>系统提示词+工具（基线）</span><span>~{baseline.toLocaleString()} tok</span></div>
                  <div className="flex justify-between text-gray-400"><span>对话消息</span><span>~{msgs.toLocaleString()} tok</span></div>
                  <div className="mt-1 flex justify-between text-gray-400"><span>模型</span><span>{mine.model}</span></div>
                </>
              );
            })()}
          </div>
        </>
      )}
    </div>
  );
}
