'use client';

/**
 * RAG 客户端（2026-08-30 作者）：浏览器直接调管理员本机 Ollama 嵌入，
 * 服务器只存向量——零内网出站、零 SSRF 风险。
 * R67（管理员 09-02）：嵌入模型唯一真源=配置页 rag.embeddingModel（默认 qwen3-embedding:0.6b，
 * 单模型跨语言 1024 维，旧 bge/mxbai 双模型分工作废）；页面加载后 setEmbedModel() 注入。
 * 前置：Windows 的 Ollama 需设置环境变量 OLLAMA_ORIGINS=* 并重启（允许浏览器跨域）。
 */
import { API, apiFetch } from './apiBase';
import { authHeaders } from './providerApi';

let EMBED_MODEL = 'qwen3-embedding:0.6b';
export function setEmbedModel(m: string) { if (m && m.trim()) EMBED_MODEL = m.trim(); }
export function getEmbedModel() { return EMBED_MODEL; }

export function ollamaUrl() {
  // 本机访问用 localhost；局域网其他设备访问时也走同一台机的 11434
  if (typeof window === 'undefined') return 'http://localhost:11434';
  return `http://${window.location.hostname}:11434`;
}

export function ragLang(text: string): 'zh' | 'en' {
  const zh = (text.match(/[\u4e00-\u9fff]/g) || []).length;
  return zh / Math.max(text.length, 1) > 0.2 ? 'zh' : 'en';
}

export async function embed(text: string): Promise<number[]> {
  const r = await fetch(`${ollamaUrl()}/api/embed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: EMBED_MODEL, input: text.slice(0, 4000) }),
  });
  if (!r.ok) throw new Error(`Ollama 嵌入失败 HTTP ${r.status}（模型 ${EMBED_MODEL} 是否已 ollama pull？）`);
  const j = await r.json();
  return j.embeddings[0];
}

export function chunkText(text: string, size = 800, overlap = 100): string[] {
  const t = text.replace(/\n{3,}/g, '\n\n').trim();
  if (t.length <= size) return t ? [t] : [];
  const out: string[] = [];
  let i = 0;
  while (i < t.length) {
    out.push(t.slice(i, i + size));
    i += size - overlap;
  }
  return out;
}

export async function ragIngest(name: string, text: string) {
  const chunks = chunkText(text);
  const withVec = await Promise.all(chunks.map(async (c) => ({
    text: c,
    lang: ragLang(c),
    vec: await embed(c),
  })));
  const r = await apiFetch(`${API}/rag/ingest`, {
    method: 'POST',
    // R79（评审E P1）：/rag/ingest 已入 token 门（提示注入持久化面）——必须带 Bearer。
    // r25：X-By 常数头作废（管理员裁决），真钥匙=Bearer/Cookie。
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ name, chunks: withVec }),
  });
  return r.json();
}

export async function ragQuery(q: string, k = 5): Promise<{ results?: { name: string; score: number; text: string }[] }> {
  const lang = ragLang(q);
  const q_vec = await embed(q);
  const r = await apiFetch(`${API}/rag/query`, {
    method: 'POST',
    // R80 续：/rag/ 读面收口（沙箱 host.docker.internal 旁路实锤后）——读面也带 Bearer
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ q_vec, lang, k }),
  });
  return r.json();
}

export function ragStats(): Promise<{ chunks: number; docs: Record<string, number> }> {
  return apiFetch(`${API}/rag/stats`, { headers: authHeaders() })
    .then((r) => {
      // R80 续（评审C P3）：401/失败不许静默吞成假数据（旧 catch 会让统计永远显示 0 片段）
      if (!r.ok) console.warn(`[rag] stats HTTP ${r.status}`);
      return r.json();
    })
    .catch(() => ({ chunks: 0, docs: {} }));
}
