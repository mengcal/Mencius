'use client';

/**
 * settings/tabs/DocumentsTab.tsx —— 文档知识库（admin:documents，RAG）页（原 page.tsx L1119-1173 + RAG 状态迁出）
 * RAG 知识库：嵌入走本机 Ollama（浏览器直连），服务器只存向量。
 * 嵌入/存储逻辑在 ragClient.ts；R79（千问 P1）：/rag/rebuild 在 token 门内，带 Bearer。
 * 前置：Windows 环境变量 OLLAMA_ORIGINS=* 并重启 Ollama。
 */

import { useCallback, useEffect, useState } from 'react';
import { ragIngest, ragQuery, ragStats, setEmbedModel } from '@/lib/ragClient';
import { apiFetch } from '@/lib/apiBase';
import { authHeaders } from '@/lib/providerApi';
import { API, useSettings } from '../context';
import { Section, Row, inputC, cardClass, pageTitleClass, pageSubtitleClass } from '../ui';

export default function DocumentsTab() {
  const { val, set, flash } = useSettings();

  // ── RAG 知识库状态（嵌入/存储逻辑在 ragClient.ts）──
  const [ragName, setRagName] = useState('');
  const [ragText, setRagText] = useState('');
  const [ragBusy, setRagBusy] = useState(false);
  const [ragQ, setRagQ] = useState('');
  const [ragResults, setRagResults] = useState<{ name: string; score: number; text: string }[]>([]);
  const [ragStatsData, setRagStatsData] = useState<{ chunks: number; docs: Record<string, number> }>({ chunks: 0, docs: {} });
  const loadRagStats = useCallback(() => { ragStats().then(setRagStatsData); }, []);
  useEffect(() => { loadRagStats(); }, [loadRagStats]);
  const ragIngestNow = async () => {
    if (!ragName.trim() || !ragText.trim()) { flash('文档名和内容都要填'); return; }
    setRagBusy(true);
    try {
      const j = await ragIngest(ragName.trim(), ragText);
      if (j.ok) { flash(`${ragName} 入库 ${j.chunks} 段 ✓`); setRagText(''); loadRagStats(); }
      else flash(j.error || '失败');
    } catch (e: any) { flash(e.message || '失败（Ollama 在跑吗？OLLAMA_ORIGINS 设了吗）'); }
    setRagBusy(false);
  };
  const ragQueryNow = async () => {
    if (!ragQ.trim()) return;
    try {
      const j = await ragQuery(ragQ.trim());
      setRagResults(j.results || []);
    } catch (e: any) { flash(e.message || '检索失败'); }
  };

  return (
    <>
      <h2 className={pageTitleClass}>文档知识库（RAG）</h2>
      <p className={pageSubtitleClass}>
        嵌入走本机 Ollama（浏览器直连），服务器只存向量。前置：Windows 环境变量 OLLAMA_ORIGINS=* 并重启 Ollama
      </p>
      <Section first title="嵌入模型（全库唯一真源）">
        <Row label="向量模型" description="所有入库/检索/米娅查询统一用这一个模型（单模型跨语言，旧中英文双模型已退役）。推荐 qwen3-embedding:0.6b（1024维，本机显卡带得动）。⚠️ 换模型后必须点右边「重建全库」，否则新旧向量不同空间、检索全乱。">
          <div className="flex gap-2">
            <input className={inputC + ' w-52'} defaultValue={val('rag.embeddingModel', '')} placeholder="留空=后端默认 qwen3-embedding:0.6b"
              onChange={(e) => { set('rag.embeddingModel', e.target.value); setEmbedModel(e.target.value); }} />
            <button
              className="shrink-0 rounded-[10px] border border-border px-3 py-2 text-sm text-muted-foreground hover:bg-muted"
              onClick={async () => {
                try {
                  setRagBusy(true);
                  // R79（千问 P1）：/rag/rebuild 在 token 门内，带 Bearer（r25 起 X-By 常数头作废）
                  const j = await (await apiFetch(`${API}/rag/rebuild`, { method: 'POST', headers: authHeaders() })).json();
                  flash(j.ok ? `重建完成：${j.updated} 条切片已按 ${j.model} 重嵌` : `重建失败：${j.error}`);
                } catch (e: any) { flash(e.message || '重建失败'); } finally { setRagBusy(false); }
              }}
            >重建全库</button>
          </div>
        </Row>
        <Row label="向量维度" description="嵌入模型输出维度（rag.embeddingDim，默认 1024）。换不同维度的模型时改这里再重建全库——维度不符迁移会跳过并报警（09-17 起不再静默丢块）。">
          <input className={inputC + ' w-24'} type="number" defaultValue={val('rag.embeddingDim', 1024)}
            onBlur={(e) => set('rag.embeddingDim', Number(e.target.value) || 1024)} />
        </Row>
      </Section>
      <Section title="入库">
        <div className="flex gap-2">
          <input className={inputC + ' w-40 shrink-0'} placeholder="文档名" value={ragName} onChange={(e) => setRagName(e.target.value)} />
          <button className="shrink-0 rounded-[10px] bg-gray-900 px-3 py-2 text-sm font-medium text-white dark:bg-white dark:text-black" onClick={ragIngestNow}>
            {ragBusy ? '嵌入中…' : '入库'}
          </button>
        </div>
        <textarea className={inputC + ' h-32'} placeholder="粘贴要入库的文档全文…" value={ragText} onChange={(e) => setRagText(e.target.value)} />
      </Section>
      <Section title="检索测试">
        <div className="flex gap-2">
          <input className={inputC + ' flex-1'} placeholder="问一句，看能召回哪段…" value={ragQ} onChange={(e) => setRagQ(e.target.value)} />
          <button className="shrink-0 rounded-[10px] bg-gray-900 px-3 py-2 text-sm font-medium text-white dark:bg-white dark:text-black" onClick={ragQueryNow}>检索</button>
        </div>
        {ragResults.length > 0 && (
          <div className="flex flex-col gap-3">
            {ragResults.map((r, i) => (
              <div key={i} className={cardClass + ' p-3'}>
                <div className="text-xxs text-muted-foreground">{r.name} · 相关度 {r.score}</div>
                <div className="mt-1 whitespace-pre-wrap text-sm">{r.text}</div>
              </div>
            ))}
          </div>
        )}
      </Section>
      <Section title="库存">
        <div className="text-sm text-muted-foreground">{ragStatsData.chunks} 个片段 · {Object.keys(ragStatsData.docs || {}).length} 份文档：{Object.entries(ragStatsData.docs || {}).map(([n, c]) => `${n}(${c})`).join('、') || '空'}</div>
      </Section>
    </>
  );
}
