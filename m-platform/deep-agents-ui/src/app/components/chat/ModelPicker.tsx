'use client';

/**
 * components/chat/ModelPicker.tsx —— 输入框右下角模型选择（原 ChatInterface.tsx L754-812 迁出）
 * ------------------------------------------------------------------
 * 参考 open-webui 交互：按钮弹出模型列表弹层（贴按钮上沿），带模糊搜索（忽略大小写和 -_. 分隔符，
 * "lm5.3"能搜到 GLM-5.3-Flash）；选中后 onPick 落库并收起弹层。
 * 弹层开合/位置/搜索词由本组件自持；models/selected 由 useModelSelection 传入。
 */

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface ModelPickerProps {
  models: { model: string; provider: string }[];
  selectedModel: string;
  selectedProvider: string;
  onPick: (m: string, provider?: string) => void;
}

export function ModelPicker({ models, selectedModel, selectedProvider, onPick }: ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [modelSearch, setModelSearch] = useState("");
  return (
    <div className="relative">
      <button
        type="button"
        onClick={(e) => {
          const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
          setPos({ x: r.right, y: r.top });
          setOpen(!open);
          setModelSearch("");
        }}
        className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-tertiary transition-colors hover:bg-accent hover:text-primary"
        title={selectedModel || "选择模型（接线中：当前仍由助手组长模型应答）"}
      >
        {selectedModel || "模型"}
        <ChevronDown size={12} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="fixed z-50 w-80 rounded-lg border border-border bg-popover shadow-md" style={{ bottom: window.innerHeight - pos.y + 6, left: pos.x - 320 }}>
            <div className="flex items-center gap-1.5 border-b border-border px-3 py-2 text-xs text-tertiary">
              搜索模型
              <input
                autoFocus
                value={modelSearch}
                onChange={(e) => setModelSearch(e.target.value)}
                placeholder="glm / intern / qwen…"
                className="ml-1 w-full bg-transparent outline-none"
              />
            </div>
            <div className="max-h-64 overflow-y-auto py-1">
              {models.length === 0 && (
                <div className="px-3 py-2 text-tertiary">（先在设置页"外部连接"拉取模型列表）</div>
              )}
              {models.filter((m) => {
                if (!modelSearch.trim()) return true;
                // 模糊匹配：忽略大小写和 -_.分隔符（"lm5.3"能搜到 GLM-5.3-Flash）
                const norm = (s: string) => s.toLowerCase().replace(/[-_.]/g, "");
                const q = norm(modelSearch);
                return norm(m.model).includes(q) || norm(m.provider).includes(q);
              }).map((m) => (
                <button
                  key={`${m.provider}/${m.model}`}
                  type="button"
                  onClick={() => { onPick(m.model, m.provider); setOpen(false); }}
                  className={cn(
                    "flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-accent",
                    selectedModel === m.model && (!selectedProvider || selectedProvider === m.provider) && "text-primary"
                  )}
                >
                  {selectedModel === m.model && (!selectedProvider || selectedProvider === m.provider) ? "✓" : ""} {m.model}
                  <span className="ml-auto text-[0.625rem] text-gray-500">{m.provider}</span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
