'use client';

/**
 * settings/tabs/AdminGeneralTab.tsx —— 管理（admin:general）页（原 page.tsx L694-738 原样迁出）
 * 米娅与安全（确认分档四档门 + 管理员密钥 + 压缩模型两级联动 + 批准规则）+ 技能清单（W3 卡片式增删改）。
 * W2（r25 家规）：Community Sharing / 用户状态两个零后端空壳按钮连根拔除；
 *   同批清掉 "Default Interface Settings"（OWUI 英文残留 + 零功能行，"界面"页才是真设置处）。
 * W1：字号/控件统一走 ui.tsx 的四档 token。
 */

import React, { useState } from 'react';
import { useSettings } from '../context';
import { Section, Row, Switch, inputC, pageTitleClass, pageSubtitleClass } from '../ui';  // r32：inputCImportant 随密码框退役
import { API, apiFetch } from '@/lib/apiBase';
import AdminTokenRow from '../rows/AdminTokenRow';
import SkillsManager from '../rows/SkillsManager';

// r32：档位四档单一真源=lib/confirmTiers.ts（前端）；本文件原 TIER_RANK/TIER_LABEL
// 双抄已删。放宽密码门整段退役（r32 爸爸裁决），档位走专端点 /settings/confirm-level，
// 通用 /settings/general 的 confirmLevel 写路已在后端关闭（providers.py）。

function TierPicker() {
  const { val, reload } = useSettings();
  const [tier, setTier] = useState(String(val('general.confirmLevel', 'strict') || 'strict'));
  const [msg, setMsg] = useState('');

  // r32（爸爸裁决撤密码门）：四档直选，pending/pwd 密码流整段退役；
  // _rev 带上（NOVA F5 防撞车）；成功后 context.reload() 刷新 _rev——
  // 不刷新则第二次改档必假 409（NOVA P3#16）；conflict 出声并提示刷新。
  const apply = async (lv: string) => {
    try {
      const r = await apiFetch(`${API}/settings/confirm-level`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level: lv, _rev: Number(val('_rev') || 0) }),
      });
      const j = await r.json().catch(() => ({}));
      if (j?.ok) { setTier(j.confirmLevel); setMsg('✓ 已切换'); await reload(); }
      else if (j?.conflict) { setMsg(j?.error || '设置已被后台修改，请刷新页面'); await reload(); }
      else { if (j?.previous) setTier(j.previous); setMsg(j?.error || '切换失败'); }
    } catch { setMsg('无法连接后端'); }
  };
  const onPick = (lv: string) => { setMsg(''); apply(lv); };
  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <select className={inputC + ' w-36'} value={tier} onChange={(e) => onPick(e.target.value)}>
        <option value="full">完全访问（全自动；米娅 execute 同知夏落宿主 Git Bash，权限对等）</option>
        <option value="auto_edit">自动编辑（跑代码先问）</option>
        <option value="strict">变更前确认（都先问）</option>
        <option value="plan">计划模式（只出计划）</option>
      </select>
      {msg && <span className="text-xs text-muted-foreground">{msg}</span>}
    </div>
  );
}

