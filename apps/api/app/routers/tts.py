from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from app.services.voxcpm_tts_service import VoxCPMTTSService, VoxCPMTTSUnavailable


router = APIRouter(prefix="/tts", tags=["tts"])


def _parse_bool(value: bool | str | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_suffix(file: UploadFile) -> str:
    _, suffix = os.path.splitext(file.filename or "")
    if suffix.lower() in {".wav", ".mp3", ".flac", ".ogg", ".webm", ".m4a"}:
        return suffix
    return ".wav"


async def _write_upload_to_temp(file: UploadFile | None) -> str | None:
    if file is None:
        return None

    with tempfile.NamedTemporaryFile(delete=False, suffix=_safe_suffix(file)) as output:
        while chunk := await file.read(1024 * 1024):
            output.write(chunk)
        return output.name


def _cleanup(paths: Iterator[str | None]) -> None:
    for path in paths:
        if not path:
            continue
        try:
            os.unlink(path)
        except OSError:
            pass


def _get_tts_service(request: Request):
    service = getattr(request.app.state, "voxcpm_tts_service", None)
    if service is None:
        service = VoxCPMTTSService()
        request.app.state.voxcpm_tts_service = service
    return service


@router.post("/upload")
async def upload_tts(
    request: Request,
    text: str = Form(...),
    prompt_text: str | None = Form(None),
    cfg_value: float = Form(2.0),
    inference_timesteps: int = Form(10),
    normalize: str | bool | None = Form(False),
    denoise: str | bool | None = Form(False),
    reference_audio: UploadFile | None = File(None),
    prompt_audio: UploadFile | None = File(None),
) -> Response:
    if not text.strip():
        raise HTTPException(status_code=422, detail="text is required")

    reference_audio_path = await _write_upload_to_temp(reference_audio)
    prompt_audio_path = await _write_upload_to_temp(prompt_audio)
    try:
        service = _get_tts_service(request)
        try:
            audio = await run_in_threadpool(
                service.synthesize,
                text=text.strip(),
                prompt_text=prompt_text.strip() if prompt_text and prompt_text.strip() else None,
                prompt_audio_path=prompt_audio_path,
                reference_audio_path=reference_audio_path,
                cfg_value=cfg_value,
                inference_timesteps=inference_timesteps,
                normalize=_parse_bool(normalize),
                denoise=_parse_bool(denoise),
            )
        except VoxCPMTTSUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"VoxCPM synthesis failed: {exc}") from exc
    finally:
        _cleanup(iter((reference_audio_path, prompt_audio_path)))

    return Response(content=audio, media_type="audio/wav")
