'use client';

/**
 * settings/tabs/GeneralTab.tsx —— 通用（个人）页（原 page.tsx L606-676 原样迁出）
 * 系统提示词 / 高级参数（paramsOpen 折叠） / 对话压缩与权限。
 * R80（Cora ⑧ 半条）：人设/系统提示词区补"需重启"提示。
 * localStorage 键 'mia.showToolCalls' 原样保留。
 */

import { useEffect, useState } from 'react';
import { useSettings } from '../context';
import { Section, Row, Switch, inputC, autoGrow, pageTitleClass, pageSubtitleClass } from '../ui';

export default function GeneralTab() {
  const { val, set, flash } = useSettings();
  // localStorage 只能在客户端 useEffect 读，避免 SSR 水合不一致报错
  const [showToolCalls, setShowToolCalls] = useState(true);
  useEffect(() => {
    setShowToolCalls(localStorage.getItem('mia.showToolCalls') !== 'false');
  }, []);
  const [paramsOpen, setParamsOpen] = useState(true);
  return (
    <>
      <h2 className={pageTitleClass}>通用</h2>
      <p className={pageSubtitleClass}>米娅人设、高级参数与对话显示偏好</p>
      <Section first title="系统提示词">
        <textarea
          className={inputC}
          style={{ overflow: 'hidden' }}
          placeholder="米娅人设卡…"
          defaultValue={val('general.system_prompt')}
          ref={autoGrow(112)}
          onChange={(e) => { set('general.system_prompt', e.target.value); const t = e.currentTarget; t.style.height = 'auto'; t.style.height = Math.max(t.scrollHeight, 112) + 'px'; }}
        />
        {/* R80（Cora ⑧ 半条）：人设/系统提示词区补"需重启"提示——牛马矩阵区有、这里两轮漏了 */}
        <p className="mt-1 text-xxs text-muted-foreground">保存后需重启容器生效（米娅启动时读取 system_prompt）。</p>
      </Section>
      <Section title="高级参数">
        <Row label="模型参数" description="米娅主脑的生成参数——显示的数字即生效值（未填按官方推荐默认）。其余采样参数（top_p/seed 等）官方无接线需求，不摆假控件">
          <button className="text-sm text-muted-foreground hover:text-foreground" onClick={() => setParamsOpen(!paramsOpen)}>
            {paramsOpen ? '关闭' : '显示'}
          </button>
        </Row>
        {paramsOpen && [
          ['temperature', '温度', '1.0（千问思考模式官方推荐）'],
          ['max_tokens', '最大输出 tokens', '16384（模型上限 131072）'],
        ].map(([k, label, dflt]) => (
          <Row key={k} label={label}>
            <input
              className={inputC + ' w-40 text-right'}
              placeholder={dflt}
              defaultValue={val(`general.params.${k}`)}
              onChange={(e) => set(`general.params.${k}`, e.target.value)}
            />
          </Row>
        ))}
      </Section>
      <Section title="对话压缩">
        <Row label="Context Compaction" description="已归位：在 管理 → 界面 设置（对话压缩，官方 SummarizationMiddleware）">
          <span className="text-sm text-muted-foreground">见「界面」页</span>
        </Row>
        <Row label="显示工具调用" description="对话里显示牛马干活的工具卡片（可折叠展开）。关闭后隐藏，界面更清爽">
          <Switch
            checked={showToolCalls}
            onChange={(v) => {
              setShowToolCalls(v);
              localStorage.setItem('mia.showToolCalls', String(v));
              flash('已切换，刷新对话页生效');
            }}
          />
        </Row>
        <Row label="允许米娅管理邮箱" description="关闭后米娅无法再收发/管理全家邮箱——工具会明确拒绝并告知原因。">
          <Switch checked={!!val('permissions.miaManageEmail', true)} onChange={(v) => set('permissions.miaManageEmail', v)} />
        </Row>
        <Row label="允许米娅管理牛马" description="关闭后米娅无法修改牛马的模型/职业配置（只有爸爸在设置页能改）">
          <Switch checked={!!val('permissions.miaManageAgents', true)} onChange={(v) => set('permissions.miaManageAgents', v)} />
        </Row>
      </Section>
    </>
  );
}
