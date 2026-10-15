import { describe, it, expect } from 'vitest';
import { CONFIRM_TIERS, TIER_RANK, TIER_LABEL } from './confirmTiers';

/**
 * confirmTiers.test.ts —— 四档单一真源的结构不变式（r32 F18 落地的守护测试）
 * 后端真源 = token_admin.py _TIER_RANK + settings_schema.py；本文件守护前端单源自身的一致性：
 * rank 单调、四档齐全、标签非空。加档时此测试先红，提醒同步后端。
 */
describe('confirmTiers 前端单一真源', () => {
  it('四档齐全且顺序正确', () => {
    expect(CONFIRM_TIERS.map((t) => t.v)).toEqual(['plan', 'strict', 'auto_edit', 'full']);
  });

  it('rank 严格单调递增（档位可比性的根基）', () => {
    const ranks = CONFIRM_TIERS.map((t) => t.rank);
    for (let i = 1; i < ranks.length; i++) {
      expect(ranks[i]).toBeGreaterThan(ranks[i - 1]);
    }
  });

  it('TIER_RANK/TIER_LABEL 与 CONFIRM_TIERS 一一对应（无双源回潮）', () => {
    for (const t of CONFIRM_TIERS) {
      expect(TIER_RANK[t.v]).toBe(t.rank);
      expect(TIER_LABEL[t.v]).toBe(t.plain);
    }
    expect(Object.keys(TIER_RANK)).toHaveLength(4);
  });

  it('标签全部非空（爸爸可见文案不许空白）', () => {
    for (const t of CONFIRM_TIERS) {
      expect(t.label.trim().length).toBeGreaterThan(0);
      expect(t.plain.trim().length).toBeGreaterThan(0);
    }
  });
});
