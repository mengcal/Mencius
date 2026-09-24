'use client';

/**
 * settings/tabs/ModelsTab.tsx —— 模型（admin:models）页（原 page.tsx L788-833 原样迁出）
 * 管理员按模型单独设置提示词/参数（留空 = 用全局）；搜索时全展开，平时默认折叠。
 * W4：底部「上下文窗口表」等输入从「白底浅灰字」改 W1 深色高对比；JSON 框给等宽字体 + 13px。
 * W1：字号/控件统一走 ui.tsx 的四档 token。
 */

import { useState } from 'react';
import { Search } from 'lucide-react';
import { useSettings } from '../context';
import {
  Section, Row, inputC, inputMonoClass, cardClass, pageTitleClass, pageSubtitleClass,
} from '../ui';
import ModelConfigRow from '../rows/ModelConfigRow';

export default function ModelsTab() {
  const { providers, val, set } = useSettings();
  const [modelSearch, setModelSearch] = useState('');
  const [expandedProviders, setExpandedProviders] = useState<Set<string>>(new Set()); // 模型页默认全折叠，点哪展开哪
  return (
    <>
      <h2 className={pageTitleClass}>模型</h2>
      <p className={pageSubtitleClass}>
        管理员可按模型单独设置提示词与参数（留空 = 用全局设置）；普通用户只有「通用」里的全局提示词
      </p>
      <div className="mb-4 flex items-center gap-1.5 rounded-[10px] border border-border bg-card px-3 py-1.5 text-sm text-muted-foreground">
        <Search className="size-3.5" />
        <input value={modelSearch} onChange={(e) => setModelSearch(e.target.value)} placeholder="搜索模型…" className="w-full bg-transparent outline-none placeholder:text-muted-foreground" />
      </div>
      {providers.filter((p) => (p.models_cache || []).some((m: string) => { if (!modelSearch.trim()) return true; const n = (x: string) => x.toLowerCase().replace(/[-_.]/g, ""); return n(m).includes(n(modelSearch)); })).map((p: any) => {
        const filtered = p.models_cache.filter((m: string) => { if (!modelSearch.trim()) return true; const n = (x: string) => x.toLowerCase().replace(/[-_.]/g, ""); return n(m).includes(n(modelSearch)); });
        const open = !!modelSearch.trim() || expandedProviders.has(p.name); // 搜索时全展开，平时默认折叠
        return (
          <div key={p.name} className={cardClass + ' mb-3'}>
            <button
              className="flex w-full items-center justify-between px-4 py-3"
              onClick={() => {
                const next = new Set(expandedProviders);
                if (next.has(p.name)) next.delete(p.name); else next.add(p.name);
                setExpandedProviders(next);
              }}
            >
              <span className="flex items-center gap-2 text-sm font-medium">
                {p.name}
                <span className="text-xxs text-muted-foreground">{(p.models_cache || []).length} 个模型</span>
              </span>
              <span className="text-xxs text-muted-foreground">{open ? '收起 ▲' : '展开 ▼'}</span>
            </button>
            {open && (
              <div className="flex flex-col gap-3 border-t border-border p-4">
                {filtered.map((m: string) => (
                  <ModelConfigRow key={`${p.name}/${m}`} model={m} provider={p.name} val={val} set={set} />
                ))}
              </div>
            )}
          </div>
        );
      })}
      {!providers.some((p) => (p.models_cache || []).some((m: string) => !modelSearch.trim() || m.toLowerCase().includes(modelSearch.trim().toLowerCase()))) && (
        <p className="text-sm text-muted-foreground">
          {modelSearch.trim() ? '没有匹配的模型。' : '还没有模型缓存——先去「外部连接」点齿轮拉取模型列表。'}
        </p>
      )}
      {/* 09-17 深夜 schema 收口：批②③⑤新键补 UI（键名/默认值单一来源=settings_schema.py，此处只读写） */}
      <Section title="模型运行参数">
        <Row label="重试次数 (model.maxRetries)" description="模型调用失败（429/慢响应）时的自动重试次数">
          <input className={inputC + ' w-24'} type="number" defaultValue={val('model.maxRetries', 3)} onBlur={(e) => set('model.maxRetries', Number(e.target.value) || 3)} />
        </Row>
        <Row label="请求超时秒 (model.requestTimeout)" description="单次模型请求的最长等待秒数">
          <input className={inputC + ' w-28'} type="number" defaultValue={val('model.requestTimeout', 90)} onBlur={(e) => set('model.requestTimeout', Number(e.target.value) || 90)} />
        </Row>
        <Row label="未知模型窗口兜底 (models.contextLimitDefault)" description="上下文窗口表里查不到的模型用这个 token 数兜底">
          <input className={inputC + ' w-32'} type="number" defaultValue={val('models.contextLimitDefault', 131072)} onBlur={(e) => set('models.contextLimitDefault', Number(e.target.value) || 131072)} />
        </Row>
        <div>
          <label className="mb-1 block text-sm text-foreground">上下文窗口表 (models.contextLimits)</label>
          <p className="mb-1 text-xxs text-muted-foreground">JSON：模型名 → token 数，覆盖内置默认表。</p>
          <textarea
            className={inputMonoClass + ' min-h-24 resize-y'}
            rows={4}
            defaultValue={JSON.stringify(val('models.contextLimits', { 'glm-4.7': 200000, 'glm-4.5-air': 131072, 'glm-4.6v': 65536 }))}
            onBlur={(e) => { try { set('models.contextLimits', JSON.parse(e.target.value)); } catch { /* 非法 JSON 不写入 */ } }}
          />
        </div>
      </Section>
    </>
  );
}
