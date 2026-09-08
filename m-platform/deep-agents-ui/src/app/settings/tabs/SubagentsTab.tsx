'use client';

/**
 * settings/tabs/SubagentsTab.tsx —— 工人岗矩阵（admin:subagents）页（原 page.tsx L836-973 原样迁出）
 * Sub-agents（open-webui 式：子代理数=这里建几头工人岗，deepagents 官方机制，无需额外开关）。
 * 真实服务商 key + 职业设定 + 思维档 + boss 回退链（R64：回退链必须设置页自己填自己选，不许硬编码）。
 * 改谁更新谁，其他工人岗不动；保存后需重启容器生效（助手启动时读取）。
 */

import { useState } from 'react';
import { Plus } from 'lucide-react';
import { useSettings } from '../context';
import { Section, inputC } from '../ui';

export default function SubagentsTab() {
  const { draftRef, agents, providers, modelsByProvider, set, flash } = useSettings();
  const [expandedAgents, setExpandedAgents] = useState<Set<string>>(new Set()); // 工人岗默认折叠
  const [addAgentOpen, setAddAgentOpen] = useState(false);
  const [addAgentName, setAddAgentName] = useState('');
  return (
    <>
      <h2 className="mb-1 text-lg font-medium">工人岗矩阵</h2>
      <p className="mb-5 text-xs text-gray-500">子代理数=这里建几头工人岗（deepagents 官方机制，无需额外开关）；确认分档在 通用→助手与安全</p>
      <Section first title="工人岗矩阵（职业设定 + 模型指派）">
        <p className="text-[0.6875rem] text-gray-400 dark:text-gray-600">改谁更新谁，其他工人岗不动；保存后需重启容器生效（助手启动时读取）。</p>
        <button
          className="flex w-full items-center justify-center gap-1 rounded-lg border border-dashed border-gray-300 dark:border-gray-700 px-3 py-2 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-900"
          onClick={() => { setAddAgentOpen(!addAgentOpen); setAddAgentName(''); }}
        >
          <Plus className="size-3.5" /> 添加工人岗
        </button>
        {addAgentOpen && (
          <div className="flex gap-2">
            <input className={inputC} placeholder="工人岗名（英文，如 translator）" value={addAgentName} onChange={(e) => setAddAgentName(e.target.value)} />
            <button
              className="shrink-0 rounded-lg bg-gray-900 dark:bg-white px-3 py-1.5 text-xs font-medium text-white dark:text-black"
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
            <div key={k} className="rounded-lg border border-gray-100 dark:border-gray-900">
              <button className="flex w-full items-center justify-between px-3 py-2.5" onClick={() => {
                const next = new Set(expandedAgents);
                if (next.has(k)) next.delete(k); else next.add(k);
                setExpandedAgents(next);
              }}>
                <span className="flex items-center gap-2 text-sm font-medium">
                  {k}
                  {a.desc && <span className="text-[0.625rem] font-normal text-gray-500">{a.desc}</span>}
                </span>
                <span className="text-[0.625rem] text-gray-500">{open ? '收起 ▲' : '展开 ▼'}</span>
              </button>
              {open && (
                <div className="border-t border-gray-100 p-3 dark:border-gray-900">
                  <label className="mb-1 block text-[0.6875rem] text-gray-500">职业设定（擅长做什么，助手派活依据）</label>
                  <input className={inputC} defaultValue={a.desc || ''} onChange={(e) => set(`agents.${k}.desc`, e.target.value)} />
                  <div className="mt-2 flex gap-3">
                    <div className="flex-1"><label className="mb-1 block text-[0.6875rem] text-gray-500">服务商（外部连接里启用的）</label>
                      <select className={inputC} defaultValue={a.provider} onChange={(e) => set(`agents.${k}.provider`, e.target.value)}>
                        {!providers.some((p: any) => p.name === a.provider && p.enabled !== false) && (
                          <option value="">请选择服务商</option>
                        )}
                        {providers.filter((p: any) => p.enabled !== false).map((p: any) => (
                          <option key={p.name} value={p.name}>{p.name}（{(p.models_cache || []).length} 个模型）</option>
                        ))}
                      </select></div>
                    <div className="flex-[2]"><label className="mb-1 block text-[0.6875rem] text-gray-500">模型（点击弹出该服务商的列表，直接选）</label>
                      <select className={inputC} value={cowModel} onChange={(e) => set(`agents.${k}.model`, e.target.value)}>
                        {cowModel && !cowModels.includes(cowModel) && <option value={cowModel}>{cowModel}（手动值）</option>}
                        {cowModels.map((m: string) => <option key={m} value={m}>{m}</option>)}
                      </select></div>
                    <div className="w-28"><label className="mb-1 block text-[0.6875rem] text-gray-500">思维档（岗位性质，非模型属性）</label>
                      <select className={inputC} defaultValue={(draftRef.current[`agents.${k}.thinking`] ?? a.thinking ?? '') as string}
                        onChange={(e) => set(`agents.${k}.thinking`, e.target.value)}>
                        <option value="">（默认）</option>
                        <option value="off">关闭</option>
                        <option value="low">低</option>
                        <option value="medium">中</option>
                        <option value="high">高</option>
                      </select></div>
                  </div>
                  {/* R64 回退链编辑（管理员定：回退链必须设置页自己填自己选，不许硬编码） */}
                  {k === 'boss' && (() => {
                    const fbs = (draftRef.current[`agents.${k}.fallbacks`] ?? (a.fallbacks || [])) as any[];
                    return (
                      <div className="mt-3">
                        <label className="mb-1 block text-[0.6875rem] text-gray-500">回退链（主模型异常时按顺序降级；留空 = 不回退，托底走 .env）</label>
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
                              className="px-1 text-xs text-red-400 hover:text-red-300"
                              onClick={() => set(`agents.${k}.fallbacks`, fbs.filter((_: any, i: number) => i !== fi))}
                            >✕</button>
                          </div>
                        ))}
                        <button
                          className="mt-1 text-[0.625rem] text-gray-500 hover:text-gray-300"
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
    </>
  );
}
