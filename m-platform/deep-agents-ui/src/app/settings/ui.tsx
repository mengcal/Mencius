'use client';

/**
 * settings/ui.tsx —— M 平台设置页样式基元（W1 排版规范唯一来源）
 * ------------------------------------------------------------------
 * 排版 token（全站只此一份，改这里=全站生效；禁止在页面里再写魔法字号/尺寸）：
 *
 *   字号四档（W1 规范：24 / 16 / 14 / 12，禁用 text-[0.68rem] 这类一次性字号）：
 *     pageTitleClass     页标题     24px / semibold
 *     pageSubtitleClass  页副标题   12px / muted
 *     sectionTitleClass  分组标题   16px / medium（上间距 32px 由 Section 的 mt-8 提供）
 *     rowTitleClass      行标题     14px / medium
 *     rowDescClass       行描述     12px / muted
 *   行距：label 与控件同行、描述在 label 下（见 Row）；行与行间距 16px（Section 的 gap-4）
 *   控件：输入框高 40px、圆角 10px；统一深色主题
 *         bg-card / border-border / text-foreground / placeholder text-muted-foreground
 *         —— 消灭 bg-white + 浅灰字组合；密钥类重要输入框 inputCImportant（白底深字）是唯一例外。
 *   卡片：cardClass = 圆角 10px + border-border + bg-card（技能卡/服务商卡/模型卡共用）
 *
 * 本文件只做纯展示，不碰数据流；数据读写一律走 ../context。
 */

import * as Tooltip from '@radix-ui/react-tooltip';
import { Info } from 'lucide-react';

/** ⓘ 悬停详情（09-23 爸爸令，Docker Desktop 同款交互）：
 *  行描述只留一句概要，长说明收进 ⓘ 气泡——界面简洁，信息不丢。
 *  规范依据（Red Hat/UXPin）：纯文本补充信息用 hover tooltip；
 *  200ms 延迟防误触，max-w 380px 保可读，深色 popover 色板。 */
export function InfoTip({ text }: { text: string }) {
  return (
    <Tooltip.Provider delayDuration={200}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>
          <button
            type="button"
            aria-label="查看详细说明"
            className="inline-flex h-4 w-4 shrink-0 cursor-help items-center justify-center rounded-full align-middle text-muted-foreground transition-colors hover:text-foreground"
          >
            <Info size={14} />
          </button>
        </Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side="top"
            sideOffset={6}
            className="z-50 max-w-[380px] rounded-[10px] border border-border bg-popover px-3 py-2 text-xs leading-relaxed text-popover-foreground shadow-md"
          >
            {text}
            <Tooltip.Arrow className="fill-popover" />
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

/** 页标题 24px / semibold（每个 tab 顶部 h2 用） */
export const pageTitleClass = 'text-2xl font-semibold text-foreground';
/** 页副标题 12px / muted（W6：页标题下的一句克制说明） */
export const pageSubtitleClass = 'mt-1 mb-6 text-xxs text-muted-foreground';
/** 分组标题 16px / medium（Section 标题用；上间距 32px 在外层 Section） */
export const sectionTitleClass = 'mb-3 text-base font-medium text-foreground';
/** 行标题 14px / medium（Row 的 label） */
export const rowTitleClass = 'text-sm font-medium text-foreground';
/** 行描述 12px / muted（Row 的 description，位于 label 下） */
export const rowDescClass = 'mt-1 text-xxs text-muted-foreground';
/** 通用卡片壳（技能卡/服务商卡/模型卡）：圆角 10px + 深色主题边框/底色 */
export const cardClass = 'rounded-[10px] border border-border bg-card';

/** 普通输入控件统一式：高 40px、圆角 10px、深色主题（bg-card 底 + text-foreground 字 + muted 占位）。
 *  用 min-h-10 而非 h-10——textarea 走 autoGrow 内联高度 / 显式 h-32 时不打架。 */
export const inputC = 'w-full min-h-10 rounded-[10px] border border-border bg-card px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-ring';

/** R10.8f 爸爸定纲（老花可读性）+R10.11（Eve/Cora 风格评审）收敛一式：密钥/密码类
 *  "重要输入框"专用——白底深字大号粗体。全站唯一例外（普通输入一律 inputC）；
 *  圆角同样收敛到 W1 的 10px，禁再造第四种圆角。 */
export const inputCImportant = 'w-full h-10 rounded-[10px] border-2 border-indigo-300 bg-white px-4 text-base font-medium text-gray-900 placeholder-gray-400';

/** JSON / 参数类输入框（W4）：深色主题同 inputC，但换等宽字体 + text-xs(13px)。
 *  单独成 token 是为了避免与 inputC 的 text-sm 打架（同属性两个 class 谁生效看 CSS 顺序）。 */
export const inputMonoClass = 'w-full rounded-[10px] border border-border bg-card px-3 py-2 font-mono text-xs text-foreground outline-none placeholder:text-muted-foreground focus:border-ring';

export const tabButtonClass = (active: boolean) =>
  `flex items-center gap-1.5 h-7 px-2 md:w-full shrink-0 rounded-[10px] text-sm text-left transition-colors duration-75 ${
    active
      ? 'font-medium text-foreground bg-black/[0.04] dark:bg-white/[0.06]'
      : 'text-muted-foreground hover:text-foreground'
  }`;

export const groupHeadingClass = (first: boolean) =>
  `hidden md:block shrink-0 text-xxs text-muted-foreground px-2 ${first ? 'mt-0.5' : 'mt-2'} mb-0.5`;

export function Switch({ checked, onChange, disabled }: { checked: boolean; onChange?: (v: boolean) => void; disabled?: boolean }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange?.(!checked)}
      className={`relative h-4 min-h-4 w-7 shrink-0 cursor-pointer rounded-full mx-[0.0625rem] transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? 'bg-gray-900 dark:bg-white' : 'bg-gray-300 dark:bg-gray-700'
      }`}
    >
      <span
        className={`pointer-events-none absolute top-[0.125rem] block h-3 w-3 shrink-0 rounded-full transition-all duration-150 ${
          checked ? 'left-[0.875rem] bg-white dark:bg-black' : 'left-[0.125rem] bg-white dark:bg-gray-500'
        }`}
      />
    </button>
  );
}

export function Row({ label, description, hint, children }: { label: string; description?: string; hint?: string; children?: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0 flex-1">
        <div className={rowTitleClass}>
          {label}
          {hint && <span className="ml-1.5"><InfoTip text={hint} /></span>}
        </div>
        {description && <p className={rowDescClass}>{description}</p>}
      </div>
      <div className="shrink-0 pt-0.5">{children}</div>
    </div>
  );
}

export function Section({ title, first, children }: { title?: string; first?: boolean; children?: React.ReactNode }) {
  return (
    <section className={first ? '' : 'mt-8'}>
      {title && <h3 className={sectionTitleClass}>{title}</h3>}
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  );
}

/** R65 铁律：提示词框不许定高出滚动条——一律 JS 随内容增高（minH=下限）。R66 抽公共版，主框/模型单设框/JSON框共用 */
export function autoGrow(minH: number) {
  return (el: HTMLTextAreaElement | null) => {
    if (!el) return;
    const grow = () => { el.style.height = 'auto'; el.style.height = Math.max(el.scrollHeight, minH) + 'px'; };
    grow(); requestAnimationFrame(grow); setTimeout(grow, 60);
  };
}
