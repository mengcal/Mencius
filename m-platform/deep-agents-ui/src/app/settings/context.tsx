'use client';

/**
 * settings/context.tsx —— 设置页共享数据流（SettingsContext）
 * ------------------------------------------------------------------
 * 职责：加载 settings.json（S）+ 草稿（draftRef）+ 按路径读写（val/set）
 *       + 按节收集保存（save）+ 3 秒提示条（flash）+ 派生数据（providers/agents/modelsByProvider）。
 * R67：嵌入模型唯一真源=配置页，加载/保存后即时注入 ragClient（setEmbedModel）。
 * 所有 tabs/rows 只依赖本文件 + ../ui，禁止互相 import（规避循环依赖）。
 */

import { createContext, useContext, useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode, MutableRefObject } from 'react';
import { postSettings, getSettings, authHeaders } from '@/lib/providerApi';
import { API as _API, apiFetch as _apiFetch } from '@/lib/apiBase';
import { setEmbedModel } from '@/lib/ragClient';

/** 后端基址（R10.11 千问 P1-2：改走 @/lib/apiBase 的同源 /lg 基址——旧值 127.0.0.1:2024 直连是跨源，
 *  SameSite=Strict Cookie 不携带 → 密钥管理/技能锁/知识库重建三项 401，恢复通道自断。
 *  历史注记：拆分时从原 page.tsx 逐字保留的常量，/lg 改造轮漏了这里。） */
export { API } from '@/lib/apiBase';

type SettingsCtx = {
  /** settings.json 全量（后端 /settings API 返回） */
  S: any;
  /** 未保存草稿（按点分路径暂存，保存时按节收集） */
  draftRef: MutableRefObject<any>;
  /** 右下角保存钮上的 3 秒提示文案 */
  msg: string;
  flash: (t: string) => void;
  reload: () => Promise<void>;
  /** 读路径值：草稿优先，回退 S，再回退默认值 */
  val: (path: string, dflt?: any) => any;
  /** 写草稿（不落盘，等保存钮统一提交） */
  set: (path: string, v: any) => void;
  /** 按节收集草稿一次全部提交 */
  save: () => Promise<void>;
  providers: any[];
  agents: Record<string, any>;
  /** 各服务商的模型列表（settings 里已有，直接派生，不额外请求） */
  modelsByProvider: Record<string, string[]>;
};

const SettingsContext = createContext<SettingsCtx | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [S, setS] = useState<any>({});
  const [msg, setMsg] = useState('');
  const draftRef = useRef<any>({});
  // 09-17 深夜 schema 收口：配置总表（后端 settings_schema.py 经 GET /settings/schema 下发）
  // 作为默认值唯一来源——前端各输入框 val(key, 字面量) 的字面量退为 schema 未达时的最后兜底。
  const schemaRef = useRef<Record<string, any>>({});

  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(''), 3000); };

  const reload = useCallback(async () => {
    try {
      const s = await getSettings();
      setS(s);
      setEmbedModel((s?.rag?.embeddingModel || ''));  // R67：嵌入模型唯一真源=配置页，加载/保存后即时注入 ragClient
      try {
        const sc = await _apiFetch(`${_API}/settings/schema`, { headers: authHeaders() });
        if (sc.ok) {
          const j = await sc.json();
          const m: Record<string, any> = {};
          for (const [k, v] of Object.entries(j as any)) m[k] = (v as any).default;
          schemaRef.current = m;
        }
      } catch { /* schema 拉不到=退回各输入框自带兜底，不崩 */ }
      draftRef.current = {};
    } catch {
      // 后端未启动或不可达：空配置展示，不让页面崩
      setS({});
      flash('无法连接后端，请确认平台服务正在运行');
    }
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const val = (path: string, dflt: any = '') => {
    const p = draftRef.current[path] !== undefined ? draftRef.current[path]
      : path.split('.').reduce((o: any, k) => (o ?? {})[k], S);
    return p ?? schemaRef.current[path] ?? dflt;
  };
  const set = (path: string, v: any) => { draftRef.current[path] = v; flash('未保存'); };

  const save = async () => {
    // 按节收集草稿，一次全部提交（请求封装见 src/lib/providerApi.ts）
    const bySection: Record<string, any> = {};
    Object.entries(draftRef.current).forEach(([k, v]) => {
      const [section, ...rest] = k.split('.');
      let o = bySection[section] = bySection[section] || {};
      rest.forEach((kk, i) => { if (i === rest.length - 1) o[kk] = v; else { o[kk] = o[kk] || {}; o = o[kk]; } });
    });
    if (bySection.external && Object.keys(bySection.external).length === 0) bySection.external.providers = S.external?.providers || [];
    // r32 F1：全部 tab 的主保存链注入 _rev（防撞车全覆盖）。
    // r32c F1 修正（CB/Qoder 双 P0）：rev 不许循环外取一次——第 1 节落盘 mtime 即变，
    // 第 2 节起必 409 且 reload 抹草稿=静默丢数据。改：后端成功帧回吐新 rev，逐节续版；
    // 失败/冲突节如实报节名且**不 reload**（保住未保存草稿），全成才清草稿刷新。
    let rev = Number((S as any)?._rev || 0);
    const failed: string[] = [];
    let conflict = false;
    for (const [section, body] of Object.entries(bySection)) {
      const j = await postSettings(section, { ...body, _rev: rev });
      if ((j as any)?.conflict) { conflict = true; failed.push(section); continue; }
      if (!(j as any)?.ok) { failed.push(section); continue; }
      rev = Number((j as any).rev ?? rev);
    }
    if (conflict) flash('设置已被后台修改，请刷新页面后重新进入再保存（未保存：' + failed.join('、') + '）');
    else if (failed.length) flash('以下改动未保存：' + failed.join('、') + '——请重试或刷新页面');
    else { flash('已保存 ✓'); await reload(); }
  };

  const providers: any[] = Array.isArray(S.external?.providers) ? S.external.providers : [];
  const agents = S.agents || {};
  // 各服务商的模型列表（settings 里已有，直接派生，不额外请求）
  const modelsByProvider: Record<string, string[]> = {};
  providers.forEach((p: any) => { modelsByProvider[p.name] = p.models_cache || []; });

  return (
    <SettingsContext.Provider value={{ S, draftRef, msg, flash, reload, val, set, save, providers, agents, modelsByProvider }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings(): SettingsCtx {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('useSettings 必须在 <SettingsProvider> 内使用（settings/page.tsx 已包）');
  return ctx;
}
