'use client';

/**
 * settings/tabs/ConnectionsTab.tsx —— 外部连接（admin:connections）页（原 page.tsx L743-785 + L484-533 + 弹窗 L1186-1227 迁出）
 * 参考 open-webui 交互：填地址+密钥→自动拉模型→启停/刷新/删除/行内改名，全界面操作无需编辑文件。
 * 含「添加/编辑服务商」弹窗（一个框管添加+编辑，密钥掩码可显隐，三协议模式）。
 * 单条 upsert（参考 open-webui/Dify 交互：每个供应商独立保存，绝不塞进整表大草稿——那是崩溃根源）。
 */

import { useState } from 'react';
import { Plus, RefreshCw, Trash2 } from 'lucide-react';
import { postProviderAction } from '@/lib/providerApi';
import { useSettings } from '../context';
import { Section, Switch, inputC } from '../ui';

export default function ConnectionsTab() {
  const { S, providers, flash, reload } = useSettings();
  const [addOpen, setAddOpen] = useState(false);
  const [editName, setEditName] = useState<string | null>(null); // null=添加，非空=编辑该服务商
  const [showKey, setShowKey] = useState(false);
  const [addForm, setAddForm] = useState<{ name: string; base_url: string; api_key: string; tag: string; mode: string }>({ name: '', base_url: '', api_key: '', tag: '', mode: 'chat_completions' });

  // ── 服务商管理（界面点选完成，无需编辑任何文件）──
  const openAdd = () => { setEditName(null); setShowKey(false); setAddForm({ name: '', base_url: '', api_key: '', tag: '有限免费', mode: 'chat_completions' }); setAddOpen(true); };
  const openEdit = (p: any) => { setEditName(p.name); setShowKey(false); setAddForm({ name: p.name, base_url: p.base_url || '', api_key: '', tag: p.tag || '', mode: p.mode || 'chat_completions' }); setAddOpen(true); };
  const addProvider = async () => {
    if (!addForm.name.trim() || !addForm.base_url.trim()) { flash('名称和地址都要填'); return; }
    flash('保存并拉取中…');
    const j = await postProviderAction('add', { name: addForm.name, base_url: addForm.base_url, api_key: addForm.api_key });
    if (j.ok) {
      await postProviderAction('update', { name: addForm.name, tag: addForm.tag, mode: addForm.mode }); // 标签/协议走单条 update
      flash(`${j.name} 已添加，拉到 ${j.count} 个模型 ✓`);
      setAddOpen(false); setEditName(null);
      await reload();
    } else flash(j.error || '失败');
  };
  const saveEdit = async () => {
    if (!editName) return;
    const patch: Record<string, any> = { base_url: addForm.base_url, tag: addForm.tag, mode: addForm.mode };
    if (addForm.api_key.trim()) patch.api_key = addForm.api_key.trim(); // 留空=不改密钥
    flash('保存中…');
    const j = await postProviderAction('update', { name: editName, ...patch });
    if (j.ok) { flash('已更新 ✓'); setAddOpen(false); setEditName(null); await reload(); }
    else flash(j.error || '更新失败');
  };
  const refreshProvider = async (name: string) => {
    flash('拉取中…');
    const j = await postProviderAction('refresh', { name });
    if (j.ok) { flash(`${name} 拉到 ${j.count} 个模型 ✓`); await reload(); }
    else flash(j.error || '失败');
  };
  const renameProvider = async (old: string, nw: string) => {
    const j = await postProviderAction('rename', { old, new: nw });
    if (j.ok) {
      flash(`已改名：${old} → ${nw}${j.agents_updated?.length ? `（联动工人岗 ${j.agents_updated.join('、')}）` : ''}`);
      await reload();
    } else { flash(j.error || '改名失败'); await reload(); }
  };
  const toggleProvider = async (name: string, enabled: boolean) => {
    await postProviderAction('toggle', { name, enabled });
    await reload();
  };
  const deleteProvider = async (name: string) => {
    if (!window.confirm(`确定删除服务商「${name}」？助手和工人岗将立刻无法使用它。`)) return;
    await postProviderAction('delete', { name });
    flash('已删除');
    await reload();
  };

  return (
    <>
      <h2 className="mb-1 text-lg font-medium">外部连接</h2>
      <p className="mb-5 text-xs text-gray-500">
        添加后全平台可用：助手对话框的模型列表、工人岗矩阵下拉、按模型设置，全部吃这里拉取的列表——不用再手动编辑任何文件
      </p>
      <Section first title="OpenAI 接口">
        <button
          className="mb-1 flex w-full items-center justify-center gap-1 rounded-lg border border-dashed border-gray-300 dark:border-gray-700 px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-900"
          onClick={() => { (S.external?.providers || []).forEach((p: any, i: number) => p.enabled !== false && setTimeout(() => refreshProvider(p.name), i * 1200)); }}
        >
          <RefreshCw className="size-3" /> 全部刷新模型列表
        </button>
        <button
          className="flex w-full items-center justify-center gap-1 rounded-lg border border-dashed border-gray-300 dark:border-gray-700 px-3 py-2 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-900"
          onClick={openAdd}
        >
          <Plus className="size-3.5" /> 添加服务商
        </button>
        {providers.map((p) => (
          <div key={p.name} className="flex items-center gap-2">
            <input
              className={'bg-gray-100 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg px-3 py-1.5 text-xs text-gray-800 dark:text-gray-200 outline-none focus:border-gray-500 w-28 shrink-0'}
              defaultValue={p.name}
              title="点击改名（自动联动工人岗配置）"
              onBlur={(e) => { const old = p.name, nw = e.target.value.trim(); if (nw && nw !== old) renameProvider(old, nw); }}
            />
            <span className="flex-1 truncate text-xs text-gray-600 dark:text-gray-400" title={p.base_url}>{p.base_url}</span>
            {p.tag && <span className="shrink-0 rounded-full bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-[0.625rem] text-gray-500">{p.tag}</span>}
            <span className="shrink-0 text-[0.625rem] text-gray-400">{p.mode === 'anthropic' ? 'Anthropic' : p.mode === 'responses' ? 'Responses' : 'Chat'}</span>
            <button title={`${p.name} · 重新拉取模型列表`} onClick={() => refreshProvider(p.name)} className="shrink-0 rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-900">
              {p.models_cache?.length ? <span className="text-[0.625rem]">{p.models_cache.length}</span> : <RefreshCw className="size-3.5" />}
            </button>
            <Switch checked={p.enabled !== false} onChange={(v) => toggleProvider(p.name, v)} />
            <button title={`编辑 ${p.name}（地址/密钥/标签/协议）`} onClick={() => openEdit(p)} className="shrink-0 rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-900">⚙</button>
            <button title={`删除 ${p.name}`} onClick={() => deleteProvider(p.name)} className="shrink-0 rounded-lg p-1.5 text-red-400 hover:bg-gray-100 dark:hover:bg-gray-900">
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
      </Section>

      {/* ── 添加/编辑服务商弹窗（外置式编辑弹窗（参考成熟 agent 平台）：一个框管添加+编辑，密钥掩码可显隐，三协议模式）── */}
      {addOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setAddOpen(false)}>
          <div className="w-[480px] rounded-xl border border-gray-200 bg-white p-5 shadow-2xl dark:border-gray-800 dark:bg-gray-900" onClick={(e) => e.stopPropagation()}>
            <h3 className="mb-4 text-base font-medium text-gray-900 dark:text-white">{editName ? `编辑连接 · ${editName}` : '添加连接'}</h3>
            <label className="mb-1 block text-xs text-gray-500">名称</label>
            <input className={inputC + (editName ? ' opacity-60' : '')} readOnly={!!editName} placeholder="如：智谱 / 魔搭 / 书生 / DeepSeek" value={addForm.name} onChange={(e) => setAddForm({ ...addForm, name: e.target.value })} />
            {editName && <p className="mt-1 text-[0.625rem] text-gray-400">改名请在列表行内直接改（会自动联动工人岗配置）</p>}
            <label className="mb-1 mt-3 block text-xs text-gray-500">接口地址（URL）</label>
            <input className={inputC} placeholder="https://open.bigmodel.cn/api/paas/v4" value={addForm.base_url} onChange={(e) => setAddForm({ ...addForm, base_url: e.target.value })} />
            <label className="mb-1 mt-3 block text-xs text-gray-500">API 密钥（KEY）</label>
            <div className="flex items-center gap-1">
              <input className={inputC + ' flex-1'} type={showKey ? 'text' : 'password'} placeholder={editName ? '留空 = 保持当前密钥不变' : 'sk-… / 粘贴密钥'} value={addForm.api_key} onChange={(e) => setAddForm({ ...addForm, api_key: e.target.value })} />
              <button type="button" title={showKey ? '隐藏' : '显示'} onClick={() => setShowKey(!showKey)} className="shrink-0 rounded-lg px-2 py-1.5 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800">{showKey ? '🙈' : '👁'}</button>
            </div>
            <div className="mt-3 flex gap-3">
              <div className="flex-1">
                <label className="mb-1 block text-xs text-gray-500">标签</label>
                <select className={inputC} value={addForm.tag} onChange={(e) => setAddForm({ ...addForm, tag: e.target.value })}>
                  <option value="">（无）</option>
                  <option value="有限免费">有限免费</option>
                  <option value="付费">付费</option>
                </select>
              </div>
              <div className="flex-1">
                <label className="mb-1 block text-xs text-gray-500">协议模式</label>
                <select className={inputC} value={addForm.mode} onChange={(e) => setAddForm({ ...addForm, mode: e.target.value })}>
                  <option value="chat_completions">Chat Completions</option>
                  <option value="anthropic">Anthropic Messages</option>
                  <option value="responses">Responses</option>
                </select>
              </div>
            </div>
            <p className="mt-3 text-[0.6875rem] text-gray-400 dark:text-gray-600">{editName ? '改地址/密钥后记得点"重新拉取模型列表"刷新缓存。' : '保存时自动 GET /models 拉取模型列表，拉到即全平台可用。'}</p>
            <div className="mt-4 flex justify-end gap-2">
              <button className="rounded-lg px-3 py-1.5 text-xs text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800" onClick={() => setAddOpen(false)}>取消</button>
              <button className="rounded-lg bg-gray-900 dark:bg-white px-4 py-1.5 text-xs font-medium text-white dark:text-black" onClick={() => (editName ? saveEdit() : addProvider())}>
                {editName ? '保存' : '保存并拉取模型'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
