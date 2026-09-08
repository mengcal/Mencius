'use client';

/**
 * settings/tabs/AboutTab.tsx —— 「关于」页（原 page.tsx L679-691 原样迁出）
 * R80 二批：原 admin:db 页签（零控件纯展示）退役，PG/Redis 状态两行并入本页。
 */

import { Section, Row } from '../ui';

export default function AboutTab() {
  return (
    <>
      <h2 className="mb-1 text-lg font-medium">关于</h2>
      <p className="mb-5 text-xs text-gray-500">版本与运行环境（R10.11 头部排版统一）</p>
      <Section first>
        <Row label="版本" description="助手办公室 · deep-agents-ui + langgraph-api"><span className="text-xs">v1.0</span></Row>
        <Row label="设置文件" description="workspace/settings.json（打码）+ .settings_secrets（明文隔离，R79 起挪至宿主 D:\m\secrets 独立卷）" />
        <Row label="后端" description="langgraph-api 官方镜像 + deepagents 多模型蜂群" />
        {/* R80 二批：原 admin:db 页签（零控件纯展示）退役，状态两行并入关于 */}
        <Row label="PostgreSQL" description="checkpoint + store，容器名 postgres，库名 m"><span className="text-xs text-green-600 dark:text-green-500">官方组件</span></Row>
        <Row label="Redis" description="langgraph-api 队列"><span className="text-xs text-green-600 dark:text-green-500">官方组件</span></Row>
      </Section>
    </>
  );
}
