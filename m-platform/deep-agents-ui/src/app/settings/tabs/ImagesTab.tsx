'use client';

/**
 * settings/tabs/ImagesTab.tsx —— 图片（admin:images）页（原 page.tsx L1027-1057 原样迁出）
 * 对接本地 Stable Diffusion WebUI，画图任务由绘图工人岗走这个接口。
 */

import { useSettings } from '../context';
import { Section, Row, Switch, inputC, autoGrow } from '../ui';

export default function ImagesTab() {
  const { val, set } = useSettings();
  return (
    <>
      <h2 className="mb-1 text-lg font-medium">图片</h2>
      <p className="mb-5 text-xs text-gray-500">对接本地 Stable Diffusion WebUI，画图任务由绘图工人岗走这个接口</p>
      <Section first title="图像生成">
        <Row label="图像生成" description="Allow users to generate images from prompts.">
          <Switch checked={!!val('images.enabled', false)} onChange={(v) => set('images.enabled', v)} />
        </Row>
        <Row label="图像生成引擎">
          <select className={inputC + ' w-44'} defaultValue={val('images.engine', 'sd-webui')} onChange={(e) => set('images.engine', e.target.value)}>
            <option value="sd-webui">SD WebUI（本地）</option>
            <option value="default">默认 (OpenAI)</option>
          </select>
        </Row>
        <div><label className="mb-1 block text-[0.6875rem] text-gray-500">接口地址</label>
          <input className={inputC} placeholder="http://127.0.0.1:7860" defaultValue={val('images.sdUrl', '')} onChange={(e) => set('images.sdUrl', e.target.value)} />
          <p className="mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">SD WebUI 的地址，默认端口 7860；需要启动时加 --api 参数</p></div>
        <div><label className="mb-1 block text-[0.6875rem] text-gray-500">默认模型（checkpoint）</label>
          <input className={inputC} placeholder="留空用 SD 当前加载的模型" defaultValue={val('images.sdModel')} onChange={(e) => set('images.sdModel', e.target.value)} /></div>
        <div><label className="mb-1 block text-[0.6875rem] text-gray-500">额外参数（JSON）</label>
          <textarea className={inputC} style={{ overflow: 'hidden' }} placeholder="{}" defaultValue={val('images.extraParams')} ref={autoGrow(64)} onChange={(e) => { set('images.extraParams', e.target.value); const t = e.currentTarget; t.style.height = 'auto'; t.style.height = Math.max(t.scrollHeight, 64) + 'px'; }} />
          <p className="mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">Send extra JSON parameters with each image generation request.</p></div>
        <Row label="图像编辑" description="Allow users to edit existing images.">
          <div className="flex items-center gap-2">
            <span className="text-[0.625rem] text-yellow-600 dark:text-yellow-500 border border-yellow-600/40 rounded px-1.5 py-px">未实现</span>
            <Switch checked={!!val('future.images.edit', false)} onChange={(v) => set('future.images.edit', v)} />
          </div>
        </Row>
      </Section>
    </>
  );
}
