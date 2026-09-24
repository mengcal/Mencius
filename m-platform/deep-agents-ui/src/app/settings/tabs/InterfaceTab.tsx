'use client';

/**
 * settings/tabs/InterfaceTab.tsx —— 界面（admin:interface，Experience）页（原 page.tsx L1067-1116 原样迁出）
 * 任务模型（W5 改为可选）/ 显示（界面字号 zoom）/ 对话（Context Compaction 六字段）。
 * R79⑧（Lyra 假功能四件套）：Tool Permissions 零接线纯占位，退役；
 * R79⑧：旧压缩模型下拉退役（与「对话压缩」两级联动真源打架）；
 * R79⑧：Generation 区整段退役（标题生成/语音提示词全是零消费假开关）。
 * W5：任务模型从写死的「当前模型」改为可选（数据源 GET /models/all，值存 settings.task.model）；
 * W1/去 OWUI 化：字号归四档 token，英文描述改中文。
 */

import { useEffect, useState } from 'react';
import { useSettings } from '../context';
import { Section, Row, Switch, inputC, pageTitleClass, pageSubtitleClass } from '../ui';
import { getAllModels } from '@/lib/providerApi';

export default function InterfaceTab() {
  const { val, set } = useSettings();
  // W5：任务模型数据源=现成 GET /models/all（服务商模型列表，分组显示；不自己造本地模型）
  const [allModels, setAllModels] = useState<{ model: string; provider: string }[]>([]);
  useEffect(() => { getAllModels().then(setAllModels).catch(() => { /* 拉不到=只留「跟随主管模型」选项 */ }); }, []);
  const byProvider: Record<string, string[]> = {};
  allModels.forEach((m) => { (byProvider[m.provider] = byProvider[m.provider] || []).push(m.model); });

  return (
    <>
      <h2 className={pageTitleClass}>界面</h2>
      <p className={pageSubtitleClass}>任务与对话生成行为</p>
      <Section first title="任务">
        <Row label="任务模型" description="后台任务（标题生成等）用哪个模型；留空=跟随后台默认（现状：书记员模型，回退主管模型），与旧行为一致。设了却对不上模型列表时，后台任务会明确报错指向本页，不静默兜底。">
          <select className={inputC + ' w-64'} value={String(val('task.model', ''))} onChange={(e) => set('task.model', e.target.value)}>
            <option value="">（跟随后台默认）</option>
            {Object.entries(byProvider).map(([prov, ms]) => (
              <optgroup key={prov} label={`服务商模型 · ${prov}`}>
                {ms.map((m) => <option key={`${prov}/${m}`} value={m}>{m}</option>)}
              </optgroup>
            ))}
          </select>
        </Row>
      </Section>
      <Section title="显示">
        <Row label="界面字号" description="整体缩放（html zoom）。100%=标准，110%≈浏览器缩放一档，改完保存即生效。爸爸老花眼友好。">
          <select className={inputC + ' w-32'} value={String(val('interface.uiZoom', 110))}
            onChange={(e) => { const v = +e.target.value; set('interface.uiZoom', v); document.documentElement.style.zoom = String(v / 100); }}>
            <option value="100">100%（标准）</option>
            <option value="110">110%（大一号）</option>
            <option value="125">125%（很大）</option>
            <option value="150">150%（特大）</option>
          </select>
        </Row>
      </Section>
      <Section title="对话">
        {/* R79⑧（Lyra 假功能四件套）：Tool Permissions（future.interface.toolPerms）零接线纯占位，退役 */}
        {/* R79⑧：旧压缩模型下拉退役——它把 interface.compaction.model 写成"当前模型/平铺模型名"，
            与上方「对话压缩」区的服务商+模型两级联动（真源）打架，选了还容易把 provider 落空导致压缩回退 boss。
            压缩模型请到上方「对话压缩」区配置。 */}
        <Row label="对话压缩 (Context Compaction)" description="对话上下文变长时，把较早的历史消息压缩成摘要（官方 SummarizationMiddleware）。">
          <Switch checked={!!val('interface.compaction.enabled', true)} onChange={(v) => set('interface.compaction.enabled', v)} />
        </Row>
        <div><label className="mb-1 block text-sm text-foreground">触发阈值 (Token Threshold)</label>
          <input type="number" className={inputC} defaultValue={val('interface.compaction.threshold', 80000)} onChange={(e) => set('interface.compaction.threshold', +e.target.value)} />
          <p className="mt-1 text-xxs text-muted-foreground">估算上下文超过这个 token 数时，较早的消息会被压缩成摘要。</p></div>
        <div><label className="mb-1 block text-sm text-foreground">上限 (Token Cap)</label>
          <input type="number" className={inputC} defaultValue={val('interface.compaction.cap', 80000)} onChange={(e) => set('interface.compaction.cap', +e.target.value)} />
          <p className="mt-1 text-xxs text-muted-foreground">单个模型自定义的压缩阈值不能超过这个上限。</p></div>
        <div><label className="mb-1 block text-sm text-foreground">保留条数 (Retained Messages)</label>
          <input type="number" className={inputC} defaultValue={val('interface.compaction.retained', 40)} onChange={(e) => set('interface.compaction.retained', +e.target.value)} />
          <p className="mt-1 text-xxs text-muted-foreground">压缩较早消息后，保留最近多少条消息不去动。</p></div>
        <div><label className="mb-1 block text-sm text-foreground">压缩提示词 (Context Compaction Prompt)</label>
          <input className={inputC} placeholder="留空以使用默认提示词，或输入自定义提示词" defaultValue={val('interface.compaction.prompt')} onChange={(e) => set('interface.compaction.prompt', e.target.value)} />
          <p className="mt-1 text-xxs text-muted-foreground">控制较早消息被改写成滚动摘要的方式。</p></div>
        {/* R80（Cora ⑧ 半条）：压缩六字段区补"需重启"提示——压缩中间件启动时装配，改完不重启不生效 */}
        <p className="text-xxs text-amber-600/80 dark:text-amber-500/80">保存后需重启容器生效（压缩中间件在启动时装配；此区与上方「对话压缩」的显示开关互不冲突）。</p>
      </Section>
    </>
  );
}
