/**
 * lib/confirmTiers.ts —— 确认分档四档的前端单一真源（r32 F18）
 * 此前 page.tsx 与 AdminGeneralTab.tsx 各抄一份 TIER_RANK/TIER_LABEL，
 * 加档改两处必漏一处（爸爸之恨第 0 条：同一默认值两处抄写=违规）。
 * 后端真源 = token_admin.py _TIER_RANK + settings_schema.py；改档位先改后端再对齐这里。
 */

export const CONFIRM_TIERS = [
  { v: "plan", rank: 0, label: "🛡 计划模式（只出计划）", plain: "计划模式" },
  { v: "strict", rank: 1, label: "🛡 变更前确认（都先问）", plain: "变更前确认" },
  { v: "auto_edit", rank: 2, label: "🛡 自动编辑（跑代码先问）", plain: "自动编辑" },
  { v: "full", rank: 3, label: "🛡 完全访问（全自动）", plain: "完全访问" },
] as const;

export const TIER_RANK: Record<string, number> = Object.fromEntries(
  CONFIRM_TIERS.map((t) => [t.v, t.rank])
);

export const TIER_LABEL: Record<string, string> = Object.fromEntries(
  CONFIRM_TIERS.map((t) => [t.v, t.plain])
);
