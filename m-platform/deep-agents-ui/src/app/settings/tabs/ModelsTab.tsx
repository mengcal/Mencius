'use client';

/**
 * settings/tabs/ModelsTab.tsx —— 模型（admin:models）页（原 page.tsx L788-833 原样迁出）
 * 管理员按模型单独设置提示词/参数（留空 = 用全局）；搜索时全展开，平时默认折叠。
 */

import { useState } from 'react';
import { Search } from 'lucide-react';
import { useSettings } from '../context';
import ModelConfigRow from '../rows/ModelConfigRow';

export default function ModelsTab() {
  const { providers, val, set } = useSettings();
  const [modelSearch, setModelSearch] = useState('');
  const [expandedProviders, setExpandedProviders] = useState<Set<string>>(new Set()); // 模型页默认全折叠，点哪展开哪
  return (
    <>
      <h2 className="mb-1 text-lg font-medium">模型</h2>
      <p className="mb-5 text-xs text-gray-500">
        管理员可按模型单独设置提示词与参数（留空 = 用全局设置）；普通用户只有"通用"里的全局提示词
      </p>
      <div className="mb-4 flex items-center gap-1.5 rounded-lg bg-gray-100 dark:bg-gray-900 px-2 py-1.5 text-xs text-gray-500 dark:text-gray-400">
        <Search className="size-3.5" />
        <input value={modelSearch} onChange={(e) => setModelSearch(e.target.value)} placeholder="搜索模型…" className="w-full bg-transparent outline-none" />
      </div>
      {providers.filter((p) => (p.models_cache || []).some((m: string) => { if (!modelSearch.trim()) return true; const n = (x: string) => x.toLowerCase().replace(/[-_.]/g, ""); return n(m).includes(n(modelSearch)); })).map((p: any) => {
        const filtered = p.models_cache.filter((m: string) => { if (!modelSearch.trim()) return true; const n = (x: string) => x.toLowerCase().replace(/[-_.]/g, ""); return n(m).includes(n(modelSearch)); });
        const open = !!modelSearch.trim() || expandedProviders.has(p.name); // 搜索时全展开，平时默认折叠
        return (
          <div key={p.name} className="rounded-lg border border-gray-100 dark:border-gray-900">
            <button
              className="flex w-full items-center justify-between px-3 py-2.5"
              onClick={() => {
                const next = new Set(expandedProviders);
                if (next.has(p.name)) next.delete(p.name); else next.add(p.name);
                setExpandedProviders(next);
              }}
            >
              <span className="flex items-center gap-2 text-sm font-medium">
                {p.name}
                <span className="text-[0.625rem] text-gray-500">{(p.models_cache || []).length} 个模型</span>
              </span>
              <span className="text-[0.625rem] text-gray-500">{open ? '收起 ▲' : '展开 ▼'}</span>
            </button>
            {open && (
              <div className="flex flex-col gap-2 border-t border-gray-100 p-3 dark:border-gray-900">
                {filtered.map((m: string) => (
                  <ModelConfigRow key={`${p.name}/${m}`} model={m} provider={p.name} val={val} set={set} />
                ))}
              </div>
            )}
          </div>
        );
      })}
      {!providers.some((p) => (p.models_cache || []).some((m: string) => !modelSearch.trim() || m.toLowerCase().includes(modelSearch.trim().toLowerCase()))) && (
        <p className="text-xs text-gray-500">
          {modelSearch.trim() ? '没有匹配的模型。' : '还没有模型缓存——先去"外部连接"点齿轮拉取模型列表。'}
        </p>
      )}
    </>
  );
}
