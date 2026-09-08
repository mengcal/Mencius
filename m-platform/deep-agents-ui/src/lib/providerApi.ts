'use client';

/**
 * 服务商管理 API 客户端（2026-08-29 作者）
 * 全部请求发往本平台自己的后端固定地址（NEXT_PUBLIC_LANGGRAPH_URL），
 * 不存在用户可控的目标 URL；服务商地址只作为业务数据放进请求体，
 * 由后端（office.py）做协议校验后转发拉取模型列表。
 */
import { API, apiFetch } from './apiBase';

// R10.5 XSS L2：管理员钥匙的新家=HttpOnly Cookie（JS 读不到，OWASP 建议+LibreChat 模式）。
// localStorage 仅作旧页面过渡兼容读取——生成/轮换密钥后即清空，不再写入。
const TOKEN_KEY = 'mia_admin_token';
export function getAdminToken(): string {
  try { return localStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; }
}
export function clearAdminToken() {
  try { localStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
}
export function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const t = getAdminToken();
  const h: Record<string, string> = { ...extra };
  if (t) h['Authorization'] = `Bearer ${t}`;
  return h;
}

export function postProviderAction(action: string, payload: Record<string, unknown>) {
  return apiFetch(`${API}/providers/${action}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  })
    .then((r) => r.json())
    .catch(() => ({ error: '无法连接后端 (2024 端口)，请确认 workplatform 容器在跑' }));
}

/** 保存设置节（section 来自本页固定白名单，非用户可控）。r25：X-By 常数头作废，真钥匙=管理员 token（Bearer/Cookie） */
export function postSettings(section: string, body: Record<string, unknown>) {
  return apiFetch(`${API}/settings/${section}`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
  })
    .then((r) => r.json())
    .catch(() => ({ ok: false, error: '无法连接后端 (2024 端口)' }));
}

// R75 token 管理端点
export function tokenStatus(): Promise<{ configured: boolean }> {
  return apiFetch(`${API}/settings/token/status`).then((r) => r.json()).catch(() => ({ configured: false }));
}
export function tokenRotate(newToken?: string, bootstrapCode?: string): Promise<{ ok?: boolean; token?: string; error?: string }> {
  return apiFetch(`${API}/settings/token`, {
    method: 'POST',
    // R10.5 事故修复：首设（未配置态）必须带 X-Bootstrap 激活码（宿主 .token_bootstrap 文件里的值）——
    // 此前前端没有激活码输入框，管理员清钥后 4 连 403（审计实锤），UI 断层当场爆发。
    headers: authHeaders({
      'Content-Type': 'application/json',
      ...(bootstrapCode ? { 'X-Bootstrap': bootstrapCode } : {}),
    }),
    body: JSON.stringify({ token: newToken || '' }),
  }).then((r) => r.json()).catch(() => ({ error: '无法连接后端' }));
}
export function tokenClear(): Promise<{ ok?: boolean; error?: string }> {
  return apiFetch(`${API}/settings/token`, {
    method: 'DELETE',
    headers: authHeaders(),
  }).then((r) => r.json()).catch(() => ({ error: '无法连接后端' }));
}

/** 读取全量设置（打码版）。R80 续：读面收口后 GET /settings 也带 Bearer（浏览器=管理员有钥匙） */
export function getSettings() {
  return apiFetch(`${API}/settings`, { headers: authHeaders() }).then((r) => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  });
}

/** 所有启用服务商的模型合集（带服务商标识，同名模型各服务商各一条） */
export function getAllModels(): Promise<{ model: string; provider: string }[]> {
  return apiFetch(`${API}/models/all`, { headers: authHeaders() })
    .then((r) => r.json())
    .then((j) =>
      (j.providers || []).flatMap((p: any) =>
        (p.models || []).map((m: string) => ({ model: m, provider: p.provider }))
      )
    )
    .catch(() => []);
}

/** 后台任务列表（R3：独立线程长任务）。R80 续：读面收口带 Bearer */
export function getBackgroundTasks(): Promise<{ tasks: any[] }> {
  return apiFetch(`${API}/tasks/list`, { headers: authHeaders() })
    .then((r) => r.json())
    .catch(() => ({ tasks: [] }));
}

/** 上传文件落盘到平台（识图等按路径读取）。R79 补（hy4 自检）：/files/save 写共享卷已入 token 门，
 *  管理员的浏览器带 Bearer 上传正常；助手无钥匙=写不进 files/。 */
export function saveFile(name: string, b64: string): Promise<{ ok?: boolean; path?: string; error?: string }> {
  return apiFetch(`${API}/files/save`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ name, b64 }),
  })
    .then((r) => r.json())
    .catch(() => ({ error: '无法连接后端 (2024 端口)' }));
}
