/** 后端固定地址：R10.8e 改走 same-origin 代理（/lg → 2024），彻底消灭跨源问题 */
export const API =
  (typeof window !== 'undefined' && `${window.location.origin}/lg`) ||
  process.env.NEXT_PUBLIC_LANGGRAPH_URL ||
  'http://127.0.0.1:2024';

// R10.8e：统一 fetch 包装——same-origin 代理自动携带 Cookie（HttpOnly），
// localStorage 的 Bearer 头为过渡兼容（有就带），新钥匙只种 Cookie 不再写 localStorage。
export function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  return fetch(input, { credentials: 'include', ...init });
}
