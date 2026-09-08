'use client';

/**
 * settings/tabs/InterfaceTab.tsx —— 界面（admin:interface，Experience）页（原 page.tsx L1067-1116 原样迁出）
 * 参考 open-webui 公开界面布局：任务模型 / 显示（界面字号 zoom）/ 对话（Context Compaction 六字段）。
 * R79⑧（评审D 假功能四件套）：Tool Permissions 零接线纯占位，退役；
 * R79⑧：旧压缩模型下拉退役（与「对话压缩」两级联动真源打架）；
 * R79⑧：Generation 区整段退役（标题生成/语音提示词全是零消费假开关）。
 */

import { useSettings } from '../context';
import { Section, Row, Switch, inputC } from '../ui';

export default function InterfaceTab() {
  const { val, set } = useSettings();
  return (
    <>
      <h2 className="mb-1 text-lg font-medium">界面</h2>
      <p className="mb-5 text-xs text-gray-500">任务与对话生成行为</p>
      <Section first title="任务">
        <Row label="任务模型" description="后台任务（标题生成等）的兜底模型，当前版本由组长模型兼任。">
          <select className={inputC + ' w-40'} disabled>
            <option>当前模型</option>
          </select>
        </Row>
      </Section>
      <Section first title="显示">
        <Row label="界面字号" description="整体缩放（html zoom）。100%=标准，110%≈浏览器缩放一档，改完保存即生效。管理员老花眼友好。">
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
        {/* R79⑧（评审D 假功能四件套）：Tool Permissions（future.interface.toolPerms）零接线纯占位，退役 */}
        {/* R79⑧：旧压缩模型下拉退役——它把 interface.compaction.model 写成"当前模型/平铺模型名"，
            与上方「对话压缩」区的服务商+模型两级联动（真源）打架，选了还容易把 provider 落空导致压缩回退 boss。
            压缩模型请到上方「对话压缩」区配置。 */}
        <Row label="Context Compaction" description="Summarize older chat history when the conversation context grows large.（官方 SummarizationMiddleware）">
          <Switch checked={!!val('interface.compaction.enabled', true)} onChange={(v) => set('interface.compaction.enabled', v)} />
        </Row>
        <div><label className="mb-1 block text-[0.6875rem] text-gray-500">Token Threshold</label>
          <input type="number" className={inputC} defaultValue={val('interface.compaction.threshold', 80000)} onChange={(e) => set('interface.compaction.threshold', +e.target.value)} />
          <p className="mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">Older messages are summarized when estimated context exceeds this token limit.</p></div>
        <div><label className="mb-1 block text-[0.6875rem] text-gray-500">Token Cap</label>
          <input type="number" className={inputC} defaultValue={val('interface.compaction.cap', 80000)} onChange={(e) => set('interface.compaction.cap', +e.target.value)} />
          <p className="mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">Model-specific context compaction thresholds cannot exceed this token limit.</p></div>
        <div><label className="mb-1 block text-[0.6875rem] text-gray-500">Retained Messages</label>
          <input type="number" className={inputC} defaultValue={val('interface.compaction.retained', 40)} onChange={(e) => set('interface.compaction.retained', +e.target.value)} />
          <p className="mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">Percentage of recent messages to keep after older messages are summarized.</p></div>
        <div><label className="mb-1 block text-[0.6875rem] text-gray-500">Context Compaction Prompt</label>
          <input className={inputC} placeholder="留空以使用默认提示词，或输入自定义提示词" defaultValue={val('interface.compaction.prompt')} onChange={(e) => set('interface.compaction.prompt', e.target.value)} />
          <p className="mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">Controls how older messages are rewritten into a running summary.</p></div>
        {/* R80（评审A ⑧ 半条）：压缩六字段区补"需重启"提示——压缩中间件启动时装配，改完不重启不生效 */}
        <p className="text-[0.6875rem] text-amber-600/80 dark:text-amber-500/80">保存后需重启容器生效（压缩中间件在启动时装配；此区与上方「对话压缩」的显示开关互不冲突）。</p>
      </Section>
    </>
  );
}
