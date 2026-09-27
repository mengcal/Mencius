'use client';

/**
 * settings/tabs/AboutTab.tsx —— 「关于」页（原 page.tsx L679-691 原样迁出）
 * R80 二批：原 admin:db 页签（零控件纯展示）退役，PG/Redis 状态两行并入本页。
 * W1：页标题/副标题走 ui.tsx 四档 token。
 */

import { Section, Row, pageTitleClass, pageSubtitleClass } from '../ui';

export default function AboutTab() {
  return (
    <>
      <h2 className={pageTitleClass}>关于</h2>
      <p className={pageSubtitleClass}>版本与运行环境</p>
      <Section first>
        <Row label="版本" description="米娅办公室 · deep-agents-ui + langgraph-api"><span className="text-sm">v1.0</span></Row>
        <Row label="设置文件" description="平台设置与密钥分两处存放：设置页所见为打码视图，真实密钥隔离在独立存储卷，永不进代码与仓库" />
        <Row label="后端" description="langgraph-api 官方镜像 + deepagents 多模型蜂群" />
        {/* R80 二批：原 admin:db 页签（零控件纯展示）退役，状态两行并入关于 */}
        <Row label="PostgreSQL" description="对话存档与检索库（官方组件）"><span className="text-sm text-green-600 dark:text-green-500">官方组件</span></Row>
        <Row label="Redis" description="langgraph-api 队列"><span className="text-sm text-green-600 dark:text-green-500">官方组件</span></Row>
      </Section>
    </>
  );
}
