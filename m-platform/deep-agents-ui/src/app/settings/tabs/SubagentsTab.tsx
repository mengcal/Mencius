'use client';

/**
 * settings/tabs/SubagentsTab.tsx —— 牛马矩阵（admin:subagents）页（原 page.tsx L836-973 原样迁出）
 * Sub-agents（OWUI 式：子代理数=这里建几头牛马，deepagents 官方机制，无需额外开关）。
 * 真实服务商 key + 职业设定 + 思维档 + boss 回退链（R64：回退链必须设置页自己填自己选，不许硬编码）。
 * 改谁更新谁，其他牛马不动；保存后需重启容器生效（米娅启动时读取）。
 * W1：字号归四档 token，卡片壳统一 cardClass。
 */

import { useState } from 'react';
import { Plus } from 'lucide-react';
import { useSettings } from '../context';
import { Section, inputC, cardClass, pageTitleClass, pageSubtitleClass } from '../ui';

export default function SubagentsTab() {
  const { draftRef, agents, providers, modelsByProvider, val, set, flash } = useSettings();
  const [expandedAgents, setExpandedAgents] = useState<Set<string>>(new Set()); // 牛马默认折叠
  const [addAgentOpen, setAddAgentOpen] = useState(false);
  const [addAgentName, setAddAgentName] = useState('');
  return (
    <>
      <h2 className={pageTitleClass}>牛马矩阵</h2>
      <p className={pageSubtitleClass}>子代理数=这里建几头牛马（deepagents 官方机制，无需额外开关）；确认分档在 通用→米娅与安全</p>
      <Section first title="牛马矩阵（职业设定 + 模型指派）">
        <p className="text-xxs text-muted-foreground">改谁更新谁，其他牛马不动；保存后需重启容器生效（米娅启动时读取）。</p>
        <button
          className="flex w-full items-center justify-center gap-1 rounded-[10px] border border-dashed border-border px-3 py-2 text-sm text-muted-foreground hover:bg-muted"
          onClick={() => { setAddAgentOpen(!addAgentOpen); setAddAgentName(''); }}
        >
          <Plus className="size-3.5" /> 添加牛马
        </button>
        {addAgentOpen && (
          <div className="flex gap-2">
            <input className={inputC} placeholder="牛马名（英文，如 translator）" value={addAgentName} onChange={(e) => setAddAgentName(e.target.value)} />
            <button
              className="shrink-0 rounded-[10px] bg-gray-900 px-3 py-2 text-sm font-medium text-white dark:bg-white dark:text-black"
              onClick={() => {
                const name = addAgentName.trim();
                if (!name || agents[name]) { flash('名字不能为空或已存在'); return; }
                set(`agents.${name}.provider`, providers.find((p: any) => p.enabled !== false)?.name || '');
                set(`agents.${name}.model`, '');
                set(`agents.${name}.desc`, '');
                flash('已加入草稿，填好后点右下角保存');
                setAddAgentOpen(false);
              }}
            >
              添加
            </button>
          </div>
        )}
        {Object.entries(agents).map(([k, a]: any) => {
          const open = expandedAgents.has(k);
          const cowProvider = draftRef.current[`agents.${k}.provider`] ?? a.provider ?? '';
          const cowModel = draftRef.current[`agents.${k}.model`] ?? a.model ?? '';
          const cowModels = modelsByProvider[cowProvider] || [];
          return (
            <div key={k} className={cardClass}>
              <button className="flex w-full items-center justify-between px-4 py-3" onClick={() => {
                const next = new Set(expandedAgents);
                if (next.has(k)) next.delete(k); else next.add(k);
                setExpandedAgents(next);
              }}>
                <span className="flex items-center gap-2 text-sm font-medium">
                  {k}
                  {a.desc && <span className="text-xxs font-normal text-muted-foreground">{a.desc}</span>}
                </span>
                <span className="text-xxs text-muted-foreground">{open ? '收起 ▲' : '展开 ▼'}</span>
              </button>
              {open && (
                <div className="border-t border-border p-4">
                  <label className="mb-1 block text-sm text-muted-foreground">职业设定（擅长做什么，米娅派活依据）</label>
                  <input className={inputC} defaultValue={a.desc || ''} onChange={(e) => set(`agents.${k}.desc`, e.target.value)} />
                  <div className="mt-3 flex gap-3">
                    <div className="flex-1"><label className="mb-1 block text-sm text-muted-foreground">服务商（外部连接里启用的）</label>
                      <select className={inputC} defaultValue={a.provider} onChange={(e) => set(`agents.${k}.provider`, e.target.value)}>
                        {!providers.some((p: any) => p.name === a.provider && p.enabled !== false) && (
                          <option value="">请选择服务商</option>
                        )}
                        {providers.filter((p: any) => p.enabled !== false).map((p: any) => (
                          <option key={p.name} value={p.name}>{p.name}（{(p.models_cache || []).length} 个模型）</option>
                        ))}
                      </select></div>
                    <div className="flex-[2]"><label className="mb-1 block text-sm text-muted-foreground">模型（点击弹出该服务商的列表，直接选）</label>
                      <select className={inputC} value={cowModel} onChange={(e) => set(`agents.${k}.model`, e.target.value)}>
                        {cowModel && !cowModels.includes(cowModel) && <option value={cowModel}>{cowModel}（手动值）</option>}
                        {cowModels.map((m: string) => <option key={m} value={m}>{m}</option>)}
                      </select></div>
                    <div className="w-28"><label className="mb-1 block text-sm text-muted-foreground">思维档（岗位性质，非模型属性）</label>
                      <select className={inputC} defaultValue={(draftRef.current[`agents.${k}.thinking`] ?? a.thinking ?? '') as string}
                        onChange={(e) => set(`agents.${k}.thinking`, e.target.value)}>
                        <option value="">（默认）</option>
                        <option value="off">关闭</option>
                        <option value="low">低</option>
                        <option value="medium">中</option>
                        <option value="high">高</option>
                      </select></div>
                  </div>
                  {/* R64 回退链编辑（爸爸定：回退链必须设置页自己填自己选，不许硬编码） */}
                  {k === 'boss' && (() => {
                    const fbs = (draftRef.current[`agents.${k}.fallbacks`] ?? (a.fallbacks || [])) as any[];
                    return (
                      <div className="mt-3">
                        <label className="mb-1 block text-sm text-muted-foreground">回退链（主模型异常时按顺序降级；留空 = 不回退，托底走 .env）</label>
                        {fbs.map((fb: any, fi: number) => (
                          <div key={fi} className="mt-1 flex items-center gap-2">
                            <select
                              className={inputC + ' flex-1'}
                              value={fb.provider || ''}
                              onChange={(e) => {
                                const arr = [...fbs];
                                arr[fi] = { ...arr[fi], provider: e.target.value };
                                set(`agents.${k}.fallbacks`, arr);
                              }}
                            >
                              <option value="">选服务商</option>
                              {providers.filter((p: any) => p.enabled !== false).map((p: any) => (
                                <option key={p.name} value={p.name}>{p.name}</option>
                              ))}
                            </select>
                            <select
                              className={inputC + ' flex-[2]'}
                              value={fb.model || ''}
                              onChange={(e) => {
                                const arr = [...fbs];
                                arr[fi] = { ...arr[fi], model: e.target.value };
                                set(`agents.${k}.fallbacks`, arr);
                              }}
                            >
                              <option value="">选模型</option>
                              {(modelsByProvider[fb.provider] || []).map((m: string) => (
                                <option key={m} value={m}>{m}</option>
                              ))}
                              {fb.model && !(modelsByProvider[fb.provider] || []).includes(fb.model) && (
                                <option value={fb.model}>{fb.model}（手动值）</option>
                              )}
                            </select>
                            <button
                              className="px-1 text-sm text-red-400 hover:text-red-300"
                              onClick={() => set(`agents.${k}.fallbacks`, fbs.filter((_: any, i: number) => i !== fi))}
                            >✕</button>
                          </div>
                        ))}
                        <button
                          className="mt-1 text-xxs text-muted-foreground hover:text-foreground"
                          onClick={() => set(`agents.${k}.fallbacks`, [...fbs, { provider: '', model: '' }])}
                        >＋ 添加一档回退</button>
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          );
        })}
      </Section>
      {/* 09-17 深夜知夏拍板归类：外部岗相关键归牛马矩阵页（原暂放"米娅与安全"，语义不符） */}
      <Section title="外部岗网关">
        <div className="flex flex-wrap gap-3 text-sm">
          <label className="flex flex-col gap-1">领取超时（秒）
            <input className={inputC + ' w-28'} type="number" defaultValue={val('approvals.claimTimeout', 1800)}
              onBlur={(e) => set('approvals.claimTimeout', Number(e.target.value) || 1800)} />
          </label>
          <label className="flex flex-col gap-1">CodeBuddy 默认模型
            <input className={inputC + ' w-56'} defaultValue={val('codebuddy.defaultModel', 'Qwen/Qwen3.8-Flash-Next')}
              onBlur={(e) => set('codebuddy.defaultModel', e.target.value.trim() || 'Qwen/Qwen3.8-Flash-Next')} />
          </label>
          <label className="flex flex-col gap-1">可换模型白名单（逗号分隔）
            <input className={inputC + ' w-72'} defaultValue={val('codebuddy.allowedModels', '')} placeholder="留空=只许默认模型"
              onBlur={(e) => set('codebuddy.allowedModels', e.target.value.trim())} />
          </label>
        </div>
        <p className="mt-1 text-xxs text-muted-foreground">领取超时=任务卡被外部岗领走后多久无动作算超时重派；默认模型=外部岗网关的模型名（env CODEBUDDY_MODEL 仍可压过）；白名单决定米娅能按需换哪些模型（默认模型恒可）</p>
      </Section>
      {/* 09-19 schema 尾巴：围炉/圆桌朋友席 UI——五席各 {provider,model} 双必填，后端 fail-closed（缺一即报错指向本页） */}
      <Section title="围炉与圆桌（朋友席）">
        {([['hearth.A', '围炉·朋友 A 位（顺思路补漏）'],
           ['hearth.B', '围炉·朋友 B 位（提新方向）'],
           ['roundtable.A', '圆桌·朋友 A 位'],
           ['roundtable.B', '圆桌·朋友 B 位'],
           ['roundtable.host', '圆桌·主持人（留空=回退 boss，有意设计）']] as const).map(([k, label]) => {
          const cur = ((val(k, {}) || {}) as { provider?: string; model?: string });
          const commit = (patch: { provider?: string; model?: string }) => {
            const provider = String(patch.provider ?? cur.provider ?? '').trim();
            const model = String(patch.model ?? cur.model ?? '').trim();
            set(k, provider || model ? { provider, model } : {});
          };
          return (
            <div key={k} className="mb-3 flex flex-wrap items-end gap-3 text-sm">
              <span className="w-44 pb-2.5 text-foreground">{label}</span>
              {/* r33c（爸爸 09-26："改成下拉列表"）：手填改双下拉——服务商走 providers 列表，模型走该服务商 models_cache；切服务商自动清模型防错配 */}
              <label className="flex flex-col gap-1">服务商
                <select className={inputC + ' w-40'} value={cur.provider ?? ''}
                  onChange={(e) => commit({ provider: e.target.value, model: '' })}>
                  <option value="">（选择服务商）</option>
                  {providers.filter((p: any) => p.name).map((p: any) => <option key={p.name} value={p.name}>{p.name}</option>)}
                </select>
              </label>
              <label className="flex flex-col gap-1">模型
                <select className={inputC + ' w-56'} value={cur.model ?? ''} onChange={(e) => commit({ model: e.target.value })}>
                  <option value="">（选择模型）</option>
                  {(modelsByProvider[cur.provider ?? ''] || []).map((m: string) => <option key={m} value={m}>{m}</option>)}
                </select>
              </label>
            </div>
          );
        })}
        <p className="mt-1 text-xxs text-muted-foreground">围炉/圆桌的朋友席各 = {`{服务商, 模型}`} 双必填（后端 fail-closed：只配一半会明确报错并指向本页）；主持人位不配=自动回退 boss。改动失焦即存。</p>
      </Section>
    </>
  );
}
