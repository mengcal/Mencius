'use client';

/**
 * settings/tabs/WebTab.tsx —— 联网搜索（admin:web）页（原 page.tsx L976-1024 原样迁出）
 * 搜索开关 / 引擎路由 / SearXNG / 搜索限制 / 引擎密钥。
 * R10.5（爸爸）：「Web Search Confirmation」占位删除——搜索是只读动作，确认门四档已管住变更类行为。
 * W1/去 OWUI 化：字号归四档 token，英文标题/说明改中文。
 */

import { useSettings } from '../context';
import { Section, Row, Switch, inputC, pageTitleClass, pageSubtitleClass } from '../ui';

export default function WebTab() {
  const { val, set } = useSettings();
  return (
    <>
      <h2 className={pageTitleClass}>联网搜索</h2>
      <p className={pageSubtitleClass}>对话联网开关、搜索引擎路由与引擎密钥</p>
      <Section first title="搜索">
        <Row label="联网搜索" description="允许在对话中搜索互联网。">
          <Switch checked={!!val('search.enabled', true)} onChange={(v) => set('search.enabled', v)} />
        </Row>
        <Row label="默认搜索引擎" description="米娅默认走智能路由：中文秘塔→博查，英文 Tavily。手动指定后固定用该引擎。">
          <select className={inputC + ' w-40'} defaultValue={val('search.engine', 'auto')} onChange={(e) => set('search.engine', e.target.value)}>
            <option value="auto">auto（智能路由）</option>
            <option value="metaso">秘塔 metaso</option>
            <option value="bocha">博查 bocha</option>
            <option value="tavily">tavily</option>
            <option value="searxng">searxng</option>
          </select>
        </Row>
      </Section>
      <Section title="SearXNG">
        <div><label className="mb-1 block text-sm text-foreground">Searxng 查询接口地址</label>
          <input className={inputC} defaultValue={val('search.searxngUrl', '')} placeholder="留空=后端默认 http://searxng:8080/search" onChange={(e) => set('search.searxngUrl', e.target.value)} /></div>
        <div><label className="mb-1 block text-sm text-foreground">Searxng 搜索语言（例如：all, en, es, de, fr 等）</label>
          <input className={inputC} defaultValue={val('search.searxngLang', 'all')} onChange={(e) => set('search.searxngLang', e.target.value)} /></div>
      </Section>
      {/* 09-17 深夜 schema 收口：公网引擎端点可配（留空=后端默认表；只许 https，非法值后端轻闸门回落） */}
      <Section title="公网搜索引擎端点">
        {([['search.bochaUrl', '博查 Bocha', 'https://api.bochaai.com/v1/web-search'],
           ['search.tavilyUrl', 'Tavily', 'https://api.tavily.com/search'],
           ['search.metasoUrl', '秘塔 Metaso', 'https://metaso.cn/api/mcp'],
           ['search.bingUrl', 'Bing', 'https://www.bing.com/search']] as const).map(([k, label, dflt]) => (
          <div key={k}><label className="mb-1 block text-sm text-foreground">{label} 端点</label>
            <input className={inputC} defaultValue={val(k, '')} placeholder={'留空=默认 ' + dflt} onChange={(e) => set(k, e.target.value)} /></div>
        ))}
      </Section>
      <Section title="搜索限制">
        <div className="flex gap-3">
          <div className="flex-1"><label className="mb-1 block text-sm text-foreground">搜索结果数量</label>
            <input type="number" className={inputC} defaultValue={val('search.resultCount', 5)} onChange={(e) => set('search.resultCount', +e.target.value)} /></div>
          <div className="flex-1"><label className="mb-1 block text-sm text-foreground">并发请求</label>
            <input type="number" className={inputC} defaultValue={val('search.concurrency', 3)} onChange={(e) => set('search.concurrency', +e.target.value)} /></div>
        </div>
        <p className="text-xxs text-muted-foreground">控制返回结果数量与并发请求数。</p>
        <div><label className="mb-1 block text-sm text-foreground">URL 抓取内容长度上限</label>
          <input type="number" className={inputC} defaultValue={val('search.fetchMaxLength', 8000)} onChange={(e) => set('search.fetchMaxLength', +e.target.value)} />
          <p className="mt-1 text-xxs text-muted-foreground">从 URL 抓取内容时返回的最大字符数。留空表示不限制。</p></div>
        <div><label className="mb-1 block text-sm text-foreground">域名过滤列表</label>
          <input className={inputC} placeholder="输入域名，多个域名用逗号分隔（例如：example.com,site.org,!excludedsite.com）" defaultValue={val('search.domainFilter')} onChange={(e) => set('search.domainFilter', e.target.value)} /></div>
      </Section>
      <Section title="引擎密钥">
        <div><label className="mb-1 block text-sm text-foreground">秘塔 metasoKey（中文主力，每天 100 积分）</label>
          <input type="password" className={inputC} placeholder={val('search.metasoKey') || '未设置'} onChange={(e) => set('search.metasoKey', e.target.value)} /></div>
        <div><label className="mb-1 block text-sm text-foreground">博查 bochaKey（中文备选）</label>
          <input type="password" className={inputC} placeholder={val('search.bochaKey') || '未设置'} onChange={(e) => set('search.bochaKey', e.target.value)} /></div>
        <div><label className="mb-1 block text-sm text-foreground">Tavily Key（英文）</label>
          <input type="password" className={inputC} placeholder={val('search.tavilyKey') || '未设置'} onChange={(e) => set('search.tavilyKey', e.target.value)} /></div>
      </Section>
    </>
  );
}
