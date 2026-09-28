/**
 * settings/nav.ts —— OWUI 设置页导航树 + 未实现占位行常量
 * ------------------------------------------------------------------
 * 组名与顺序照抄 open-webui SettingsModal（Personal/Basic、个人资料、Admin/系统、AI、Experience、Tools）。
 * 纯数据模块，不含组件；只被 page.tsx（侧栏渲染 + 占位页标题）消费。
 */

import {
  Settings, SlidersHorizontal, Info, Link2, Bot, LayoutList,
  ImageIcon, FileText, Globe,
} from 'lucide-react';  // R80 二批（hy3 审计+死导航组清理）：12 个零引用图标死 import 已清
import type { ElementType } from 'react';

export type Tab = { id: string; label: string; icon: ElementType; real?: boolean };
export type Group = { heading: string | null; tabs: Tab[] };

export const NAV: { section: string; groups: Group[] }[] = [
  {
    section: '个人',
    groups: [
      {
        heading: '基本',
        tabs: [
          { id: 'general', label: '通用', icon: Settings, real: true },
        ],
      },
      // R80 二批：Personal 区 Data 分组（数据/用量/已归档/个性化）系 R77 删渲染块后残留的死导航入口，整组摘除
    ],
  },
  {
    section: '个人资料',
    groups: [
      {
        heading: null,
        tabs: [
          { id: 'about', label: '关于', icon: Info, real: true },
        ],
      },
    ],
  },
  {
    section: '系统',
    groups: [
      {
        heading: '系统',
        tabs: [
          // R10.5（爸爸）：Personal 区已有"通用"（米娅的）——管理员的这页改名"管理"，不再重名
          { id: 'admin:general', label: '管理', icon: Settings, real: true },
        ],
      },
      {
        heading: '模型',
        tabs: [
          { id: 'admin:connections', label: '外部连接', icon: Link2, real: true },
          { id: 'admin:models', label: '模型', icon: Bot, real: true },
          { id: 'admin:subagents', label: '牛马矩阵', icon: LayoutList, real: true },
        ],
      },
      {
        heading: '体验',
        tabs: [
          { id: 'admin:interface', label: '界面', icon: SlidersHorizontal, real: true },
          { id: 'admin:images', label: '图片', icon: ImageIcon, real: true },
        ],
      },
      {
        heading: '工具',
        tabs: [
          { id: 'admin:documents', label: '文档', icon: FileText, real: true },
          { id: 'admin:web', label: '联网搜索', icon: Globe, real: true },
        ],
      },
      // R80 二批（hy3 审计）：admin:db「数据库」页签退役——零可编辑控件纯展示，
      // PG/Redis 状态两行并入 关于 页；Data 分组随之消失（Database 图标 import 同步清理）
    ],
  },
];

export const ALL_TABS = NAV.flatMap((s) => s.groups.flatMap((g) => g.tabs));

// 未实现功能的占位开关（存 future 节，作为路线图）
// r36w（CB P3）：FUTURE_ROWS 全表为永不渲染的死数据，整表退役（delete 行保留防引用断裂）。

