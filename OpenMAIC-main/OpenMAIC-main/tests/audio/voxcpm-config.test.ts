import { describe, expect, it } from 'vitest';

import {
  DEFAULT_VOXCPM_BACKEND,
  VOXCPM_VLLM_MODEL_ID,
  buildVoxCPMBackendUrl,
  getVoxCPMBackendEndpoint,
} from '@/lib/audio/voxcpm';
import { TTS_PROVIDERS } from '@/lib/audio/constants';

describe('VoxCPM local backend defaults', () => {
  it('defaults to the FastAPI Python API adapter used by the learning platform backend', () => {
    expect(DEFAULT_VOXCPM_BACKEND).toBe('python-api');
    expect(getVoxCPMBackendEndpoint(DEFAULT_VOXCPM_BACKEND)).toBe('/tts/upload');
    expect(buildVoxCPMBackendUrl('http://127.0.0.1:8000', DEFAULT_VOXCPM_BACKEND)).toBe(
      'http://127.0.0.1:8000/tts/upload',
    );
  });

  it('keeps the local learning backend as the built-in VoxCPM base URL', () => {
    expect(TTS_PROVIDERS['voxcpm-tts'].defaultBaseUrl).toBe('http://127.0.0.1:8000');
    expect(TTS_PROVIDERS['voxcpm-tts'].defaultModelId).toBe(VOXCPM_VLLM_MODEL_ID);
  });
});
