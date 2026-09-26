import { describe, it, expect } from 'vitest';
import { cn } from './utils';

describe('cn() 类名合并（src/lib/utils.ts）', () => {
  it('拼接多个类名', () => {
    expect(cn('a', 'b')).toBe('a b');
  });

  it('过滤 false/undefined/null 假值', () => {
    expect(cn('a', false, undefined, null, 'b')).toBe('a b');
  });

  it('tailwind 冲突时后写的赢（tailwind-merge 语义）', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4');
    expect(cn('text-sm', 'text-lg')).toBe('text-lg');
  });

  it('不同维度的类共存不互删', () => {
    expect(cn('px-2', 'py-1')).toBe('px-2 py-1');
  });

  it('空输入返回空字符串', () => {
    expect(cn()).toBe('');
  });
});
