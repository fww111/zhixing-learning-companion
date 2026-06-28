import { afterEach, describe, expect, it, vi } from 'vitest';

import { DEFAULT_TTS_MODELS, TTS_PROVIDERS } from '@/lib/audio/constants';
import { generateTTS } from '@/lib/audio/tts-providers';

describe('Qwen TTS', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('uses qwen-tts as the stable default model for Bailian playback', () => {
    expect(TTS_PROVIDERS['qwen-tts'].defaultModelId).toBe('qwen-tts');
    expect(DEFAULT_TTS_MODELS['qwen-tts']).toBe('qwen-tts');
  });

  it('falls back from qwen3-tts-flash to qwen-tts when DashScope rejects generated audio', async () => {
    const audioBytes = new Uint8Array([0x52, 0x49, 0x46, 0x46, 1, 2, 3, 4]);
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            code: 'InvalidParameter',
            message: 'Due to invalid text, invalid audio was returned.',
          }),
          { status: 400, headers: { 'content-type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            output: { audio: { url: 'https://dashscope-result.example/audio.wav' } },
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(audioBytes, { status: 200, headers: { 'content-type': 'audio/x-wav' } }),
      );
    vi.stubGlobal('fetch', fetchMock);

    const result = await generateTTS(
      {
        providerId: 'qwen-tts',
        apiKey: 'sk-test',
        baseUrl: 'https://dashscope.aliyuncs.com/api/v1',
        modelId: 'qwen3-tts-flash',
        voice: 'Cherry',
      },
      '同学们好，欢迎来到标准课堂。',
    );

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string).model).toBe('qwen3-tts-flash');
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string).model).toBe('qwen-tts');
    expect(fetchMock.mock.calls[2][0]).toBe('https://dashscope-result.example/audio.wav');
    expect(result.audio).toEqual(audioBytes);
    expect(result.format).toBe('wav');
  });
});
