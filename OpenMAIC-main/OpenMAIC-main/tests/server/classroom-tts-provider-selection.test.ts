import { describe, expect, it, vi } from 'vitest';

import { selectServerTTSProvider } from '@/lib/server/classroom-media-generation';

vi.mock('@/lib/server/provider-config', () => ({
  getServerTTSProviders: () => ({
    'voxcpm-tts': { baseUrl: 'http://127.0.0.1:8000' },
    'qwen-tts': { baseUrl: 'https://dashscope.aliyuncs.com/api/v1' },
    'minimax-tts': { baseUrl: 'https://api.minimaxi.com' },
  }),
}));

describe('classroom server-side TTS provider selection', () => {
  it('prefers Aliyun Bailian Qwen TTS over local VoxCPM2 when both are configured', () => {
    expect(selectServerTTSProvider()).toBe('qwen-tts');
  });
});
