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
import { postSettings, getSettings } from '@/lib/providerApi';
import { setEmbedModel } from '@/lib/ragClient';

/** 后端基址（R10.11 评审E P1-2：改走 @/lib/apiBase 的同源 /lg 基址——旧值 127.0.0.1:2024 直连是跨源，
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

  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(''), 3000); };

  const reload = useCallback(async () => {
    try {
      const s = await getSettings();
      setS(s);
      setEmbedModel((s?.rag?.embeddingModel || ''));  // R67：嵌入模型唯一真源=配置页，加载/保存后即时注入 ragClient
      draftRef.current = {};
    } catch {
      // 后端未启动或不可达：空配置展示，不让页面崩
      setS({});
      flash('无法连接后端 (2024 端口)，请确认 workplatform 容器在跑');
    }
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const val = (path: string, dflt: any = '') => {
    const p = draftRef.current[path] !== undefined ? draftRef.current[path]
      : path.split('.').reduce((o: any, k) => (o ?? {})[k], S);
    return p ?? dflt;
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
    let ok = true;
    for (const [section, body] of Object.entries(bySection)) {
      const j = await postSettings(section, body);
      ok = ok && j.ok;
    }
    flash(ok ? '已保存 ✓' : '保存失败');
    if (ok) await reload();
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
