from __future__ import annotations

from fastapi.testclient import TestClient

from app.db import Base, create_engine_for_url, create_session_factory
from app.main import create_app
from app.services.voxcpm_tts_service import VoxCPMTTSService, VoxCPMTTSUnavailable


class FakeVoxCPMTTSService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

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
        self.calls.append(
            {
                "text": text,
                "prompt_text": prompt_text,
                "prompt_audio_path": prompt_audio_path,
                "reference_audio_path": reference_audio_path,
                "cfg_value": cfg_value,
                "inference_timesteps": inference_timesteps,
                "normalize": normalize,
                "denoise": denoise,
            }
        )
        return b"RIFF....WAVEfmt "


class UnavailableVoxCPMTTSService:
    def synthesize(self, **_kwargs) -> bytes:
        raise VoxCPMTTSUnavailable(
            "VoxCPM model is not ready. Download openbmb/VoxCPM2 to data/models/voxcpm first."
        )


def make_client(tmp_path, service: FakeVoxCPMTTSService | None = None) -> TestClient:
    database_url = f"sqlite:///{tmp_path / 'voxcpm-tts-test.db'}"
    engine = create_engine_for_url(database_url)
    testing_session_local = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    app = create_app(session_factory=testing_session_local)
    if service is not None:
        app.state.voxcpm_tts_service = service
    return TestClient(app)


def test_openmaic_python_api_tts_upload_returns_wav_audio(tmp_path):
    service = FakeVoxCPMTTSService()
    client = make_client(tmp_path, service)

    response = client.post(
        "/tts/upload",
        data={
            "text": "(沉稳男教师声音)讲解 Python 函数参数。",
            "cfg_value": "2.5",
            "inference_timesteps": "12",
            "normalize": "true",
            "denoise": "false",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content.startswith(b"RIFF")
    assert service.calls == [
        {
            "text": "(沉稳男教师声音)讲解 Python 函数参数。",
            "prompt_text": None,
            "prompt_audio_path": None,
            "reference_audio_path": None,
            "cfg_value": 2.5,
            "inference_timesteps": 12,
            "normalize": True,
            "denoise": False,
        }
    ]


def test_openmaic_python_api_tts_upload_passes_reference_audio(tmp_path):
    service = FakeVoxCPMTTSService()
    client = make_client(tmp_path, service)

    response = client.post(
        "/tts/upload",
        data={
            "text": "继续讲解变量作用域。",
            "prompt_text": "这是一段参考音频文本。",
        },
        files={"reference_audio": ("voice.wav", b"RIFF....WAVEfmt ", "audio/wav")},
    )

    assert response.status_code == 200
    assert service.calls[0]["prompt_text"] == "这是一段参考音频文本。"
    reference_audio_path = service.calls[0]["reference_audio_path"]
    assert isinstance(reference_audio_path, str)
    assert reference_audio_path.endswith(".wav")


def test_openmaic_python_api_tts_upload_requires_text(tmp_path):
    client = make_client(tmp_path, FakeVoxCPMTTSService())

    response = client.post("/tts/upload", data={"text": "   "})

    assert response.status_code == 422
    assert response.json()["detail"] == "text is required"


def test_openmaic_python_api_tts_upload_reports_model_unavailable(tmp_path):
    client = make_client(tmp_path, UnavailableVoxCPMTTSService())

    response = client.post("/tts/upload", data={"text": "你好，这是测试。"})

    assert response.status_code == 503
    assert "VoxCPM model is not ready" in response.json()["detail"]


def test_openmaic_python_api_tts_upload_can_return_fallback_tone_when_enabled(tmp_path):
    class FallbackService(VoxCPMTTSService):
        def _get_model(self):
            raise VoxCPMTTSUnavailable("model cache missing")

    service = FallbackService()
    service.fallback_tone_enabled = True
    client = make_client(tmp_path, service)

    response = client.post("/tts/upload", data={"text": "你好，这是测试。"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content.startswith(b"RIFF")