export default function AdminGeneralTab() {
  const { providers, val, set } = useSettings();
  return (
    <>
      <h2 className={pageTitleClass}>管理</h2>
      <p className={pageSubtitleClass}>管理员密钥、确认分档、压缩模型与技能清单（平台级配置）</p>
      <Section first title="米娅与安全">
        <Row label="确认分档"
          description="四档动态确认门，即时生效；放宽/收紧自由直切（r32 爸爸裁决：个人平台不设管理员验证，等多用户版再考虑）。"
          hint="计划模式=只出图纸不动手；变更前确认=每处改动先问；自动编辑=数据区写放行、执行/发信/删除/动编制先问；完全访问=不问（信任档）。写入由管理员密钥守卫（米娅没有=改不动）。⚠️ 完全访问=信任态：后台自动汇报/注入面也随之全开（被注入的米娅可自由派活）——选它即知情接受（R80 Cora 注记）。档位变更全程落审计（confirm_level_change：旧→新+是否放宽+IP，写 office 侧账本；审计写不进=自动回滚，r30）。">
          <TierPicker />
        </Row>
        <Row label="管理员登录名" description="登录页第一个输入框校验的名字（与密码双要素；改完即生效，下次登录用新名字）。默认 admin">
          <input className={inputC + ' w-36'} defaultValue={val('general.admin_name', 'admin')}
            onBlur={(e) => {
              // r32（NOVA 常驻1 违规）：清空不再静默回落 'admin'（改完名字的爸爸失手清空
              // 就被自己改掉的名字挡在门外）——恢复原值并出声。
              const v = e.target.value.trim();
              if (!v) { e.target.value = String(val('general.admin_name', 'admin') || 'admin'); alert('登录名不能为空，已恢复原值'); return; }
              set('general.admin_name', v);
            }} />
        </Row>
        {/* 09-17 深夜 schema 收口：批⑤键补 UI（单一来源=settings_schema.py） */}
        <Row label="记忆抽取阈值" description="米娅回复累积多少字触发后台事实抽取（scribe.extractThreshold，默认 600）">
          <input className={inputC + ' w-24'} type="number" defaultValue={val('scribe.extractThreshold', 600)}
            onBlur={(e) => {
              // r32（NOVA 常驻1）：非法输入出声不静默回落——Number('')=0、负数/小数同理拦截
              const n = Number(e.target.value);
              if (!Number.isInteger(n) || n <= 0) { alert('阈值需为正整数'); e.target.value = String(val('scribe.extractThreshold', 600)); return; }
              set('scribe.extractThreshold', n);
            }} />
        </Row>
        <Row label="笔记老化天数" description="私人笔记超多少天没更新就巡检提醒归档（scribe.agingDays，默认 30）">
          <input className={inputC + ' w-24'} type="number" defaultValue={val('scribe.agingDays', 30)}
            onBlur={(e) => {
              const n = Number(e.target.value);
              if (!Number.isInteger(n) || n <= 0) { alert('天数需为正整数'); e.target.value = String(val('scribe.agingDays', 30)); return; }
              set('scribe.agingDays', n);
            }} />
        </Row>
        {/* 外部岗两键（领取超时/CodeBuddy 模型）09-17 深夜知夏拍板挪至牛马矩阵页（语义归属） */}
        <AdminTokenRow />
        <Row label="压缩模型"
          description="对话压缩（Summarization）用哪个具体模型（不是服务商）；留空=跟随主管模型。"
          hint="选型要点：压缩要的是「读长文写摘要」，关思考、上下文窗口大即可，不必旗舰——魔搭 qwen3.8-flash（免费、无思考档）通常就够。">
          {(() => {
            const prov = providers.find((p: any) => p.name === val('interface.compaction.provider', ''));
            return (
              <div className="flex flex-wrap gap-2">
                <select className={inputC + ' w-36'} defaultValue={val('interface.compaction.provider', '')}
                  onChange={(e) => { set('interface.compaction.provider', e.target.value); set('interface.compaction.model', ''); }}>
                  <option value="">（默认·主管模型）</option>
                  {providers.filter((p: any) => p.name).map((p: any) => <option key={p.name} value={p.name}>{p.name}</option>)}
                </select>
                <select key={String(val('interface.compaction.provider', ''))} className={inputC + ' w-52'} defaultValue={val('interface.compaction.model', '')}
                  onChange={(e) => set('interface.compaction.model', e.target.value)}>
                  <option value="">（该服务商默认/留空=主管）</option>
                  {((prov?.models_cache) || []).map((m: string) => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
            );
          })()}
        </Row>
        <RememberRulesCard />
      </Section>
      {/* W3：技能清单独立成区（卡片式 + 增删改），不再挤在「米娅与安全」行里 */}
      <Section title="技能清单">
        <SkillsManager />
      </Section>
    </>
  );
}

// ── r49 双钮"批准并记住这类"规则卡（可见可删——爸爸权柄，米娅无权）──
function RememberRulesCard() {
  const [rules, setRules] = useState<Array<{ key: string; tool: string; note?: string }>>([]);
  const [loadState, setLoadState] = useState<'loading' | 'ok' | 'error'>('loading');

  const load = React.useCallback(async () => {
    setLoadState('loading');
    try {
      const r = await apiFetch(`${API}/settings/remember-rules`);
      const d = await r.json();
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setRules(d.rules || []);
      setLoadState('ok');
    } catch {
      // r32（Eve P2-3/NOVA/Cora 三路同锤）：加载失败不再谎报"（暂无规则）"——
      // 失败与空列表同文案=静默兜底（爸爸之恨第 1 条），r30 修了 del() 漏了 load()。
      setLoadState('error');
    }
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const del = async (key: string) => {
    // r30 Cora#7：删除必须读响应——401/500 谎报"已删"刷新后规则复活（schtasks
    // 谎报案前端变体）。失败不动本地列表，如实弹回。
    try {
      const res = await apiFetch(`${API}/settings/remember-rules`, {
        method: 'DELETE', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key }),
      });
      const j = await res.json().catch(() => null);
      if (!j?.ok) { alert(`删除失败：${j?.error || `HTTP ${res.status}`}`); return; }
      setRules((prev) => prev.filter((r) => r.key !== key));
    } catch (e) {
      alert(`删除失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <Row label="批准规则（免卡清单）" description="批量卡上点「批准并记住」存下的精确规则：同工具+同目标以后免卡直接放行，每次命中都进批准账。删除即恢复弹卡。规则由管理员密钥守卫（米娅无权增删）。">
      <div className="flex flex-col gap-1">
        {loadState === 'error' && (
          <span className="text-sm text-red-600">
            规则加载失败——
            <button type="button" className="underline hover:no-underline" onClick={load}>点此重试</button>
          </span>
        )}
        {loadState === 'ok' && rules.length === 0 && <span className="text-sm text-muted-foreground">（暂无规则）</span>}
        {loadState === 'loading' && <span className="text-sm text-muted-foreground">加载中…</span>}
        {rules.map((r) => (
          <div key={r.key} className="flex items-center gap-2">
            <code className="rounded bg-muted px-1.5 py-0.5 text-xxs">{r.key}</code>
            {r.note && <span className="text-xxs text-muted-foreground">{r.note}</span>}
            <button className="text-xxs text-red-600 hover:underline" onClick={() => del(r.key)}>删除</button>
          </div>
        ))}
      </div>
    </Row>
  );
}
