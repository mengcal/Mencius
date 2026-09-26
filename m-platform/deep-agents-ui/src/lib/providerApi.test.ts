import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  getAdminToken,
  clearAdminToken,
  authHeaders,
  postProviderAction,
  postSettings,
  tokenStatus,
  tokenRotate,
  tokenClear,
  getAllModels,
  getBackgroundTasks,
  saveFile,
  getSettings,
} from './providerApi';

const TOKEN_KEY = 'mia_admin_token';

function jsonResponse(data: unknown, ok = true) {
  return { ok, status: ok ? 200 : 500, json: async () => data } as unknown as Response;
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(jsonResponse({ ok: true }))
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('admin token 存取（localStorage 过渡兼容）', () => {
  it('getAdminToken 无钥匙时返回空串', () => {
    expect(getAdminToken()).toBe('');
  });

  it('getAdminToken 有钥匙时返回原值', () => {
    localStorage.setItem(TOKEN_KEY, 'sk-admin-1');
    expect(getAdminToken()).toBe('sk-admin-1');
  });

  it('clearAdminToken 清空后返回空串', () => {
    localStorage.setItem(TOKEN_KEY, 'sk-admin-1');
    clearAdminToken();
    expect(getAdminToken()).toBe('');
  });
});

describe('authHeaders() 认证头拼接', () => {
  it('无 token 时不带 Authorization，只透传 extra', () => {
    expect(authHeaders({ 'Content-Type': 'application/json' })).toEqual({
      'Content-Type': 'application/json',
    });
  });

  it('无 token 且无 extra 返回空对象', () => {
    expect(authHeaders()).toEqual({});
  });

  it('有 token 时注入 Bearer 且与 extra 合并', () => {
    localStorage.setItem(TOKEN_KEY, 'sk-admin-1');
    expect(authHeaders({ 'Content-Type': 'application/json' })).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer sk-admin-1',
    });
  });
});

describe('请求构造：URL / method / body（mock fetch，不发真请求）', () => {
  it('postProviderAction 拼出 /providers/{action} 并 POST JSON', async () => {
    await postProviderAction('test', { a: 1 });
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${window.location.origin}/lg/providers/test`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ a: 1 });
  });

  it('postSettings 拼出 /settings/{section} 并 POST JSON', async () => {
    await postSettings('rag', { embeddingModel: 'm' });
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe(`${window.location.origin}/lg/settings/rag`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ embeddingModel: 'm' });
  });

  it('r32 F1：postSettings 原样透传调用方给的 _rev（防撞车覆盖全入口的前提）', async () => {
    await postSettings('permissions', { miaManageAgents: true, _rev: 1777000000123456 });
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body._rev).toBe(1777000000123456); // 微秒级 _rev 原样到后端，JS 精度安全
    expect(body.miaManageAgents).toBe(true);
  });

  it('tokenRotate 无参时 body.token 为空串', async () => {
    await tokenRotate();
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ token: '' });
  });

  it('tokenClear 用 DELETE 且只带认证头', async () => {
    await tokenClear();
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(init.method).toBe('DELETE');
    expect(init.body).toBeUndefined();
  });
});

describe('响应处理与失败兜底（空值/异常边界）', () => {
  it('tokenStatus 正常解析 configured', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ configured: true, guard: true, unreachable: false })));
    await expect(tokenStatus()).resolves.toEqual({ configured: true, guard: true, unreachable: false });
  });

  it('tokenStatus 网络失败静默回退 configured: false', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    await expect(tokenStatus()).resolves.toEqual({ configured: false });
  });

  it('postProviderAction 网络失败回退友好错误对象（r32 F15：内部端口/容器名出用户文案）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    await expect(postProviderAction('test', {})).resolves.toEqual({
      error: '无法连接后端，请确认服务正在运行',
    });
  });

  it('getSettings HTTP 非 2xx 时抛异常（不静默吞）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({}, false)));
    await expect(getSettings()).rejects.toThrow('HTTP 500');
  });

  it('getAllModels 把 providers×models 摊平成 {model, provider} 列表', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          providers: [
            { provider: 'ollama', models: ['qwen3', 'llama3'] },
            { provider: 'openai', models: ['gpt-4o'] },
          ],
        })
      )
    );
    await expect(getAllModels()).resolves.toEqual([
      { model: 'qwen3', provider: 'ollama' },
      { model: 'llama3', provider: 'ollama' },
      { model: 'gpt-4o', provider: 'openai' },
    ]);
  });

  it('getAllModels 缺字段/请求失败都安全回退空数组', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({})));
    await expect(getAllModels()).resolves.toEqual([]);

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    await expect(getAllModels()).resolves.toEqual([]);
  });

  it('getBackgroundTasks 失败回退 { tasks: [] }', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('down')));
    await expect(getBackgroundTasks()).resolves.toEqual({ tasks: [] });
  });

  it('saveFile 请求体包含 name 与 b64', async () => {
    await saveFile('a.png', 'AAAA');
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ name: 'a.png', b64: 'AAAA' });
  });
});
