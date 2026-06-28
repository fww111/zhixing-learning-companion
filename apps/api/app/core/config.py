from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


MYSQL_DATABASE_URL = "mysql+pymysql://root:709055@127.0.0.1:3306/sortbei11?charset=utf8mb4"
DEFAULT_LLM_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_LLM_MODEL = "deepseek-v4-pro"
DEFAULT_NEO4J_BOLT_URI = "bolt://127.0.0.1:7687"
DEFAULT_NEO4J_USER = "neo4j"
DEFAULT_NEO4J_PASSWORD = ""
DEFAULT_EMBEDDING_PROVIDER = "local_bge"
DEFAULT_EMBEDDING_MODEL = "D:/softbei/a3/data/models/embeddings/BAAI/bge-m3"
DEFAULT_EMBEDDING_DEVICE = "cpu"
DEFAULT_EMBEDDING_CACHE_DIR = "D:/softbei/a3/data/models/embeddings"
DEFAULT_EMBEDDING_BATCH_SIZE = 16
DEFAULT_EMBEDDING_MAX_CHARS = 512
DEFAULT_EMBEDDING_MAX_SEQ_LENGTH = 512
DEFAULT_OCR_TEXT_MIN_CHARS = 50
DEFAULT_OCR_MAX_PAGES = 20
DEFAULT_OCR_RENDER_SCALE = 1.5
DEFAULT_OCR_MODEL_SIZE = "mobile"
DEFAULT_MINERU_BASE_URL = "https://mineru.net"
DEFAULT_MINERU_MODEL_VERSION = "vlm"
DEFAULT_MINERU_LANGUAGE = "ch"
DEFAULT_MILVUS_URI = "http://127.0.0.1:19530"
DEFAULT_OPENMAIC_BASE_URL = "http://127.0.0.1:3000"
DEFAULT_VOXCPM_MODEL_ID = "openbmb/VoxCPM2"
DEFAULT_VOXCPM_CACHE_DIR = "D:/softbei/a3/data/models/voxcpm"
DEFAULT_TUTOR_VISION_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_TUTOR_VISION_MODEL = "qwen3.7-plus"


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower().strip() in {"1", "true", "yes", "on"}


def load_env_file(path: Path, override: bool = False) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = value


def get_project_env_paths() -> tuple[Path, Path]:
    current = Path(__file__).resolve()
    api_root = current.parents[2]
    repo_root = current.parents[4]
    return repo_root / ".env", api_root / ".env"


def load_project_env_files() -> None:
    repo_env, api_env = get_project_env_paths()
    load_env_file(repo_env)
    load_env_file(api_env)


def normalize_neo4j_uri(raw_uri: str | None) -> str:
    uri = (raw_uri or "").strip()
    if not uri:
        return DEFAULT_NEO4J_BOLT_URI

    parsed = urlparse(uri)
    if parsed.scheme in {"http", "https"}:
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 7474
        if port == 7474:
            return f"bolt://{host}:7687"

    return uri


load_project_env_files()


