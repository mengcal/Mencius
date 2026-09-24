'use client';

/**
 * settings/rows/SkillsManager.tsx —— W3 技能清单（卡片式 + 新建/编辑/删除 + 重新登记）
 * ------------------------------------------------------------------
 * 技能 = 技能目录（宿主 D:\m\skills，容器内 _SKILLS_DIR）下一个目录里的 SKILL.md：
 *   frontmatter（name/description）+ 正文。
 * 读写走后端 /skills/list|create|update|delete（管理员 token 门内，与 /skills/rehash 同门）；
 * create/update/delete 后端自动重登记 skills_lock 基线并把新哈希随响应带回。
 * 原 SkillsLockRow.tsx（纯哈希文本展示，太挤）退役，本组件接管「清单 + 增删改 + 重新登记」。
 */

import { useEffect, useState } from 'react';
import { Plus, Pencil, Trash2, RefreshCw, Search } from 'lucide-react';
import { authHeaders } from '@/lib/providerApi';
import { apiFetch } from '@/lib/apiBase';
import { inputC, cardClass, rowTitleClass, rowDescClass } from '../ui';
import { API } from '../context';

type Skill = { name: string; description: string; body: string; hash: string; status: string };
type Editor = { mode: 'create' | 'edit'; name: string; description: string; content: string };

const NAME_RE = /^[a-z0-9][a-z0-9_-]{1,40}$/;

const badgeCls = (status: string) =>
  'shrink-0 rounded-full border px-2 py-0.5 text-xxs ' +
  (status === '✓'
    ? 'border-green-600/40 text-green-600 dark:text-green-500'
    : status === '✗'
      ? 'border-red-500/40 text-red-500'
      : 'border-yellow-600/40 text-yellow-600 dark:text-yellow-500');

