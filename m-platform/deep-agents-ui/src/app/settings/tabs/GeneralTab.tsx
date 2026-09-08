'use client';

/**
 * settings/tabs/GeneralTab.tsx —— 通用（个人）页（原 page.tsx L606-676 原样迁出）
 * 系统提示词 / 高级参数（paramsOpen 折叠） / 对话压缩与权限。
 * R80（评审A ⑧ 半条）：人设/系统提示词区补"需重启"提示。
 * localStorage 键 'mia.showToolCalls' 原样保留。
 */

import { useEffect, useState } from 'react';
import { useSettings } from '../context';
import { Section, Row, Switch, inputC, autoGrow } from '../ui';

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
      <h2 className="mb-1 text-lg font-medium">通用</h2>
      <p className="mb-5 text-xs text-gray-500">助手人设、高级参数与对话显示偏好（R10.11 头部排版统一）</p>
      <Section first title="系统提示词">
        <textarea
          className={inputC}
          style={{ overflow: 'hidden' }}
          placeholder="助手人设卡…"
          defaultValue={val('general.system_prompt')}
          ref={autoGrow(112)}
          onChange={(e) => { set('general.system_prompt', e.target.value); const t = e.currentTarget; t.style.height = 'auto'; t.style.height = Math.max(t.scrollHeight, 112) + 'px'; }}
        />
        {/* R80（评审A ⑧ 半条）：人设/系统提示词区补"需重启"提示——工人岗矩阵区有、这里两轮漏了 */}
        <p className="mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">保存后需重启容器生效（助手启动时读取 system_prompt）。</p>
      </Section>
      <Section title="高级参数">
        <Row label="Model parameters" description="Show or hide custom generation parameters.（温度/max_tokens 已生效，其余参数存配置待接线）">
          <button className="text-xs text-gray-500 hover:text-gray-800 dark:hover:text-gray-200" onClick={() => setParamsOpen(!paramsOpen)}>
            {paramsOpen ? '关闭' : '显示'}
          </button>
        </Row>
        {paramsOpen && [
          ['stream', '流式对话响应 (Stream Chat Response)'],
          ['seed', '种子 (Seed)'],
          ['stop', '停止序列 (Stop Sequence)'],
          ['temperature', '温度 (Temperature)'],
          ['reasoning_effort', '推理力度 (Reasoning Effort)'],
          ['max_tokens', 'max_tokens'],
          ['top_k', 'top_k'],
          ['top_p', 'top_p'],
          ['min_p', 'min_p'],
          ['frequency_penalty', 'frequency_penalty'],
          ['presence_penalty', 'presence_penalty'],
        ].map(([k, label]) => (
          <Row key={k} label={label}>
            <input
              className={inputC + ' w-32 text-right'}
              placeholder="默认"
              defaultValue={val(`general.params.${k}`)}
              onChange={(e) => set(`general.params.${k}`, e.target.value)}
            />
          </Row>
        ))}
        {paramsOpen && <div className="pt-1 text-center text-xs text-gray-500">＋ 增加自定义参数（后续支持）</div>}
      </Section>
      <Section title="对话压缩">
        <Row label="Context Compaction" description="已归位：在 管理 → 界面 设置（对话压缩，官方 SummarizationMiddleware）">
          <span className="text-xs text-gray-500">见"界面"页</span>
        </Row>
        <Row label="显示工具调用" description="对话里显示工人岗干活的工具卡片（可折叠展开）。关闭后隐藏，界面更清爽">
          <Switch
            checked={showToolCalls}
            onChange={(v) => {
              setShowToolCalls(v);
              localStorage.setItem('mia.showToolCalls', String(v));
              flash('已切换，刷新对话页生效');
            }}
          />
        </Row>
        <Row label="允许助手管理工人岗" description="关闭后助手无法修改工人岗的模型/职业配置（只有管理员在设置页能改）">
          <Switch checked={!!val('permissions.miaManageAgents', true)} onChange={(v) => set('permissions.miaManageAgents', v)} />
        </Row>
      </Section>
    </>
  );
}
