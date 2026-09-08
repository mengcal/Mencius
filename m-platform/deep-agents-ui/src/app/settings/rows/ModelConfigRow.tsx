'use client';

/**
 * settings/rows/ModelConfigRow.tsx —— 管理员·按模型单独设置
 * ------------------------------------------------------------------
 * 展开该模型的提示词/参数，存 model_overrides 节（留空=用全局）。
 * val/set 由调用方（tabs/ModelsTab）从 SettingsContext 取出后传入，本组件保持纯展示。
 * 原 page.tsx L346-392 原样迁出。
 */

import { useState } from 'react';
import { inputC, autoGrow } from '../ui';

export default function ModelConfigRow({ model, provider, val, set }: {
  model: string;
  provider: string;
  val: (path: string, dflt?: any) => any;
  set: (path: string, v: any) => void;
}) {
  const [open, setOpen] = useState(false);
  const hasOverride = ['system_prompt', 'temperature', 'top_p', 'max_tokens'].some(
    (k) => val(`model_overrides.${model}.${k}`) !== ''
  );
  return (
    <div className="rounded-lg border border-gray-100 dark:border-gray-900">
      <button className="flex w-full items-center justify-between px-3 py-2" onClick={() => setOpen(!open)}>
        <div className="flex items-center gap-2">
          <span className="text-xs">{model}</span>
          {hasOverride && (
            <span className="text-[0.5rem] text-blue-500 border border-blue-500/40 rounded px-1">已单独设置</span>
          )}
        </div>
        <span className="text-[0.625rem] text-gray-500">{open ? '收起 ▲' : '单独设置 ▼'}</span>
      </button>
      {open && (
        <div className="border-t border-gray-100 p-3 dark:border-gray-900">
          <label className="mb-1 block text-[0.6875rem] text-gray-500">系统提示词（留空用全局）</label>
          <textarea
            className={inputC}
            style={{ overflow: 'hidden' }}
            placeholder="该模型专属人设/指令…"
            defaultValue={val(`model_overrides.${model}.system_prompt`)}
            ref={autoGrow(80)}
            onChange={(e) => { set(`model_overrides.${model}.system_prompt`, e.target.value); const t = e.currentTarget; t.style.height = 'auto'; t.style.height = Math.max(t.scrollHeight, 80) + 'px'; }}
          />
          <div className="mt-2 flex gap-3">
            <div className="flex-1"><label className="mb-1 block text-[0.6875rem] text-gray-500">temperature</label>
              <input type="number" step="0.1" className={inputC} defaultValue={val(`model_overrides.${model}.temperature`)} onChange={(e) => set(`model_overrides.${model}.temperature`, e.target.value === '' ? '' : +e.target.value)} /></div>
            <div className="flex-1"><label className="mb-1 block text-[0.6875rem] text-gray-500">top_p</label>
              <input type="number" step="0.05" className={inputC} defaultValue={val(`model_overrides.${model}.top_p`)} onChange={(e) => set(`model_overrides.${model}.top_p`, e.target.value === '' ? '' : +e.target.value)} /></div>
            <div className="flex-1"><label className="mb-1 block text-[0.6875rem] text-gray-500">max_tokens</label>
              <input type="number" className={inputC} defaultValue={val(`model_overrides.${model}.max_tokens`)} onChange={(e) => set(`model_overrides.${model}.max_tokens`, e.target.value === '' ? '' : +e.target.value)} /></div>
          </div>
          <div className="mt-1 text-[0.625rem] text-gray-500">服务商：{provider} · 保存到 settings.json 的 model_overrides 节</div>
        </div>
      )}
    </div>
  );
}
