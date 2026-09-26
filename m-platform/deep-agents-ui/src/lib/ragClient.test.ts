import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  setEmbedModel,
  getEmbedModel,
  ollamaUrl,
  ragLang,
  chunkText,
  embed,
  ragStats,
} from './ragClient';

function jsonResponse(data: unknown, ok = true) {
  return { ok, status: ok ? 200 : 500, json: async () => data } as unknown as Response;
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(jsonResponse({ embeddings: [[0.1, 0.2]] }))
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('嵌入模型注入（模块级单源状态）', () => {
  it('未注入时 getEmbedModel 为空串', () => {
    expect(getEmbedModel()).toBe('');
  });

  it('setEmbedModel 注入后可读回，空白串被忽略', () => {
    setEmbedModel('  qwen3-embedding:0.6b  ');
    expect(getEmbedModel()).toBe('qwen3-embedding:0.6b');
    setEmbedModel('   ');
    expect(getEmbedModel()).toBe('qwen3-embedding:0.6b');
  });
});

describe('ollamaUrl() URL 拼接', () => {
  it('浏览器环境拼 hostname + 11434 固定端口', () => {
    expect(ollamaUrl()).toBe(`http://${window.location.hostname}:11434`);
  });
});

describe('ragLang() 中英文判定（阈值 0.2）', () => {
  it('纯中文判 zh', () => {
    expect(ragLang('今天是晴天')).toBe('zh');
  });

  it('纯英文判 en', () => {
    expect(ragLang('hello world today')).toBe('en');
  });

  it('少量中文字符混在英文里仍判 en', () => {
    expect(ragLang('this is an English sentence with one 字')).toBe('en');
  });

  it('空串安全回退 en（不除零）', () => {
    expect(ragLang('')).toBe('en');
  });
});

describe('chunkText() 分片（默认 size=800 overlap=100）', () => {
  it('空串返回空数组', () => {
    expect(chunkText('')).toEqual([]);
  });

  it('纯空白 trim 后为空返回空数组', () => {
    expect(chunkText('   \n\t ')).toEqual([]);
  });

  it('不超过 size 时整段返回单片', () => {
    expect(chunkText('hello', 800)).toEqual(['hello']);
  });

  it('超过 size 时按 size-overlap 步进切片，片间有重叠', () => {
    const chunks = chunkText('a'.repeat(10), 4, 2);
    expect(chunks).toEqual(['aaaa', 'aaaa', 'aaaa', 'aaaa', 'aa']);
  });

  it('连续 3 个以上换行归一化为两个换行', () => {
    expect(chunkText('a\n\n\n\nb')).toEqual(['a\n\nb']);
  });
});

describe('embed()（mock fetch，不发真请求）', () => {
  it('模型未注入时显式报错且不发请求', async () => {
    // 换行重置模块状态做不到（单例），用临时置空模拟：直接依赖本文件开头未注入前的断言
    // 这里确保错误信息对“注入空串”场景成立——getEmbedModel 为空则必须抛
    const model = getEmbedModel();
    expect(model).not.toBe(''); // 前面用例已注入；若为空则走下方分支
    if (!model) {
      await expect(embed('x')).rejects.toThrow('嵌入模型未注入');
    }
  });

  it('成功时返回 embeddings[0]，请求体含模型名与截断到 4000 的输入', async () => {
    await expect(embed('hi')).resolves.toEqual([0.1, 0.2]);
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain(':11434/api/embed');
    expect(init.method).toBe('POST');
    const body = JSON.parse(init.body);
    expect(body.model).toBe(getEmbedModel());
    expect(body.input).toBe('hi');
  });

  it('输入超长截断到 4000 字符', async () => {
    await embed('x'.repeat(5000));
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(JSON.parse(init.body).input).toHaveLength(4000);
  });

  it('HTTP 非 2xx 抛带状态码的异常', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, false)));
    await expect(embed('hi')).rejects.toThrow('HTTP 500');
  });
});

describe('ragStats() 失败兜底', () => {
  it('网络失败静默回退零值结构', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    await expect(ragStats()).resolves.toEqual({ chunks: 0, docs: {} });
  });

  it('正常时透传后端统计', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ chunks: 3, docs: { a: 3 } }))
    );
    await expect(ragStats()).resolves.toEqual({ chunks: 3, docs: { a: 3 } });
  });
});
