import { describe, it, expect, beforeEach } from 'vitest';
import { getConfig, saveConfig, type StandaloneConfig } from './config';

describe('config localStorage 读写（src/lib/config.ts）', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('无存储时 getConfig 返回 null', () => {
    expect(getConfig()).toBeNull();
  });

  it('saveConfig 后 getConfig 往返一致', () => {
    const c: StandaloneConfig = { deploymentUrl: 'http://localhost:2024', assistantId: 'asst_1' };
    saveConfig(c);
    expect(getConfig()).toEqual(c);
  });

  it('langsmithApiKey 可选字段随存随取', () => {
    saveConfig({ deploymentUrl: 'http://x', assistantId: 'a', langsmithApiKey: 'sk-x' });
    expect(getConfig()?.langsmithApiKey).toBe('sk-x');
  });

  it('损坏 JSON 不抛异常，静默回退 null', () => {
    localStorage.setItem('deep-agent-config', '{oops');
    expect(getConfig()).toBeNull();
  });
});
