'use client';

/**
 * settings/ui.tsx —— 样式基元（类名风格参考 open-webui，归属见 NOTICE）
 * ------------------------------------------------------------------
 * Switch / Row / Section 基元组件 + inputC / tabButtonClass / groupHeadingClass
 * 类名常量 + autoGrow 文本域自增高工具（R65/R66 抽公共版）。
 * 本文件只做纯展示，不碰数据流；数据读写一律走 ../context。
 */

export const inputC =  'w-full bg-gray-100 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg px-3 py-1.5 text-xs text-gray-800 dark:text-gray-200 outline-none focus:border-gray-500';

/** R10.8f 管理员定纲（老花可读性）+R10.11（评审C/评审A 风格评审）收敛一式：密钥/密码/激活码类
 *  "重要输入框"专用——白底深字大号粗体。全站唯一例外（普通输入一律 inputC）；
 *  新重要输入框必须用本常量，禁止再造第四种圆角（评审B：rounded-full/xl/lg 三混已清账）。 */
export const inputCImportant = 'w-full rounded-lg border-2 border-indigo-300 bg-white px-4 py-2.5 text-base font-medium text-gray-900 placeholder-gray-400';

export const tabButtonClass = (active: boolean) =>
  `flex items-center gap-1.5 h-7 px-2 md:w-full shrink-0 rounded-lg text-xs text-left transition-colors duration-75 ${
    active
      ? 'font-medium text-gray-900 dark:text-white bg-gray-50 dark:bg-white/[0.04]'
      : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
  }`;

export const groupHeadingClass = (first: boolean) =>
  `hidden md:block shrink-0 text-[0.625rem] text-gray-400 dark:text-gray-600 px-2 ${first ? 'mt-0.5' : 'mt-2'} mb-0.5`;

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

export function Row({ label, description, children }: { label: string; description?: string; children?: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0 text-xs text-gray-600 dark:text-gray-400">{label}</div>
        <div className="shrink-0">{children}</div>
      </div>
      {description && <p className="-mt-1 text-[0.6875rem] text-gray-400 dark:text-gray-600">{description}</p>}
    </div>
  );
}

export function Section({ title, first, children }: { title?: string; first?: boolean; children?: React.ReactNode }) {
  return (
    <section className={first ? '' : 'mt-5'}>
      {title && <h3 className="mb-2 text-xs text-gray-400 dark:text-gray-600">{title}</h3>}
      <div className="flex flex-col gap-2.5">{children}</div>
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
