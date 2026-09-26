import { describe, it, expect } from 'vitest';
import { NAV, ALL_TABS, FUTURE_ROWS } from './nav';

/**
 * 工资单式断言演示：像核对工资单一样逐项核对常量结构——
 * 每条 expectations 是一行"应发项"，多一个少一个都过不了关。
 * （page.tsx 的模块级常量全部来自本 nav.ts：NAV / ALL_TABS / FUTURE_ROWS）
 */

describe('设置页导航树（src/app/settings/nav.ts · 工资单式核对）', () => {
  it('section 顺序照抄 OWUI：Personal → 个人资料 → Admin', () => {
    expect(NAV.map((s) => s.section)).toEqual(['Personal', '个人资料', 'Admin']);
  });

  it('Admin 区四个分组顺序：系统 / AI / Experience / Tools', () => {
    expect(NAV[2].groups.map((g) => g.heading)).toEqual(['系统', 'AI', 'Experience', 'Tools']);
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

  it('已转真实页的占位键已从 FUTURE_ROWS 摘除', () => {
    expect(FUTURE_ROWS['admin:documents']).toBeUndefined();
    expect(FUTURE_ROWS['admin:interface']).toBeUndefined();
  });

  it('FUTURE_ROWS 每项都是 [key, label] 二元组', () => {
    for (const [tab, rows] of Object.entries(FUTURE_ROWS)) {
      for (const row of rows) {
        expect(row, `${tab} 的占位行格式`).toHaveLength(2);
        expect(row[0]).toBeTruthy();
        expect(row[1]).toBeTruthy();
      }
    }
  });
});
