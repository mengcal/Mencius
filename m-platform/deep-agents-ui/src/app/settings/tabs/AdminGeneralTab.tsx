'use client';

/**
 * settings/tabs/AdminGeneralTab.tsx —— 管理（admin:general）页（原 page.tsx L694-738 原样迁出）
 * 功能占位 / 界面 / 助手与安全（确认分档四档门 + 管理员密钥 + 技能清单锁 + 压缩模型两级联动）。
 */

import { useSettings } from '../context';
import { Section, Row, Switch, inputC } from '../ui';
import AdminTokenRow from '../rows/AdminTokenRow';
import SkillsLockRow from '../rows/SkillsLockRow';

export default function AdminGeneralTab() {
  const { providers, val, set } = useSettings();
  return (
    <>
      <h2 className="mb-1 text-lg font-medium">管理</h2>
      <p className="mb-5 text-xs text-gray-500">管理员密钥、确认分档与压缩模型（平台级配置，R10.11 头部排版统一）</p>
      <Section first title="功能">
        <Row label="Community Sharing" description="Allow users to share chats with the community."><Switch checked={false} disabled /></Row>
        {/* R10.5（管理员）：「自动化任务」占位删除——助手的 start_async_task/工人岗后台派活本来就是
            自动化任务，这个 future 开关零后端消费，留着只会让人以为自动化还没开。 */}
        <Row label="用户状态" description="Show user status information in the app."><Switch checked={false} disabled /></Row>
      </Section>
      <Section title="界面">
        <Row label="Default Interface Settings" description="Set system-wide interface defaults for every account."><span className="text-xs text-gray-500">配置</span></Row>
      </Section>
      <Section title="助手与安全">
        <Row label="确认分档" description="四档动态确认门（即时生效，四档自由选择——设置即一切，政令必通）：计划模式=只出图纸不动手；变更前确认=每处改动先问；自动编辑=数据区写放行、执行/发信/删除/动编制先问；完全访问=不问（信任档）。写入由管理员密钥守卫（助手没有=改不动），未配置/非法时 fail-closed 按变更前确认处理。⚠️ 完全访问=信任态：后台自动汇报/注入面也随之全开（被注入的助手可自由派活）——选它即知情接受（R80 评审A 注记）">
          <select className={inputC + ' w-36'} defaultValue={val('general.confirmLevel', 'auto_edit')} onChange={(e) => set('general.confirmLevel', e.target.value)}>
            <option value="off">完全访问（全自动）</option>
            <option value="auto_edit">自动编辑（跑代码先问）</option>
            <option value="strict">变更前确认（都先问）</option>
            <option value="plan">计划模式（只出计划）</option>
          </select>
        </Row>
        <AdminTokenRow />
        <SkillsLockRow />
        <Row label="压缩模型" description="对话压缩（Summarization）用哪个【具体模型】（不是服务商）；留空=组长模型。选型要点：压缩要的是「读长文写摘要」，关思考、上下文窗口大即可，不必旗舰——魔搭 qwen3.8-flash（免费、无思考档）通常就够">
          {(() => {
            const prov = providers.find((p: any) => p.name === val('interface.compaction.provider', ''));
            return (
              <div className="flex flex-wrap gap-2">
                <select className={inputC + ' w-36'} defaultValue={val('interface.compaction.provider', '')}
                  onChange={(e) => { set('interface.compaction.provider', e.target.value); set('interface.compaction.model', ''); }}>
                  <option value="">（默认·组长模型）</option>
                  {providers.filter((p: any) => p.name).map((p: any) => <option key={p.name} value={p.name}>{p.name}</option>)}
                </select>
                <select key={String(val('interface.compaction.provider', ''))} className={inputC + ' w-52'} defaultValue={val('interface.compaction.model', '')}
                  onChange={(e) => set('interface.compaction.model', e.target.value)}>
                  <option value="">（该服务商默认/留空=组长）</option>
                  {((prov?.models_cache) || []).map((m: string) => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
            );
          })()}
        </Row>
      </Section>
    </>
  );
}