@dataclass(frozen=True)
class Settings:
    app_name: str = "Personalized Learning Agents"
    llm_api_key: str = ""
    llm_base_url: str = DEFAULT_LLM_BASE_URL
    llm_model: str = DEFAULT_LLM_MODEL
    tutor_vision_api_key: str = ""
    tutor_vision_base_url: str = DEFAULT_TUTOR_VISION_BASE_URL
    tutor_vision_model: str = DEFAULT_TUTOR_VISION_MODEL
    database_url: str = MYSQL_DATABASE_URL
    mock_llm: bool = False
    jwt_secret_key: str = "change-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    upload_dir: str = "data/uploads"
    chroma_persist_directory: str = "data/chroma"
    milvus_uri: str = DEFAULT_MILVUS_URI
    milvus_token: str = ""
    milvus_user: str = ""
    milvus_password: str = ""
    milvus_db_name: str = ""
    openmaic_base_url: str = DEFAULT_OPENMAIC_BASE_URL
    openmaic_timeout_seconds: float = 30.0
    voxcpm_model_id: str = DEFAULT_VOXCPM_MODEL_ID
    voxcpm_cache_dir: str = DEFAULT_VOXCPM_CACHE_DIR
    voxcpm_device: str = ""
    voxcpm_local_files_only: bool = False
    voxcpm_load_denoiser: bool = True
    voxcpm_optimize: bool = True
    voxcpm_fallback_tone: bool = False
    neo4j_uri: str = DEFAULT_NEO4J_BOLT_URI
    neo4j_user: str = DEFAULT_NEO4J_USER
    neo4j_password: str = DEFAULT_NEO4J_PASSWORD
    ocr_lang: str = "chi_sim+eng"
    ocr_text_min_chars: int = DEFAULT_OCR_TEXT_MIN_CHARS
    ocr_max_pages: int = DEFAULT_OCR_MAX_PAGES
    ocr_render_scale: float = DEFAULT_OCR_RENDER_SCALE
    ocr_model_size: str = DEFAULT_OCR_MODEL_SIZE
    max_upload_size_mb: int = 100
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_device: str = DEFAULT_EMBEDDING_DEVICE
    embedding_cache_dir: str = DEFAULT_EMBEDDING_CACHE_DIR
    embedding_batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE
    embedding_max_chars: int = DEFAULT_EMBEDDING_MAX_CHARS
    embedding_max_seq_length: int = DEFAULT_EMBEDDING_MAX_SEQ_LENGTH
    mineru_enabled: bool = False
    mineru_api_token: str = ""
    mineru_base_url: str = DEFAULT_MINERU_BASE_URL
    mineru_model_version: str = DEFAULT_MINERU_MODEL_VERSION
    mineru_language: str = DEFAULT_MINERU_LANGUAGE
    mineru_enable_table: bool = True
    mineru_enable_formula: bool = True
    mineru_is_ocr: bool = True
    mineru_poll_interval_seconds: int = 3
    mineru_poll_timeout_seconds: int = 900
    mineru_fallback_to_local: bool = True

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            llm_base_url=os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL),
            llm_model=os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL),
            tutor_vision_api_key=(
                os.getenv("TUTOR_VISION_API_KEY")
                or os.getenv("QWEN_API_KEY")
                or os.getenv("DASHSCOPE_API_KEY")
                or ""
            ),
            tutor_vision_base_url=(
                os.getenv("TUTOR_VISION_BASE_URL")
                or os.getenv("QWEN_BASE_URL")
                or DEFAULT_TUTOR_VISION_BASE_URL
            ).rstrip("/"),
            tutor_vision_model=os.getenv("TUTOR_VISION_MODEL", DEFAULT_TUTOR_VISION_MODEL),
            database_url=os.getenv("DATABASE_URL", MYSQL_DATABASE_URL),
            mock_llm=os.getenv("MOCK_LLM", "false").lower() == "true",
            jwt_secret_key=os.getenv("JWT_SECRET_KEY", "change-me-in-env"),
            jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256"),
            access_token_expire_minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")),
            upload_dir=os.getenv("UPLOAD_DIR", "data/uploads"),
            chroma_persist_directory=os.getenv("CHROMA_PERSIST_DIRECTORY", "data/chroma"),
            milvus_uri=os.getenv("MILVUS_URI", DEFAULT_MILVUS_URI),
            milvus_token=os.getenv("MILVUS_TOKEN", ""),
            milvus_user=os.getenv("MILVUS_USER", ""),
            milvus_password=os.getenv("MILVUS_PASSWORD", ""),
            milvus_db_name=os.getenv("MILVUS_DB_NAME", ""),
            openmaic_base_url=os.getenv("OPENMAIC_BASE_URL", DEFAULT_OPENMAIC_BASE_URL).rstrip("/"),
            openmaic_timeout_seconds=float(os.getenv("OPENMAIC_TIMEOUT_SECONDS", "30")),
            voxcpm_model_id=os.getenv("VOXCPM_MODEL_ID", DEFAULT_VOXCPM_MODEL_ID),
            voxcpm_cache_dir=os.getenv("VOXCPM_CACHE_DIR", DEFAULT_VOXCPM_CACHE_DIR),
            voxcpm_device=os.getenv("VOXCPM_DEVICE", ""),
            voxcpm_local_files_only=env_bool("VOXCPM_LOCAL_FILES_ONLY", False),
            voxcpm_load_denoiser=env_bool("VOXCPM_LOAD_DENOISER", True),
            voxcpm_optimize=env_bool("VOXCPM_OPTIMIZE", True),
            voxcpm_fallback_tone=env_bool("VOXCPM_FALLBACK_TONE", False),
            neo4j_uri=normalize_neo4j_uri(os.getenv("NEO4J_URI", DEFAULT_NEO4J_BOLT_URI)),
            neo4j_user=os.getenv("NEO4J_USER", DEFAULT_NEO4J_USER),
            neo4j_password=os.getenv("NEO4J_PASSWORD", DEFAULT_NEO4J_PASSWORD),
            ocr_lang=os.getenv("OCR_LANG", "chi_sim+eng"),
            ocr_text_min_chars=int(os.getenv("OCR_TEXT_MIN_CHARS", str(DEFAULT_OCR_TEXT_MIN_CHARS))),
            ocr_max_pages=int(os.getenv("OCR_MAX_PAGES", str(DEFAULT_OCR_MAX_PAGES))),
            ocr_render_scale=float(os.getenv("OCR_RENDER_SCALE", str(DEFAULT_OCR_RENDER_SCALE))),
            ocr_model_size=os.getenv("OCR_MODEL_SIZE", DEFAULT_OCR_MODEL_SIZE).lower().strip(),
            max_upload_size_mb=int(os.getenv("MAX_UPLOAD_SIZE_MB", "100")),
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", DEFAULT_EMBEDDING_PROVIDER),
            embedding_model=os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
            embedding_device=os.getenv("EMBEDDING_DEVICE", DEFAULT_EMBEDDING_DEVICE),
            embedding_cache_dir=os.getenv("EMBEDDING_CACHE_DIR", DEFAULT_EMBEDDING_CACHE_DIR),
            embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", str(DEFAULT_EMBEDDING_BATCH_SIZE))),
            embedding_max_chars=int(os.getenv("EMBEDDING_MAX_CHARS", str(DEFAULT_EMBEDDING_MAX_CHARS))),
            embedding_max_seq_length=int(os.getenv("EMBEDDING_MAX_SEQ_LENGTH", str(DEFAULT_EMBEDDING_MAX_SEQ_LENGTH))),
            mineru_enabled=env_bool("MINERU_ENABLED", False),
            mineru_api_token=os.getenv("MINERU_API_TOKEN", ""),
            mineru_base_url=os.getenv("MINERU_BASE_URL", DEFAULT_MINERU_BASE_URL).rstrip("/"),
            mineru_model_version=os.getenv("MINERU_MODEL_VERSION", DEFAULT_MINERU_MODEL_VERSION),
            mineru_language=os.getenv("MINERU_LANGUAGE", DEFAULT_MINERU_LANGUAGE),
            mineru_enable_table=env_bool("MINERU_ENABLE_TABLE", True),
            mineru_enable_formula=env_bool("MINERU_ENABLE_FORMULA", True),
            mineru_is_ocr=env_bool("MINERU_IS_OCR", True),
            mineru_poll_interval_seconds=int(os.getenv("MINERU_POLL_INTERVAL_SECONDS", "3")),
            mineru_poll_timeout_seconds=int(os.getenv("MINERU_POLL_TIMEOUT_SECONDS", "900")),
            mineru_fallback_to_local=env_bool("MINERU_FALLBACK_TO_LOCAL", True),
        )


settings = Settings.from_environment()
