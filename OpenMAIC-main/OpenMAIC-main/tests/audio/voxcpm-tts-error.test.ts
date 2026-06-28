import { afterEach, describe, expect, it, vi } from 'vitest';

import { generateTTS } from '@/lib/audio/tts-providers';

describe('VoxCPM TTS errors', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('sends prompt voices to the Python API using VoxCPM2 design text syntax', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Uint8Array([1, 2, 3]), {
        status: 200,
        headers: { 'content-type': 'audio/wav' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await generateTTS(
      {
        providerId: 'voxcpm-tts',
        baseUrl: 'http://127.0.0.1:8000',
        voice: 'voxcpm:auto',
        providerOptions: {
          backend: 'python-api',
          voicePrompt: '清晰自然的中文教师声音',
        },
      },
      '你好，这是测试。',
    );

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/tts/upload',
      expect.objectContaining({ method: 'POST' }),
    );
    const [, init] = fetchMock.mock.calls[0];
    const formData = init.body as FormData;
    expect(formData.get('text')).toBe('(清晰自然的中文教师声音)你好，这是测试。');
  });

  it('surfaces FastAPI detail when the local VoxCPM model is unavailable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail:
              'Failed to load VoxCPM model: cannot find snapshot folder on the local disk.',
          }),
          { status: 503, headers: { 'content-type': 'application/json' } },
        ),
      ),
    );

    await expect(
      generateTTS(
        {
          providerId: 'voxcpm-tts',
          baseUrl: 'http://127.0.0.1:8000',
          voice: 'voxcpm:auto',
          providerOptions: {
            backend: 'python-api',
            voicePrompt: '清晰自然的中文教师声音',
          },
        },
        '你好，这是测试。',
      ),
    ).rejects.toThrow('Failed to load VoxCPM model');
  });
});
