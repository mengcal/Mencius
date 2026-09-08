'use client';

/**
 * 助手办公室 · 设置页（管理面板交互参考 open-webui 设计，2026-08-28 作者）—— 壳
 * ------------------------------------------------------------------
 * 结构/样式参考 open-webui SettingsModal + AdminSettingRow/Switch 公开类名体系（未复制源码）：
 *   - 左侧分组导航（Personal/Basic、个人资料、Admin/系统、AI、Experience、Tools）
 *   - 右下角悬浮"保存"按钮
 * 数据全部走后端 /settings API（office.py settings_mgr）。
 *
 * 拆分说明（原 1238 行 → 壳 + 模块）：
 *   ui.tsx（Switch/Row/Section/autoGrow 基元）
 *   nav.ts（NAV 导航树 + FUTURE_ROWS 常量）
 *   context.tsx（S/draft/val/set/save/flash/providers 数据流）
 *   rows/（AdminTokenRow、SkillsLockRow、ModelConfigRow）
 *   tabs/（About/General/AdminGeneral/Connections/Models/Subagents/Web/Images/Interface/Documents）
 * 本文件只保留：tab 状态 + 侧栏渲染 + tab 分发 + 未实现占位页 + 保存钮。
 */

import { useState } from 'react';
import { ChevronLeft, Search } from 'lucide-react';
import { SettingsProvider, useSettings } from './context';
import { NAV, ALL_TABS, FUTURE_ROWS } from './nav';
import type { Tab } from './nav';
import { Section, Row, Switch, tabButtonClass, groupHeadingClass } from './ui';
import AboutTab from './tabs/AboutTab';
import GeneralTab from './tabs/GeneralTab';
import AdminGeneralTab from './tabs/AdminGeneralTab';
import ConnectionsTab from './tabs/ConnectionsTab';
import ModelsTab from './tabs/ModelsTab';
import SubagentsTab from './tabs/SubagentsTab';
import WebTab from './tabs/WebTab';
import ImagesTab from './tabs/ImagesTab';
import InterfaceTab from './tabs/InterfaceTab';
import DocumentsTab from './tabs/DocumentsTab';

/** 未实现功能的占位开关页（存 future 节，作为路线图）。原 page.tsx futureTab() 函数。 */
function FutureTab({ id }: { id: string }) {
  const { val, set } = useSettings();
  return (
    <Section first>
      {(FUTURE_ROWS[id] || [['todo', '该功能尚未实现']]).map(([k, label]) => (
        <Row key={k} label={label} description="功能尚未实现，开关状态已保存，作为后续路线图">
          <div className="flex items-center gap-2">
            <span className="text-[0.625rem] text-yellow-600 dark:text-yellow-500 border border-yellow-600/40 dark:border-yellow-500/40 rounded px-1.5 py-px">未实现</span>
            <Switch checked={!!val(`future.${id}.${k}`, false)} onChange={(v) => set(`future.${id}.${k}`, v)} />
          </div>
        </Row>
      ))}
    </Section>
  );
}

function SettingsShell() {
  const { msg, save } = useSettings();
  const [tab, setTab] = useState('general');
  const [search, setSearch] = useState('');

  const keyword = search.trim().toLowerCase();
  const visibleTab = (t: Tab) => !keyword || t.label.toLowerCase().includes(keyword) || t.id.toLowerCase().includes(keyword);

  return (
    <div className="fixed inset-0 flex bg-gray-50 dark:bg-gray-950 text-gray-800 dark:text-gray-200">
      {/* ── 左侧导航（参考 open-webui）── */}
      <aside className="flex w-[240px] shrink-0 flex-col border-r border-gray-100 dark:border-gray-900">
        <button onClick={() => (window.location.href = '/')} className="flex items-center gap-1 px-4 pt-4 pb-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200">
          <ChevronLeft className="size-4" /> 返回
        </button>
        <div className="px-4 pb-2">
          <div className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 bg-gray-100 dark:bg-gray-900 text-xs text-gray-500 dark:text-gray-400">
            <Search className="size-3.5" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索" className="w-full bg-transparent outline-none" />
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto p-1 pl-2 md:pl-1">
          {NAV.map((sec) => {
            const groups = sec.groups
              .map((g) => ({ ...g, tabs: g.tabs.filter(visibleTab) }))
              .filter((g) => g.tabs.length);
            if (!groups.length) return null;
            let first = true;
            return (
              <div key={sec.section}>
                <span className="text-[0.625rem] text-gray-400 dark:text-gray-600 px-2 mt-1.5 mb-0.5 block">{sec.section}</span>
                {groups.map((g) => (
                  <div key={g.heading}>
                    {g.heading && <span className={groupHeadingClass(first)}>{g.heading}</span>}
                    {g.tabs.map((t) => {
                      const Icon = t.icon;
                      return (
                        <button key={t.id} role="tab" aria-selected={tab === t.id} className={tabButtonClass(tab === t.id)} onClick={() => setTab(t.id)}>
                          <Icon className="size-3.5" strokeWidth={2} />
                          <span>{t.label}</span>
                          {!t.real && <span className="ml-auto text-[0.5rem] text-yellow-600 dark:text-yellow-600">未实现</span>}
                        </button>
                      );
                    })}
                    {first = false}
                  </div>
                ))}
              </div>
            );
          })}
        </nav>
      </aside>

      {/* ── 右侧内容区 ── */}
      <main className="relative flex-1 overflow-y-auto bg-white dark:bg-gray-950 border-l border-gray-100 dark:border-gray-900">
        <div className="mx-auto max-w-2xl px-8 py-8">
          {tab === 'general' && <GeneralTab />}
          {tab === 'about' && <AboutTab />}
          {tab === 'admin:general' && <AdminGeneralTab />}
          {tab === 'admin:connections' && <ConnectionsTab />}
          {tab === 'admin:models' && <ModelsTab />}
          {tab === 'admin:subagents' && <SubagentsTab />}
          {tab === 'admin:web' && <WebTab />}
          {tab === 'admin:images' && <ImagesTab />}
          {tab === 'admin:interface' && <InterfaceTab />}
          {tab === 'admin:documents' && <DocumentsTab />}

          {/* ── 未实现占位页 ── */}
          {FUTURE_ROWS[tab] && tab !== 'general' && (
            <>
              <h2 className="mb-1 text-lg font-medium">{ALL_TABS.find((t) => t.id === tab)?.label}</h2>
              <p className="mb-5 text-xs text-gray-500">规划中 · 打开的开关会存入配置作为路线图</p>
              <FutureTab id={tab} />
            </>
          )}
        </div>

        {/* ── 悬浮保存按钮（参考 open-webui）── */}
        <div className="sticky bottom-0 pointer-events-none flex justify-end">
          <button onClick={save} className="pointer-events-auto mr-6 mb-4 rounded-full bg-gray-900 dark:bg-white px-4 py-2 text-xs font-medium text-white dark:text-black shadow-lg hover:opacity-90">
            {msg || '保存'}
          </button>
        </div>
      </main>
    </div>
  );
}

export default function SettingsPage() {
  return (
    <SettingsProvider>
      <SettingsShell />
    </SettingsProvider>
  );
}
