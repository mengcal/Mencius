'use client';

/**
 * settings/tabs/ImagesTab.tsx —— 图片（admin:images）页（原 page.tsx L1027-1057 原样迁出）
 * 对接本地 Stable Diffusion WebUI，画图任务由绘图牛马走这个接口。
 * W1/去 OWUI 化：字号归四档 token，英文说明改中文。
 * r35（Qoder P1-7/P2-32）：images.enabled/engine/sdModel/extraParams 四个零后端消费的假控件
 *   连根拔（唯一消费者=tools.generate_image 读 images.sdUrl）；出图行为实际由确认档管住。
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
        <div><label className="mb-1 block text-sm text-foreground">接口地址</label>
          <input className={inputC} placeholder="http://host.docker.internal:7860" defaultValue={val('images.sdUrl', '')} onChange={(e) => set('images.sdUrl', e.target.value)} />
          <p className="mt-1 text-xxs text-muted-foreground">SD WebUI 的地址（此值由平台容器内消费，写 host.docker.internal 而非 127.0.0.1），默认端口 7860；SD 启动时需加 --api 参数</p></div>
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
