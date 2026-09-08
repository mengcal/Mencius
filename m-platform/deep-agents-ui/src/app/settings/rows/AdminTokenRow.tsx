'use client';

/**
 * settings/rows/AdminTokenRow.tsx —— R75 管理员密钥（统一 token）面板
 * ------------------------------------------------------------------
 * 生成/轮换/清除 + 忘记密钥用密码找回（R10.7）+ 修改密码（R10.8d，需旧密码验证）。
 * 密钥只存浏览器 HttpOnly Cookie + 后端 secrets，助手容器没有它 → 改不动设置/服务商/批准。
 * 参考成熟 agent 平台"锁在被锁者之外"。原 page.tsx L25-141 原样迁出。
 */

import { useEffect, useState } from 'react';
import { tokenStatus, tokenRotate, tokenClear, clearAdminToken, authHeaders } from '@/lib/providerApi';
import { apiFetch } from '@/lib/apiBase';  // R10.5 XSS L2：统一带凭据的 fetch
import { Row, inputCImportant } from '../ui';
import { API } from '../context';

export default function AdminTokenRow() {
  const [configured, setConfigured] = useState(false);
  const [justSet, setJustSet] = useState('');
  const [msg, setMsg] = useState('');
  const [boot, setBoot] = useState('');  // R10.5 事故修复：首设态的激活码输入（后端 403 指路的宿主文件值）
  const [recovering, setRecovering] = useState(false);  // R10.7 密码找回
  const [recPwd, setRecPwd] = useState('');
  const [chgOpen, setChgOpen] = useState(false);  // R10.8d 修改密码（需旧密码验证）
  const [chgOld, setChgOld] = useState('');
  const [chgNew, setChgNew] = useState('');
  const [chgNew2, setChgNew2] = useState('');
  const refresh = () => tokenStatus().then((s) => setConfigured(!!s.configured)).catch(() => {});
  useEffect(() => { refresh(); }, []);
  const gen = async (bootstrapCode?: string) => {
    const r = await tokenRotate(undefined, bootstrapCode);
    if (r.ok && r.token) { clearAdminToken(); setJustSet(r.token); setMsg('已生成：钥匙已种入 HttpOnly Cookie（恶意脚本读不到），只显这一次，务必另行保存。页面即将自动刷新…'); setBoot(''); refresh(); setTimeout(() => window.location.reload(), 1500); }
    else setMsg(r.error || '失败');
  };
  const recover = async () => {
    if (!recPwd) return setMsg('请输入管理员密码');
    try {
      const r = await apiFetch(`${API}/auth/login`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ password: recPwd }),
      });
      const j = await r.json();
      if (j?.ok) { setRecovering(false); setRecPwd(''); setMsg('找回成功：已重新登录（Cookie 已种入）。'); refresh(); setTimeout(() => window.location.reload(), 1500); }
      else setMsg(j?.error || '找回失败');
    } catch { setMsg('无法连接后端'); }
  };
  const clear = async () => {
    // R10.5 事故：管理员想"轮换"时误触清除→首设态又无激活码输入=锁外。加确认+说清后果。
    if (!window.confirm('重置会清除当前管理员密钥（浏览器 Cookie 一并作废），之后必须用宿主激活码重新生成才能恢复管理权限。确定要重置吗？')) return;
    const r = await tokenClear();
    if (r.ok) { clearAdminToken(); setJustSet(''); setMsg('已重置。请从部署目录下 guard\.token_bootstrap 文件取激活码，粘贴到下方输入框重新生成。'); refresh(); }
    else setMsg(r.error || '失败');
  };
  // R10.8d（管理员："用户怎么修改密码"）：修改找回密码——需旧密码验证（防拿到 Cookie 的脚本换通道）
  const changePwd = async () => {
    if (chgNew.length < 8) return setMsg('新密码至少 8 位');
    if (chgNew !== chgNew2) return setMsg('两次输入的新密码不一致');
    try {
      const r = await apiFetch(`${API}/auth/set_password`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ password: chgNew, old_password: chgOld }),
      });
      const j = await r.json();
      if (j?.ok) { setChgOpen(false); setChgOld(''); setChgNew(''); setChgNew2(''); setMsg('✅ 密码已修改生效！'); }
      else setMsg('❌ ' + (j?.error || '修改失败'));
    } catch { setMsg('无法连接后端'); }
  };
  return (
    <Row label="管理员密钥" description={'改设置/服务商/批准/知识库写入需带此密钥；助手容器没有它=改不动。' + (configured ? '当前：已启用（写端点强制校验）' : '当前：未配置（fail-closed：所有写端点一律 401，必须先生成）')}>
      <div className="flex flex-wrap items-center gap-2">
        {configured ? (
          <>
            {/* R10.11（评审B 风格定稿）：全平台唯一主色=灰黑方形，indigo 只活在向导页；按钮 shadow 移除（行内无投影） */}
            <button type="button" className="rounded-lg bg-gray-900 px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-gray-700 dark:bg-white dark:text-black dark:hover:bg-gray-200" onClick={() => gen()}>轮换密钥</button>
            <button type="button" className="text-xs text-red-500 underline-offset-2 hover:underline" onClick={clear}>重置（需激活码恢复）</button>
            {recovering ? (
              <span className="flex items-center gap-2">
                <input type="password" autoFocus value={recPwd} onChange={(e) => setRecPwd(e.target.value)}
                  placeholder="管理员密码" className={'w-52 ' + inputCImportant} />
                <button type="button" className="rounded-lg bg-gray-900 px-3 py-2 text-xs font-medium text-white dark:bg-white dark:text-black" onClick={recover}>登录</button>
              </span>
            ) : (
              <button type="button" className="text-xs text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-400" onClick={() => setRecovering(true)}>忘记密钥？用密码找回</button>
            )}
            {chgOpen ? (
              <div className="w-full space-y-2">
                <input type="password" value={chgOld} onChange={(e) => setChgOld(e.target.value)} placeholder="旧密码（当前的管理员密码）"
                  className={'w-72 ' + inputCImportant} />
                <input type="password" value={chgNew} onChange={(e) => setChgNew(e.target.value)} placeholder="新密码（至少 8 位）"
                  className={'w-72 ' + inputCImportant} />
                <input type="password" value={chgNew2} onChange={(e) => setChgNew2(e.target.value)} placeholder="再输一遍新密码"
                  className={'w-72 ' + inputCImportant} />
                <div className="flex items-center gap-2">
                  <button type="button" className="rounded-lg bg-gray-900 px-4 py-1.5 text-xs font-medium text-white dark:bg-white dark:text-black" onClick={changePwd}>确认修改</button>
                  <button type="button" className="text-xs text-gray-500" onClick={() => { setChgOpen(false); setChgOld(''); setChgNew(''); setChgNew2(''); }}>取消</button>
                </div>
              </div>
            ) : (
              <button type="button" className="text-xs text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-400" onClick={() => setChgOpen(true)}>修改密码</button>
            )}
          </>
        ) : (
          <>
            <input
              type="password"
              value={boot}
              onChange={(e) => setBoot(e.target.value)}
              placeholder="粘贴宿主激活码（D:\m\guard\.token_bootstrap 文件内容）"
              className={'w-80 font-mono ' + inputCImportant}
            />
            <button type="button" disabled={!boot.trim()} className="rounded-lg bg-gray-900 px-4 py-2.5 text-xs font-medium text-white transition-colors hover:bg-gray-700 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-gray-200" onClick={() => gen(boot.trim())}>用激活码生成密钥</button>
          </>
        )}
        <span className="text-xs text-gray-500">{msg}</span>
      </div>
      {!configured && (
        <div className="mt-2 w-full rounded-lg border border-amber-400 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          <b>首设引导：尚未生成管理员密钥。</b>
          保存设置 / 服务商 / 批准 / 知识库写入现在会被全部拒绝（401，fail-closed——防止助手容器内的请求抢先把平台钥匙设成它的）。
          首设要验【激活码】：它只存在宿主电脑的 <b>D:\m\guard\.token_bootstrap</b> 文件里（打开复制全部内容粘贴到上面输入框）。
          能打开这个文件夹的只有管理员和作者，助手与沙箱进不去，所以拿得到激活码的才是管理员。生成后本浏览器自动保存（种入 HttpOnly Cookie），之后正常使用无需再填。
        </div>
      )}
      {justSet && (
        <div className="mt-2 w-full rounded-lg border border-amber-300 bg-amber-50 p-2 font-mono text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          新密钥（只显这一次，复制保存）：<b>{justSet}</b>
        </div>
      )}
    </Row>
  );
}
