/**
 * settings/nav.ts —— 参考 open-webui 的设置页导航树 + 未实现占位行常量
 * ------------------------------------------------------------------
 * 组名与顺序参考 open-webui SettingsModal 公开设计（Personal/Basic、个人资料、Admin/系统、AI、Experience、Tools）。
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
    section: 'Personal',
    groups: [
      {
        heading: 'Basic',
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
    section: 'Admin',
    groups: [
      {
        heading: '系统',
        tabs: [
          // R10.5（管理员）：Personal 区已有"通用"（助手的）——管理员的这页改名"管理"，不再重名
          { id: 'admin:general', label: '管理', icon: Settings, real: true },
        ],
      },
      {
        heading: 'AI',
        tabs: [
          { id: 'admin:connections', label: '外部连接', icon: Link2, real: true },
          { id: 'admin:models', label: '模型', icon: Bot, real: true },
          { id: 'admin:subagents', label: '工人岗矩阵', icon: LayoutList, real: true },
        ],
      },
      {
        heading: 'Experience',
        tabs: [
          { id: 'admin:interface', label: '界面', icon: SlidersHorizontal, real: true },
          { id: 'admin:images', label: '图片', icon: ImageIcon, real: true },
        ],
      },
      {
        heading: 'Tools',
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
export const FUTURE_ROWS: Record<string, [string, string][]> = {
  interface: [
    ['darkMode', '深色/浅色主题切换'],
    ['fontSize', '界面字号缩放'],
  ],
  notifications: [['desktop', '桌面通知（任务完成时提醒）']],
  shortcuts: [['hotkeys', '自定义快捷键']],
  tools: [['toolServers', '外部工具服务器（MCP）']],
  audio: [['tts', '语音朗读回复（TTS）'], ['stt', '语音输入（STT）']],
  data: [['exportChats', '对话导出/备份']],
  usage: [['tokenUsage', 'Token 用量统计']],
  archived: [['archivedList', '已归档对话列表']],
  personalization: [['memory', '长期个性化记忆开关']],
  account: [['avatar', '头像与昵称']],
  'admin:auth': [['login', '登录认证（多人模式）']],
  'admin:interface': [['banners', '公告横幅']],
  'admin:audio': [['whisper', '语音服务配置']],
  'admin:evaluations': [['arena', '模型评价/竞技场']],
  'admin:analytics': [['dashboard', '使用分析面板']],
  'admin:integrations': [['functions', '函数/管道脚本']],
  'admin:documents': [['rag', '文档知识库（RAG）']],
  'admin:pipelines': [['pipelines', '工作流管道（对接 n8n）']],
};
delete FUTURE_ROWS['admin:documents']; // 已转真实页（RAG 知识库）
delete FUTURE_ROWS['admin:interface']; // 已改为真实页（Context Compaction 等），下方手动渲染
