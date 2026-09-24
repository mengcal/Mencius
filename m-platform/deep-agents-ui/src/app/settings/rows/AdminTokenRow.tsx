'use client';

/**
 * settings/rows/AdminTokenRow.tsx —— R75 管理员密钥（统一 token）面板
 * ------------------------------------------------------------------
 * 轮换/重置 + 忘记密钥用密码找回（R10.7）+ 修改密码（R10.8d，需旧密码验证）。
 * 密钥只存浏览器 HttpOnly Cookie + 后端守卫，米娅容器没有它 → 改不动设置/服务商/批准。
 * 对标 ZCode"锁在被锁者之外"。原 page.tsx L25-141 迁出。
 * R10.408（09-23 注册流程反转）：首设态的"粘贴激活码"死 UI 连根拔——未配置时
 * 全屏注册向导（SetupWizard）接管，本行不再重复建注册入口；密码找回补上
 * username（09-17 双要素上线后本入口漏送登录名=一直 400 的暗病，当场修）。
 */

import { useEffect, useState } from 'react';
import { tokenStatus, tokenRotate, tokenClear, clearAdminToken, authHeaders } from '@/lib/providerApi';
import { apiFetch } from '@/lib/apiBase';  // R10.5 XSS L2：统一带凭据的 fetch
import { Row, inputCImportant } from '../ui';
import { API, useSettings } from '../context';

export default function AdminTokenRow() {
  const { val } = useSettings();
  const [configured, setConfigured] = useState(false);
  const [justSet, setJustSet] = useState('');
  const [msg, setMsg] = useState('');
  const [recovering, setRecovering] = useState(false);  // R10.7 密码找回
  const [recPwd, setRecPwd] = useState('');
  const [chgOpen, setChgOpen] = useState(false);  // R10.8d 修改密码（需旧密码验证）
  const [chgOld, setChgOld] = useState('');
  const [chgNew, setChgNew] = useState('');
  const [chgNew2, setChgNew2] = useState('');
  const refresh = () => tokenStatus().then((s) => setConfigured(!!s.configured)).catch(() => {});
  useEffect(() => { refresh(); }, []);
  const gen = async () => {
    const r = await tokenRotate();
    if (r.ok && r.token) { clearAdminToken(); setJustSet(r.token); setMsg('已轮换：新钥匙已种入 HttpOnly Cookie（恶意脚本读不到），旧 Cookie 同时作废。页面即将自动刷新…'); refresh(); setTimeout(() => window.location.reload(), 1500); }
    else setMsg(r.error || '失败');
  };
  const recover = async () => {
    if (!recPwd) return setMsg('请输入管理员密码');
    try {
      const r = await apiFetch(`${API}/auth/login`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        // R10.408 修暗病：/auth/login 是双要素（登录名+密码），此前只送密码=永远"登录名或密码不正确"
        body: JSON.stringify({ username: String(val('general.admin_name', 'admin') || 'admin'), password: recPwd }),
      });
      const j = await r.json();
      if (j?.ok) { setRecovering(false); setRecPwd(''); setMsg('找回成功：已重新登录（Cookie 已种入）。'); refresh(); setTimeout(() => window.location.reload(), 1500); }
      else setMsg(j?.error || '找回失败');
    } catch { setMsg('无法连接后端'); }
  };
  const clear = async () => {
    // R10.5 事故（误触清除=锁外）教训保留：确认+说清后果；R10.408 后果改写——
    // 重置后回到全屏注册向导，用户名+密码重新注册即可（激活码机制已废除）。
    if (!window.confirm('重置会清除当前管理员密钥与密码（浏览器 Cookie 一并作废），平台回到注册向导，需要重新注册（用户名+密码）才能恢复管理权限。确定要重置吗？')) return;
    const r = await tokenClear();
    if (r.ok) { clearAdminToken(); setJustSet(''); setMsg('已重置，正在进入注册向导…'); refresh(); setTimeout(() => window.location.reload(), 1200); }
    else setMsg(r.error || '失败');
  };
  // R10.8d（爸爸："用户怎么修改密码"）：修改找回密码——需旧密码验证（防拿到 Cookie 的脚本换通道）
  const changePwd = async () => {
    if (chgNew.length < 8) return setMsg('新密码至少 8 位');
    if (chgNew !== chgNew2) return setMsg('两次输入的新密码不一致');
    try {
      const r = await apiFetch(`${API}/auth/set_password`, {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': "application/json" }),
        body: JSON.stringify({ password: chgNew, old_password: chgOld }),
      });
      const j = await r.json();
      if (j?.ok) { setChgOpen(false); setChgOld(''); setChgNew(''); setChgNew2(''); setMsg('✅ 密码已修改生效！'); }
      else setMsg('❌ ' + (j?.error || '修改失败'));
    } catch { setMsg('无法连接后端'); }
  };
  return (
    <Row label="管理员密钥" description={'改设置/服务商/批准/知识库写入需带此密钥；米娅容器没有它=改不动。' + (configured ? '当前：已启用（写端点强制校验）' : '当前：未配置（fail-closed：所有写端点一律 401）')}>
      <div className="flex flex-wrap items-center gap-2">
        {configured ? (
          <>
            {/* R10.11（NOVA 风格定稿）：全平台唯一主色=灰黑方形，indigo 只活在向导页；按钮 shadow 移除（行内无投影） */}
            <button type="button" className="rounded-[10px] bg-gray-900 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-gray-700 dark:bg-white dark:text-black dark:hover:bg-gray-200" onClick={() => gen()}>轮换密钥</button>
            <button type="button" className="text-sm text-red-500 underline-offset-2 hover:underline" onClick={clear}>重置（需重新注册）</button>
            {recovering ? (
              <span className="flex items-center gap-2">
                <input type="password" autoFocus value={recPwd} onChange={(e) => setRecPwd(e.target.value)}
                  placeholder="管理员密码" className={'w-52 ' + inputCImportant} />
                <button type="button" className="rounded-[10px] bg-gray-900 px-3 py-2 text-sm font-medium text-white dark:bg-white dark:text-black" onClick={recover}>登录</button>
              </span>
            ) : (
              <button type="button" className="text-sm text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-400" onClick={() => setRecovering(true)}>忘记密钥？用密码找回</button>
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
                  <button type="button" className="rounded-[10px] bg-gray-900 px-4 py-1.5 text-sm font-medium text-white dark:bg-white dark:text-black" onClick={changePwd}>确认修改</button>
                  <button type="button" className="text-sm text-muted-foreground" onClick={() => { setChgOpen(false); setChgOld(''); setChgNew(''); setChgNew2(''); }}>取消</button>
                </div>
              </div>
            ) : (
              <button type="button" className="text-sm text-indigo-600 underline-offset-2 hover:underline dark:text-indigo-400" onClick={() => setChgOpen(true)}>修改密码</button>
            )}
          </>
        ) : (
          <span className="text-sm text-muted-foreground">未配置——刷新页面即进入注册向导（设用户名+密码，谁先注册谁是主人）。</span>
        )}
        <span className="text-sm text-muted-foreground">{msg}</span>
      </div>
      {justSet && (
        <div className="mt-2 w-full rounded-[10px] border border-amber-300 bg-amber-50 p-2 font-mono text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
          新密钥（只显这一次，复制保存）：<b>{justSet}</b>
        </div>
      )}
    </Row>
  );
}