export default function SkillsManager() {
  const [data, setData] = useState<any>(null);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState('');
  const [editor, setEditor] = useState<Editor | null>(null);
  const [confirmDel, setConfirmDel] = useState<Skill | null>(null);

  const refresh = () => apiFetch(`${API}/skills/list`, { headers: authHeaders() })
    .then((r) => r.json()).then(setData).catch(() => setMsg('读取失败'));
  useEffect(() => { refresh(); }, []);

  const post = (path: string, body: any) => apiFetch(`${API}${path}`, {
    method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body),
  }).then((r) => r.json()).catch(() => ({ ok: false, reason: '无法连接后端' }));

  const rehash = async () => {
    setBusy(true); setMsg('');
    try {
      // 09-15 d2v03fix3⑨：后端 skills_rehash 失败帧 ok:False+reason（消费点读 j.reason）
      const j = await post('/skills/rehash', {});
      setMsg(j.ok ? `已重建（${j.count} 个文件）${j.note ? '；' + j.note : ''}` : (j.reason || '失败'));
      refresh();
    } catch { setMsg('失败'); } finally { setBusy(false); }
  };

  const submit = async () => {
    if (!editor) return;
    const name = editor.name.trim();
    if (!NAME_RE.test(name)) {
      setMsg('技能名不合法：只许小写字母/数字/-/_，2-41 位，首字符为字母或数字');
      return;
    }
    setBusy(true); setMsg('');
    const j = editor.mode === 'create'
      ? await post('/skills/create', { name, description: editor.description, content: editor.content })
      : await post('/skills/update', { name, description: editor.description, content: editor.content });
    if (j.ok) {
      setMsg(editor.mode === 'create' ? `已新建「${name}」` : `已保存「${name}」`);
      setEditor(null);
      refresh();
    } else setMsg(j.reason || '失败');
    setBusy(false);
  };

  const remove = async () => {
    if (!confirmDel) return;
    setBusy(true); setMsg('');
    const j = await post('/skills/delete', { name: confirmDel.name });
    if (j.ok) { setMsg(`已删除「${confirmDel.name}」`); setConfirmDel(null); refresh(); }
    else setMsg(j.reason || '删除失败');
    setBusy(false);
  };

  const skills: Skill[] = data?.skills || [];
  const kw = q.trim().toLowerCase();
  const shown = kw
    ? skills.filter((s) => s.name.toLowerCase().includes(kw) || (s.description || '').toLowerCase().includes(kw))
    : skills;

  return (
    <div className="flex flex-col gap-3">
      {/* 状态行 + 重新登记 */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xxs text-muted-foreground">
          {data
            ? (data.enabled
              ? (data.clean ? '✓ 全部校验通过' : '✗ 有不符/未登记项——已停用，重新登记后重启恢复')
              : '锁未启用')
            : '读取中…'}
        </span>
        <button
          type="button"
          disabled={busy}
          className="ml-auto flex shrink-0 items-center gap-1 rounded-[10px] border border-border px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground disabled:opacity-50"
          onClick={rehash}
        >
          <RefreshCw className="size-3.5" />重新登记
        </button>
      </div>

      {/* 搜索 + 新建 */}
      <div className="flex items-center gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-1.5 rounded-[10px] border border-border bg-card px-3 py-1.5 text-sm text-muted-foreground">
          <Search className="size-3.5" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜索技能名或描述…"
            className="w-full bg-transparent outline-none placeholder:text-muted-foreground"
          />
        </div>
        <button
          type="button"
          className="flex shrink-0 items-center gap-1 rounded-[10px] bg-gray-900 px-3 py-2 text-sm font-medium text-white dark:bg-white dark:text-black"
          onClick={() => { setMsg(''); setEditor({ mode: 'create', name: '', description: '', content: '' }); }}
        >
          <Plus className="size-3.5" />新建技能
        </button>
      </div>

      {/* 卡片列表 */}
      {shown.length === 0 && (
        <p className="text-sm text-muted-foreground">
          {skills.length ? '没有匹配的技能。' : '还没有技能——点「新建技能」加一个。'}
        </p>
      )}
      <div className="flex flex-col gap-3">
        {shown.map((s) => (
          <div key={s.name} className={cardClass + ' flex items-center gap-3 px-4 py-3'}>
            <div className="min-w-0 flex-1">
              <div className={rowTitleClass + ' truncate'}>{s.name}</div>
              <div className={rowDescClass + ' truncate'}>{s.description || '（无描述）'}</div>
            </div>
            <span className={badgeCls(s.status)} title={s.hash ? `哈希 ${s.hash}` : ''}>
              {s.status === '✓' ? '已登记' : s.status === '✗' ? '哈希不符' : '未登记'}
            </span>
            <button
              type="button"
              title={`编辑 ${s.name}`}
              className="shrink-0 rounded-[10px] p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={() => { setMsg(''); setEditor({ mode: 'edit', name: s.name, description: s.description || '', content: s.body || '' }); }}
            >
              <Pencil className="size-3.5" />
            </button>
            <button
              type="button"
              title={`删除 ${s.name}`}
              className="shrink-0 rounded-[10px] p-1.5 text-red-500 hover:bg-muted"
              onClick={() => { setMsg(''); setConfirmDel(s); }}
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
      </div>

      {msg && <p className="text-xxs text-muted-foreground">{msg}</p>}

      {/* 新建 / 编辑弹层 */}
      {editor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setEditor(null)}>
          <div
            className="flex max-h-[85vh] w-[560px] flex-col gap-3 overflow-y-auto rounded-[10px] border border-border bg-card p-5 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-medium text-foreground">{editor.mode === 'create' ? '新建技能' : '编辑技能'}</h3>
            <div>
              <label className="mb-1 block text-sm text-muted-foreground">技能名（目录名，只许小写字母/数字/-/_）</label>
              <input
                className={inputC}
                value={editor.name}
                readOnly={editor.mode === 'edit'}
                onChange={(e) => setEditor({ ...editor, name: e.target.value })}
                placeholder="如 flow-run-cmd"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-muted-foreground">一句话描述（米娅系统提示词里给她看的那句）</label>
              <input
                className={inputC}
                value={editor.description}
                onChange={(e) => setEditor({ ...editor, description: e.target.value })}
                placeholder="如 命令执行的规范与红线"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-muted-foreground">正文（SKILL.md 的 Markdown 内容）</label>
              <textarea
                className={inputC + ' h-56 resize-y font-mono'}
                value={editor.content}
                onChange={(e) => setEditor({ ...editor, content: e.target.value })}
                placeholder="写下这个技能的规则/步骤…"
              />
            </div>
            <p className="text-xxs text-muted-foreground">
              技能名与描述会自动写成 SKILL.md 的 frontmatter；保存后自动重登记技能锁，新哈希随响应返回。
            </p>
            <div className="flex justify-end gap-2">
              <button className="rounded-[10px] px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted" onClick={() => setEditor(null)}>取消</button>
              <button
                disabled={busy}
                className="rounded-[10px] bg-gray-900 px-4 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-white dark:text-black"
                onClick={submit}
              >
                {editor.mode === 'create' ? '创建' : '保存'}
              </button>
            </div>
            {msg && <p className="text-xxs text-red-500">{msg}</p>}
          </div>
        </div>
      )}

      {/* 删除二次确认 */}
      {confirmDel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setConfirmDel(null)}>
          <div className="w-[420px] rounded-[10px] border border-border bg-card p-5 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-medium text-foreground">删除技能「{confirmDel.name}」？</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              将删除该技能目录及其全部文件，并从技能锁基线重登记。此操作不可撤销。
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button className="rounded-[10px] px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted" onClick={() => setConfirmDel(null)}>取消</button>
              <button
                disabled={busy}
                className="rounded-[10px] bg-red-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
                onClick={remove}
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
