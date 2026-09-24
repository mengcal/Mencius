'use client';

/**
 * settings/tabs/ImagesTab.tsx —— 图片（admin:images）页（原 page.tsx L1027-1057 原样迁出）
 * 对接本地 Stable Diffusion WebUI，画图任务由绘图牛马走这个接口。
 * W1/去 OWUI 化：字号归四档 token，英文说明改中文。
 */

import { useSettings } from '../context';
import { Section, Row, Switch, inputC, inputMonoClass, autoGrow, pageTitleClass, pageSubtitleClass } from '../ui';

export default function ImagesTab() {
  const { val, set } = useSettings();
  return (
    <>
      <h2 className={pageTitleClass}>图片</h2>
      <p className={pageSubtitleClass}>对接本地 Stable Diffusion WebUI，画图任务由绘图牛马走这个接口</p>
      <Section first title="图像生成">
        <Row label="图像生成" description="允许在对话里按提示词生成图片。">
          <Switch checked={!!val('images.enabled', false)} onChange={(v) => set('images.enabled', v)} />
        </Row>
        <Row label="图像生成引擎">
          <select className={inputC + ' w-44'} defaultValue={val('images.engine', 'sd-webui')} onChange={(e) => set('images.engine', e.target.value)}>
            <option value="sd-webui">SD WebUI（本地）</option>
            <option value="default">默认 (OpenAI)</option>
          </select>
        </Row>
        <div><label className="mb-1 block text-sm text-foreground">接口地址</label>
          <input className={inputC} placeholder="http://host.docker.internal:7860" defaultValue={val('images.sdUrl', '')} onChange={(e) => set('images.sdUrl', e.target.value)} />
          <p className="mt-1 text-xxs text-muted-foreground">SD WebUI 的地址（此值由平台容器内消费，写 host.docker.internal 而非 127.0.0.1），默认端口 7860；SD 启动时需加 --api 参数</p></div>
        <div><label className="mb-1 block text-sm text-foreground">默认模型（checkpoint）</label>
          <input className={inputC} placeholder="留空用 SD 当前加载的模型" defaultValue={val('images.sdModel')} onChange={(e) => set('images.sdModel', e.target.value)} /></div>
        <div><label className="mb-1 block text-sm text-foreground">额外参数（JSON）</label>
          <textarea className={inputMonoClass + ' resize-y'} style={{ overflow: 'hidden' }} placeholder="{}" defaultValue={val('images.extraParams')} ref={autoGrow(64)} onChange={(e) => { set('images.extraParams', e.target.value); const t = e.currentTarget; t.style.height = 'auto'; t.style.height = Math.max(t.scrollHeight, 64) + 'px'; }} />
          <p className="mt-1 text-xxs text-muted-foreground">每次图像生成请求附带的自定义 JSON 参数。</p></div>
        <Row label="图像编辑" description="允许对已有图片进行编辑。">
          <div className="flex items-center gap-2">
            <span className="text-xxs text-yellow-600 dark:text-yellow-500 border border-yellow-600/40 rounded px-1.5 py-px">未实现</span>
            <Switch checked={!!val('future.images.edit', false)} onChange={(v) => set('future.images.edit', v)} />
          </div>
        </Row>
      </Section>
    </>
  );
}
