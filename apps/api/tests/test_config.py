from pathlib import Path

from app.core.config import (
    DEFAULT_NEO4J_BOLT_URI,
    DEFAULT_NEO4J_PASSWORD,
    MYSQL_DATABASE_URL,
    Settings,
    get_project_env_paths,
    load_env_file,
)


def test_default_settings_use_deepseek_v4_pro_local_mysql_and_neo4j(monkeypatch):
    for key in [
        "LLM_MODEL",
        "DATABASE_URL",
        "MOCK_LLM",
        "NEO4J_URI",
        "NEO4J_PASSWORD",
        "TUTOR_VISION_BASE_URL",
        "TUTOR_VISION_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)

    settings = Settings.from_environment()

    assert settings.llm_model == "deepseek-v4-pro"
    assert settings.tutor_vision_base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert settings.tutor_vision_model == "qwen3.7-plus"
    assert settings.database_url == MYSQL_DATABASE_URL
    assert settings.mock_llm is False
    assert settings.neo4j_uri == DEFAULT_NEO4J_BOLT_URI
    assert settings.neo4j_password == DEFAULT_NEO4J_PASSWORD


def test_tutor_vision_settings_can_use_qwen_specific_environment(monkeypatch):
    monkeypatch.delenv("TUTOR_VISION_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("TUTOR_VISION_BASE_URL", raising=False)
    monkeypatch.setenv("QWEN_API_KEY", "qwen-key")
    monkeypatch.setenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/")
    monkeypatch.setenv("TUTOR_VISION_MODEL", "qwen3.7-plus")

    settings = Settings.from_environment()

    assert settings.tutor_vision_api_key == "qwen-key"
    assert settings.tutor_vision_base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert settings.tutor_vision_model == "qwen3.7-plus"


def test_tutor_vision_settings_do_not_reuse_deepseek_key(monkeypatch):
    monkeypatch.delenv("TUTOR_VISION_API_KEY", raising=False)
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "deepseek-key")

    settings = Settings.from_environment()

    assert settings.tutor_vision_api_key == ""


def test_neo4j_browser_http_uri_is_normalized_to_bolt_driver_uri(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "http://127.0.0.1:7474/")

    settings = Settings.from_environment()

    assert settings.neo4j_uri == "bolt://127.0.0.1:7687"


def test_load_env_file_applies_local_values(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "MOCK_LLM=false",
                "LLM_MODEL=deepseek-v4-pro",
                "DATABASE_URL=mysql+pymysql://root:123456@127.0.0.1:3306/softbei?charset=utf8mb4",
            ]
        ),
        encoding="utf-8",
    )
    for key in ["MOCK_LLM", "LLM_MODEL", "DATABASE_URL"]:
        monkeypatch.delenv(key, raising=False)

    load_env_file(Path(env_file))
    settings = Settings.from_environment()

    assert settings.mock_llm is False
    assert settings.llm_model == "deepseek-v4-pro"
    assert settings.database_url.endswith("softbei?charset=utf8mb4")


def test_project_env_paths_target_repo_root_and_api_root():
    repo_env, api_env = get_project_env_paths()

    assert repo_env == Path(__file__).resolve().parents[3] / ".env"
    assert api_env == Path(__file__).resolve().parents[1] / ".env"


def test_course_knowledge_settings_are_loaded(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("UPLOAD_DIR", "data/uploads")
    monkeypatch.setenv("MILVUS_URI", "http://127.0.0.1:19530")
    monkeypatch.setenv("MILVUS_TOKEN", "milvus-token")
    monkeypatch.setenv("MILVUS_DB_NAME", "softbei")
    monkeypatch.setenv("OPENMAIC_BASE_URL", "http://127.0.0.1:3000")
    monkeypatch.setenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("OCR_LANG", "chi_sim+eng")
    monkeypatch.setenv("OCR_TEXT_MIN_CHARS", "80")
    monkeypatch.setenv("OCR_MAX_PAGES", "12")
    monkeypatch.setenv("OCR_RENDER_SCALE", "1.25")
    monkeypatch.setenv("OCR_MODEL_SIZE", "mobile")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local_bge")
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    monkeypatch.setenv("EMBEDDING_DEVICE", "cpu")
    monkeypatch.setenv("EMBEDDING_CACHE_DIR", "data/models/embeddings")
    monkeypatch.setenv("MINERU_ENABLED", "true")
    monkeypatch.setenv("MINERU_API_TOKEN", "mineru-token")
    monkeypatch.setenv("MINERU_BASE_URL", "https://mineru.net")
    monkeypatch.setenv("MINERU_MODEL_VERSION", "vlm")
    monkeypatch.setenv("MINERU_LANGUAGE", "ch")
    monkeypatch.setenv("MINERU_ENABLE_TABLE", "true")
    monkeypatch.setenv("MINERU_ENABLE_FORMULA", "true")
    monkeypatch.setenv("MINERU_IS_OCR", "true")
    monkeypatch.setenv("MINERU_POLL_INTERVAL_SECONDS", "2")
    monkeypatch.setenv("MINERU_POLL_TIMEOUT_SECONDS", "600")
    monkeypatch.setenv("MINERU_FALLBACK_TO_LOCAL", "false")

    settings = Settings.from_environment()

    assert settings.upload_dir == "data/uploads"
    assert settings.milvus_uri == "http://127.0.0.1:19530"
    assert settings.milvus_token == "milvus-token"
    assert settings.milvus_db_name == "softbei"
    assert settings.openmaic_base_url == "http://127.0.0.1:3000"
    assert settings.neo4j_uri == "bolt://127.0.0.1:7687"
    assert settings.neo4j_user == "neo4j"
    assert settings.neo4j_password == "secret"
    assert settings.ocr_lang == "chi_sim+eng"
    assert settings.ocr_text_min_chars == 80
    assert settings.ocr_max_pages == 12
    assert settings.ocr_render_scale == 1.25
    assert settings.ocr_model_size == "mobile"
    assert settings.embedding_provider == "local_bge"
    assert settings.embedding_model == "BAAI/bge-m3"
    assert settings.embedding_device == "cpu"
    assert settings.embedding_cache_dir == "data/models/embeddings"
    assert settings.mineru_enabled is True
    assert settings.mineru_api_token == "mineru-token"
    assert settings.mineru_base_url == "https://mineru.net"
    assert settings.mineru_model_version == "vlm"
    assert settings.mineru_language == "ch"
    assert settings.mineru_enable_table is True
    assert settings.mineru_enable_formula is True
    assert settings.mineru_is_ocr is True
    assert settings.mineru_poll_interval_seconds == 2
    assert settings.mineru_poll_timeout_seconds == 600
    assert settings.mineru_fallback_to_local is False
