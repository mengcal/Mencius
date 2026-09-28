import { describe, it, expect } from 'vitest';
import { NAV, ALL_TABS } from './nav';

/**
 * 工资单式断言演示：像核对工资单一样逐项核对常量结构——
 * 每条 expectations 是一行"应发项"，多一个少一个都过不了关。
 * （page.tsx 的模块级常量全部来自本 nav.ts：NAV / ALL_TABS / FUTURE_ROWS）
 */

describe('设置页导航树（src/app/settings/nav.ts · 工资单式核对）', () => {
  it('section 顺序（r36r 中文化后）：个人 → 个人资料 → 系统', () => {
    expect(NAV.map((s) => s.section)).toEqual(['个人', '个人资料', '系统']);
  });

  it('系统区四个分组顺序：系统 / 模型 / 体验 / 工具', () => {
    expect(NAV[2].groups.map((g) => g.heading)).toEqual(['系统', '模型', '体验', '工具']);
  });

  it('所有 tab id 无重复', () => {
    const ids = ALL_TABS.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('每个 tab 都有 label 和 icon（渲染不炸的最低保证）', () => {
    for (const t of ALL_TABS) {
      expect(t.label, `tab ${t.id} 缺 label`).toBeTruthy();
      expect(t.icon, `tab ${t.id} 缺 icon`).toBeTruthy();
    }
  });

  it('真实页清单：R80 收口后恰好 10 个 real 页，id 逐项核对', () => {
    expect(ALL_TABS.filter((t) => t.real).map((t) => t.id)).toEqual([
      'general',
      'about',
      'admin:general',
      'admin:connections',
      'admin:models',
      'admin:subagents',
      'admin:interface',
      'admin:images',
      'admin:documents',
      'admin:web',
    ]);
  });


});
