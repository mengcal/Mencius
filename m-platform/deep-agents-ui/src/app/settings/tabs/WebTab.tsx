'use client';

/**
 * settings/tabs/WebTab.tsx —— 联网搜索（admin:web）页（原 page.tsx L976-1024 原样迁出）
 * 搜索开关 / 引擎路由 / SearXNG / 搜索限制 / 引擎密钥。
 * R10.5（爸爸）：「Web Search Confirmation」占位删除——搜索是只读动作，确认门四档已管住变更类行为。
 * r35（Qoder P1-7/P2-31）：search.enabled/concurrency/fetchMaxLength/domainFilter 四个零后端消费的
 *   假控件连根拔（按钮必须有真实支撑，爸爸 r25 原则）；search.bingUrl 随 bing 死链族退役。
 * W1/去 OWUI 化：字号归四档 token，英文标题/说明改中文。
 */

import { useSettings } from '../context';
import { Section, Row, inputC, pageTitleClass, pageSubtitleClass } from '../ui';  // r35（Cora 联动3）：Switch 随四个假控件退役后为死 import，拔

export default function WebTab() {
  const { val, set } = useSettings();
  return (
    <>
      <h2 className={pageTitleClass}>联网搜索</h2>
      <p className={pageSubtitleClass}>搜索引擎路由、结果数与引擎密钥（联网搜索已默认常开，无需开关）</p>
      <Section first title="搜索">
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
          <input className={inputC} defaultValue={val('search.searxngUrl', '')} placeholder="留空=用平台自带的本地搜索服务（已配好，一般不用改）" onChange={(e) => set('search.searxngUrl', e.target.value)} /></div>
        <div><label className="mb-1 block text-sm text-foreground">Searxng 搜索语言（例如：all, en, es, de, fr 等）</label>
          <input className={inputC} defaultValue={val('search.searxngLang', 'all')} onChange={(e) => set('search.searxngLang', e.target.value)} /></div>
      </Section>
      {/* 09-17 深夜 schema 收口：公网引擎端点可配（留空=后端默认表；只许 https，非法值后端轻闸门回落） */}
      <Section title="公网搜索引擎端点">
        {([['search.bochaUrl', '博查 Bocha', 'https://api.bochaai.com/v1/web-search'],
           ['search.tavilyUrl', 'Tavily', 'https://api.tavily.com/search'],
           ['search.metasoUrl', '秘塔 Metaso', 'https://metaso.cn/api/mcp']] as const).map(([k, label, dflt]) => (
          <div key={k}><label className="mb-1 block text-sm text-foreground">{label} 端点</label>
            <input className={inputC} defaultValue={val(k, '')} placeholder={'留空=默认 ' + dflt} onChange={(e) => set(k, e.target.value)} /></div>
        ))}
      </Section>
      <Section title="搜索限制">
        <div className="flex gap-3">
          <div className="flex-1"><label className="mb-1 block text-sm text-foreground">搜索结果数量</label>
            <input type="number" className={inputC} defaultValue={val('search.resultCount', 5)} onChange={(e) => set('search.resultCount', +e.target.value)} /></div>
        </div>
        <p className="text-xxs text-muted-foreground">控制每次搜索返回的结果条数。</p>
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
