from __future__ import annotations

import io
import math
import threading
import wave
from dataclasses import dataclass

import numpy as np

from app.core.config import settings


class VoxCPMTTSUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class VoxCPMRuntimeConfig:
    model_id: str
    cache_dir: str | None
    device: str | None
    local_files_only: bool
    load_denoiser: bool
    optimize: bool


def _runtime_config_from_settings() -> VoxCPMRuntimeConfig:
    return VoxCPMRuntimeConfig(
        model_id=settings.voxcpm_model_id,
        cache_dir=settings.voxcpm_cache_dir or None,
        device=settings.voxcpm_device or None,
        local_files_only=settings.voxcpm_local_files_only,
        load_denoiser=settings.voxcpm_load_denoiser,
        optimize=settings.voxcpm_optimize,
    )


class VoxCPMTTSService:
    def __init__(self, runtime_config: VoxCPMRuntimeConfig | None = None) -> None:
        self.runtime_config = runtime_config or _runtime_config_from_settings()
        self.fallback_tone_enabled = settings.voxcpm_fallback_tone
        self._model = None
        self._lock = threading.Lock()

    def synthesize(
        self,
        *,
        text: str,
        prompt_text: str | None = None,
        prompt_audio_path: str | None = None,
        reference_audio_path: str | None = None,
        cfg_value: float = 2.0,
        inference_timesteps: int = 10,
        normalize: bool = False,
        denoise: bool = False,
    ) -> bytes:
        try:
            model = self._get_model()
        except VoxCPMTTSUnavailable:
            if self.fallback_tone_enabled:
                return generate_fallback_tone_wav()
            raise
        effective_prompt_audio_path = prompt_audio_path
        if prompt_text and effective_prompt_audio_path is None and reference_audio_path:
            effective_prompt_audio_path = reference_audio_path

        audio_array = model.generate(
            text=text,
            prompt_wav_path=effective_prompt_audio_path,
            prompt_text=prompt_text if effective_prompt_audio_path else None,
            reference_wav_path=reference_audio_path,
            cfg_value=cfg_value,
            inference_timesteps=inference_timesteps,
            normalize=normalize,
            denoise=denoise and bool(effective_prompt_audio_path or reference_audio_path),
        )
        sample_rate = int(getattr(getattr(model, "tts_model", None), "sample_rate", 24000))
        return encode_float_wav(audio_array, sample_rate)

    def _get_model(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from voxcpm import VoxCPM
            except Exception as exc:  # pragma: no cover - exercised in real deployments.
                raise VoxCPMTTSUnavailable(
                    "VoxCPM is not installed in this Python environment. "
                    "Install it with `pip install voxcpm` or point OpenMAIC to a separate VoxCPM service."
                ) from exc

            try:
                self._model = VoxCPM.from_pretrained(
                    hf_model_id=self.runtime_config.model_id,
                    cache_dir=self.runtime_config.cache_dir,
                    local_files_only=self.runtime_config.local_files_only,
                    load_denoiser=self.runtime_config.load_denoiser,
                    optimize=self.runtime_config.optimize,
                    device=self.runtime_config.device,
                )
            except Exception as exc:  # pragma: no cover - depends on local model/runtime.
                raise VoxCPMTTSUnavailable(f"Failed to load VoxCPM model: {exc}") from exc
            return self._model


def encode_float_wav(audio_array: np.ndarray, sample_rate: int) -> bytes:
    array = np.asarray(audio_array, dtype=np.float32)
    if array.ndim > 1:
        array = np.squeeze(array)
    array = np.clip(array, -1.0, 1.0)
    pcm = (array * 32767.0).astype("<i2")

    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())
    return output.getvalue()


def generate_fallback_tone_wav(duration_seconds: float = 0.8, sample_rate: int = 24000) -> bytes:
    sample_count = max(1, int(duration_seconds * sample_rate))
    samples = np.array(
        [
            0.18 * math.sin(2 * math.pi * 660 * index / sample_rate)
            for index in range(sample_count)
        ],
        dtype=np.float32,
    )
    return encode_float_wav(samples, sample_rate)
