import { describe, it, expect, vi, afterEach } from 'vitest';
import { API, apiFetch } from './apiBase';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('API 常量（src/lib/apiBase.ts）', () => {
  it('浏览器环境（jsdom）下 API = origin + /lg（same-origin 代理）', () => {
    expect(API).toBe(`${window.location.origin}/lg`);
    expect(API.endsWith('/lg')).toBe(true);
  });
});

describe('apiFetch() 统一 fetch 包装', () => {
  it('默认注入 credentials: include（携带 HttpOnly Cookie）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetchMock);

    await apiFetch('http://x/api');
    expect(fetchMock).toHaveBeenCalledWith('http://x/api', { credentials: 'include' });
  });

  it('合并调用方 init，且 init 可覆盖默认 credentials', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetchMock);

    await apiFetch('http://x/api', { method: 'POST', credentials: 'omit' });
    expect(fetchMock).toHaveBeenCalledWith('http://x/api', {
      credentials: 'omit',
      method: 'POST',
    });
  });

  it('透传上层异常，不做二次包装', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('network down'));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiFetch('http://x/api')).rejects.toThrow('network down');
  });
});
