'use client';

/**
 * settings/rows/SkillsLockRow.tsx —— R10.3 skills_lock（评审A/评审B 方案落地）
 * ------------------------------------------------------------------
 * 技能清单哈希锁 UI：文件级状态展示 + 重新登记（rehash）。
 * 助手系统提示词里的技能 = 管理员给的（D:\m\skills），启动时逐文件对哈希，
 * 不符/未登记 = 停用整组（宁可不带技能不裸奔）。原 page.tsx L145-185 原样迁出。
 */

import { useEffect, useState } from 'react';
import { authHeaders } from '@/lib/providerApi';
import { apiFetch } from '@/lib/apiBase';
import { Row } from '../ui';
import { API } from '../context';

export default function SkillsLockRow() {
  const [data, setData] = useState<any>(null);
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const refresh = () => apiFetch(`${API}/skills/list`, { headers: authHeaders() })
    .then((r) => r.json()).then(setData).catch(() => setMsg('读取失败'));
  useEffect(() => { refresh(); }, []);
  const rehash = async () => {
    setBusy(true); setMsg('');
    try {
      const r = await apiFetch(`${API}/skills/rehash`, { method: 'POST', headers: authHeaders() });
      const j = await r.json();
      setMsg(j.ok ? `已重建（${j.count} 个文件）${j.note ? '；' + j.note : ''}` : (j.error || '失败'));
      refresh();
    } catch { setMsg('失败'); } finally { setBusy(false); }
  };
  return (
    <Row label="技能清单（skills_lock）" description="助手系统提示词里的技能 = 管理员给的（D:\m\skills），启动时逐文件对哈希，不符/未登记=停用整组（宁可不带技能不裸奔）。此锁防的是挂载改版回归（正常情况永远全绿）。宿主改完技能后点「重新登记」，若此前被停用需重启平台一次。">
      <div className="w-full">
        {data ? (
          <div className="mb-2 text-xs text-gray-500">
            状态：{data.enabled ? (data.clean ? '✓ 全部校验通过' : '✗ 有不符/未登记项——已停用，重新登记后重启恢复') : '锁未启用'}
            {data.files?.length > 0 && (
              <ul className="mt-1 space-y-0.5 font-mono">
                {data.files.map((f: any) => (
                  <li key={f.name}>{f.status} {f.name} {f.hash && <span className="text-gray-400">{f.hash}</span>}</li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <div className="mb-2 text-xs text-gray-400">读取中…</div>
        )}
        <div className="flex items-center gap-2">
          <button type="button" disabled={busy} className="rounded-lg bg-gray-900 px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-gray-700 disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-gray-200" onClick={rehash}>重新登记</button>
          <span className="text-xs text-gray-500">{msg}</span>
        </div>
      </div>
    </Row>
  );
}
