import sys
import types
from pathlib import Path
from datetime import date
import json
from urllib.parse import quote

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import Base, create_engine_for_url, create_session_factory
from app.main import create_app
from app.models.course import CourseMaterial, GraphBuildJob, KnowledgeChunk
from app.models.profile import StudentProfile
from app.models.profile_record import StudentProfileRecord
from app.services.material_parser import ParsedPage
from app.services.course_service import (
    CourseService,
    DEFAULT_C_MATERIAL_FILENAME,
    DEFAULT_PYTHON_CHUNKS,
    DEFAULT_PYTHON_CONTAINS_EDGES,
    DEFAULT_PYTHON_EDGES,
    DEFAULT_PYTHON_MATERIAL_STORAGE_PATH,
    DEFAULT_PYTHON_NODES,
    DEFAULT_PYTHON_PREREQUISITE_EDGES,
)


def make_client(tmp_path, *, raise_server_exceptions: bool = True):
    database_url = f"sqlite:///{tmp_path / 'courses-test.db'}"
    engine = create_engine_for_url(database_url)
    TestingSessionLocal = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    app = create_app(session_factory=TestingSessionLocal)
    app.state.testing_session_factory = TestingSessionLocal
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def register_user(client: TestClient, username: str, email: str) -> str:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": "secret123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_course(client: TestClient, token: str, name: str = "machine learning basics") -> int:
    response = client.post(
        "/api/courses",
        headers=auth_headers(token),
        json={"name": name},
    )
    assert response.status_code == 200
    return response.json()["id"]


def confirm_profile_for_user(db, user_id: int, course_id: int | None = None, **overrides) -> StudentProfile:
    profile = StudentProfile(
        student_id=f"user-{user_id}",
        major="Computer Science",
        grade="澶т簩",
        learning_goal="绯荤粺鎺屾彙 Python 绋嬪簭璁捐",
        knowledge_foundation="Basic Python foundation with weak lists and functions",
        learning_style="鍏堝浘瑙ｅ啀缁冧範",
        cognitive_style="鍏堢洿瑙傜悊瑙ｅ啀浠ｇ爜楠岃瘉",
        weak_points=["鍒楄〃", "鍑芥暟"],
        time_preference="每天晚间 45 分钟",
        resource_preference=["diagram", "code practice", "short exercise"],
        motivation="Pass the course exam and complete a project",
        constraints=["纰庣墖鏃堕棿瀛︿範"],
        assessment_preference="鐭粌涔犲拰浠ｇ爜浠诲姟",
        knowledge_graph_focus=["鍒楄〃", "鍑芥暟"],
    ).model_copy(update=overrides).with_completion_score()
    db.add(
        StudentProfileRecord(
            user_id=user_id,
            course_id=course_id,
            student_id=profile.student_id,
            profile_data=profile.model_dump(mode="json"),
        )
    )
    db.commit()
    return profile


def fake_parser(storage_path, file_type, ocr_lang, ocr_max_pages=None):  # noqa: ARG001
    return [
        ParsedPage(
            source_locator="page 1",
            heading="Gradient descent",
            text="Gradient descent updates parameters with a learning rate and a loss gradient.",
        )
    ]


def long_heading_parser(storage_path, file_type, ocr_lang, ocr_max_pages=None):  # noqa: ARG001
    return [
        ParsedPage(
            source_locator="page 1",
            heading="H" * 400,
            text="Content with a very long first line heading should still be saved as a chunk.",
        )
    ]


class FakeVectorService:
    upserts = []
    closed_count = 0

    def upsert_chunks(self, course_id, chunks, **kwargs):  # noqa: ARG002
        self.upserts.append({"course_id": course_id, "chunk_ids": [chunk["id"] for chunk in chunks]})
        return None

    def delete_chunks(self, course_id, chunk_ids):  # noqa: ARG002
        return None

    def close(self):
        type(self).closed_count += 1


class RaisingVectorService:
    def upsert_chunks(self, course_id, chunks, **kwargs):  # noqa: ARG002
        raise ValueError("vector upsert failed")

    def delete_chunks(self, course_id, chunk_ids):  # noqa: ARG002
        return None


class OfflineVectorService:
    def __init__(self):
        raise RuntimeError("milvus unavailable")


class FakeKnowledgeGraphAgent:
    async def build_graph_async(self, chunks):  # noqa: ARG002
        return {
            "nodes": [{"id": "n1", "name": "Gradient descent"}],
            "edges": [],
        }


class RecordingBackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append({"func": func, "args": args, "kwargs": kwargs})

    def run_all(self):
        for task in self.tasks:
            task["func"](*task["args"], **task["kwargs"])


class NoopMaterialTaskQueue:
    def __init__(self):
        self.enqueued = []
        self.vector_rebuilds = []

    def enqueue(self, user_id, course_id, material_id, chunk_params=None):
        self.enqueued.append(
            {
                "user_id": user_id,
                "course_id": course_id,
                "material_id": material_id,
                "chunk_params": chunk_params,
            }
        )

    def enqueue_vector_rebuild(self, user_id, course_id):
        self.vector_rebuilds.append({"user_id": user_id, "course_id": course_id})


def patch_in_memory_graph_store(monkeypatch):
    class InMemoryGraphStore:
        graphs = {}

        def replace_course_graph(self, user_id, course_id, nodes, edges):
            self.graphs[(user_id, course_id)] = {"nodes": nodes, "edges": edges}

        def get_course_graph(self, user_id, course_id):
            return self.graphs.get((user_id, course_id), {"nodes": [], "edges": []})

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", InMemoryGraphStore)
    return InMemoryGraphStore


def test_courses_list_requires_authentication(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/api/courses")

    assert response.status_code == 401


def test_user_can_create_and_list_owned_courses(tmp_path):
    client = make_client(tmp_path)
    token = register_user(client, "courseuser", "course@example.com")

    created = client.post(
        "/api/courses",
        headers=auth_headers(token),
        json={
            "name": "鏈哄櫒瀛︿範鍩虹",
            "major": "Computer Science",
            "level": "澶т簩",
            "description": "Intro course",
        },
    )
    listed = client.get("/api/courses", headers=auth_headers(token))

    assert created.status_code == 200
    created_payload = created.json()
    assert created_payload["id"] > 0
    assert created_payload["name"] == "鏈哄櫒瀛︿範鍩虹"
    assert created_payload["major"] == "Computer Science"
    assert created_payload["level"] == "澶т簩"
    assert created_payload["description"] == "Intro course"

    assert listed.status_code == 200
    assert [course["id"] for course in listed.json()] == [created_payload["id"]]


def test_second_user_cannot_get_first_users_course(tmp_path):
    client = make_client(tmp_path)
    owner_token = register_user(client, "owner", "owner@example.com")
    other_token = register_user(client, "other", "other@example.com")
    created = client.post(
        "/api/courses",
        headers=auth_headers(owner_token),
        json={"name": "鏈哄櫒瀛︿範鍩虹"},
    )
    course_id = created.json()["id"]

    response = client.get(f"/api/courses/{course_id}", headers=auth_headers(other_token))

    assert response.status_code == 404


def test_unsupported_material_upload_returns_400_without_real_parsing(tmp_path):
    client = make_client(tmp_path)
    token = register_user(client, "uploader", "uploader@example.com")
    course = client.post(
        "/api/courses",
        headers=auth_headers(token),
        json={"name": "鏈哄櫒瀛︿範鍩虹"},
    )
    course_id = course.json()["id"]

    response = client.post(
        f"/api/courses/{course_id}/materials",
        headers=auth_headers(token),
        files={"file": ("notes.txt", b"plain text is not supported", "text/plain")},
    )

    assert response.status_code == 400
    assert "unsupported" in response.json()["detail"].lower()


def test_legacy_ppt_upload_reaches_parser_and_returns_controlled_error(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "pptuser", "pptuser@example.com")
    course = client.post(
        "/api/courses",
        headers=auth_headers(token),
        json={"name": "閺堝搫娅掔€涳缚绡勯崺铏诡攨"},
    )
    course_id = course.json()["id"]

    def raise_legacy_ppt_error(storage_path, file_type, ocr_lang):
        raise ValueError("Legacy .ppt parsing is not supported; convert to .pptx")

    monkeypatch.setattr(CourseService, "parser", staticmethod(raise_legacy_ppt_error))
    client.app.state.material_task_queue = NoopMaterialTaskQueue()

    response = client.post(
        f"/api/courses/{course_id}/materials",
        headers=auth_headers(token),
        files={
            "file": (
                "slides.ppt",
                b"legacy powerpoint content",
                "application/vnd.ms-powerpoint",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["parse_status"] == "queued"


def test_successful_upload_response_does_not_include_storage_path(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "success-uploader", "success-uploader@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)

    with client.app.state.testing_session_factory() as db:
        tasks = RecordingBackgroundTasks()
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="../unsafe name.PDF",
            content=b"fake pdf content",
        )
        CourseService(db).process_material_by_id(1, course_id, material.id)
        db.refresh(material)

        assert material.parse_status == "parsed"
        assert material.storage_path


def test_upload_material_returns_queued_before_background_processing(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "queued-uploader", "queued-uploader@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)

    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )

    assert material.parse_status == "queued"


def test_background_material_task_parses_chunks_and_indexes_vectors(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "background-uploader", "background-uploader@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)

    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )
        assert material.parse_status == "queued"
        CourseService(db).process_material_by_id(1, course_id, material.id)
        db.refresh(material)
        chunks = list(db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.material_id == material.id)))

    assert material.parse_status == "parsed"
    assert material.ocr_used is False
    assert len(chunks) == 1
    assert chunks[0].embedding_id == f"chunk-{chunks[0].id}"


def test_background_material_task_uses_mineru_status_before_chunking(tmp_path, monkeypatch):
    from app.services import course_service

    client = make_client(tmp_path)
    token = register_user(client, "mineru-uploader", "mineru-uploader@example.com")
    course_id = create_course(client, token)
    observed_statuses = []

    def mineru_parser(storage_path, file_type, ocr_lang, ocr_max_pages=None):  # noqa: ARG001
        with client.app.state.testing_session_factory() as probe_db:
            material = probe_db.scalar(select(CourseMaterial).where(CourseMaterial.course_id == course_id))
            observed_statuses.append(material.parse_status)
        return [
            ParsedPage(
                source_locator="page 1",
                heading="Python 鍏ラ棬",
                text="Python variables, expressions, and control flow.",
                ocr_used=True,
            )
        ]

    monkeypatch.setattr(
        course_service,
        "settings",
        types.SimpleNamespace(
            mineru_enabled=True,
            mineru_api_token="token-1",
            ocr_lang="chi_sim+eng",
            upload_dir=str(tmp_path / "uploads"),
            max_upload_size_mb=100,
        ),
    )
    monkeypatch.setattr(CourseService, "parser", staticmethod(mineru_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)

    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )
        CourseService(db).process_material_by_id(1, course_id, material.id)
        db.refresh(material)
        chunks = list(db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.material_id == material.id)))

    assert observed_statuses == ["mineru_polling"]
    assert material.parse_status == "parsed"
    assert material.ocr_used is True
    assert len(chunks) == 1
    assert chunks[0].content.startswith("Python")


def test_background_material_task_fails_fast_when_mineru_enabled_without_token(tmp_path, monkeypatch):
    from app.services import course_service

    client = make_client(tmp_path)
    token = register_user(client, "mineru-missing-token", "mineru-missing-token@example.com")
    course_id = create_course(client, token)

    def forbidden_parser(storage_path, file_type, ocr_lang, ocr_max_pages=None):  # noqa: ARG001
        raise AssertionError("parser should not run when MinerU token is missing")

    monkeypatch.setattr(
        course_service,
        "settings",
        types.SimpleNamespace(
            mineru_enabled=True,
            mineru_api_token="",
            ocr_lang="chi_sim+eng",
            upload_dir=str(tmp_path / "uploads"),
            max_upload_size_mb=100,
        ),
    )
    monkeypatch.setattr(CourseService, "parser", staticmethod(forbidden_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)

    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )
        CourseService(db).process_material_by_id(1, course_id, material.id)
        db.refresh(material)
        chunks = list(db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.material_id == material.id)))

    assert material.parse_status == "failed"
    assert "MINERU_API_TOKEN" in material.parse_error
    assert chunks == []


def test_pdf_upload_succeeds_when_ocr_dependency_is_missing_but_text_is_extractable(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "ocr-fallback", "ocr-fallback@example.com")
    course_id = create_course(client, token)

    class FakePdfPage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakePdfReader:
        def __init__(self, path):
            self.pages = [
                FakePdfPage("This page already has enough extracted text."),
                FakePdfPage("short extracted text"),
            ]

    fake_pypdf = types.SimpleNamespace(PdfReader=FakePdfReader)
    monkeypatch.setitem(sys.modules, "pypdf", fake_pypdf)

    from app.services import material_parser

    def raising_ocr_pdf_page(path, page_number, ocr_lang):  # noqa: ARG001
        raise material_parser.MaterialParseError("OCR failed. Install and configure PaddleOCR, PaddlePaddle, PyMuPDF.")

    monkeypatch.setattr(material_parser, "ocr_pdf_page", raising_ocr_pdf_page, raising=False)
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)
    client.app.state.material_task_queue = NoopMaterialTaskQueue()

    response = client.post(
        f"/api/courses/{course_id}/materials",
        headers=auth_headers(token),
        files={"file": ("lesson.pdf", b"fake pdf content", "application/pdf")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["parse_status"] == "queued"
    assert payload["ocr_used"] is False


def test_user_can_list_course_material_statuses(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "material-lister", "material-lister@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)
    client.app.state.material_task_queue = NoopMaterialTaskQueue()

    upload = client.post(
        f"/api/courses/{course_id}/materials",
        headers=auth_headers(token),
        files={"file": ("lesson.pdf", b"fake pdf content", "application/pdf")},
    )
    listed = client.get(f"/api/courses/{course_id}/materials", headers=auth_headers(token))

    assert upload.status_code == 200
    assert listed.status_code == 200
    payload = listed.json()
    assert len(payload) == 1
    assert payload[0]["filename"] == "lesson.pdf"
    assert payload[0]["parse_status"] == "queued"
    assert payload[0]["ocr_used"] is False
    assert "storage_path" not in payload[0]


def test_user_can_delete_index_failed_material_record_chunks_and_uploaded_file(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "failed-delete", "failed-delete@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", RaisingVectorService)

    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )
        CourseService(db).process_material_by_id(1, course_id, material.id)
        db.refresh(material)
        assert material.parse_status == "index_failed"
        material = db.scalar(select(CourseMaterial).where(CourseMaterial.course_id == course_id))
        assert material is not None
        material_id = material.id
        storage_path = material.storage_path

    response = client.delete(
        f"/api/courses/{course_id}/materials/{material_id}",
        headers=auth_headers(token),
    )
    listed = client.get(f"/api/courses/{course_id}/materials", headers=auth_headers(token))
    chunks = client.get(f"/api/courses/{course_id}/chunks", headers=auth_headers(token))

    assert response.status_code == 204
    assert listed.json() == []
    assert chunks.json() == []
    assert not Path(storage_path).exists()


def test_delete_parsed_material_removes_chunks_and_vector_entries(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "parsed-delete", "parsed-delete@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))

    deleted_vectors = []
    deleted_graphs = []

    class RecordingVectorService(FakeVectorService):
        def delete_chunks(self, course_id, chunk_ids):
            deleted_vectors.append({"course_id": course_id, "chunk_ids": chunk_ids})

    class RecordingGraphStore:
        def delete_course_graph(self, user_id, course_id):
            deleted_graphs.append({"user_id": user_id, "course_id": course_id})

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "vector_service_cls", RecordingVectorService)
    monkeypatch.setattr(CourseService, "graph_store_cls", RecordingGraphStore)
    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )
        CourseService(db).process_material_by_id(1, course_id, material.id)
        material_id = material.id

    response = client.delete(
        f"/api/courses/{course_id}/materials/{material_id}",
        headers=auth_headers(token),
    )
    chunks = client.get(f"/api/courses/{course_id}/chunks", headers=auth_headers(token))

    assert response.status_code == 204
    assert chunks.json() == []
    assert deleted_vectors == [{"course_id": course_id, "chunk_ids": [1]}]
    assert deleted_graphs == [{"user_id": 1, "course_id": course_id}]


def test_delete_parsed_material_continues_when_vector_store_is_unavailable(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "offline-vector-delete", "offline-vector-delete@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)
    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )
        CourseService(db).process_material_by_id(1, course_id, material.id)
        material_id = material.id

    monkeypatch.setattr(CourseService, "vector_service_cls", OfflineVectorService)

    response = client.delete(
        f"/api/courses/{course_id}/materials/{material_id}",
        headers=auth_headers(token),
    )
    chunks = client.get(f"/api/courses/{course_id}/chunks", headers=auth_headers(token))
    materials = client.get(f"/api/courses/{course_id}/materials", headers=auth_headers(token))

    assert response.status_code == 204
    assert chunks.json() == []
    assert materials.json() == []


def test_rebuild_vector_index_retries_stale_indexing_materials(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "stale-indexing-retry", "stale-indexing-retry@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)
    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )
        CourseService(db).process_material_by_id(1, course_id, material.id)
        material.parse_status = "indexing"
        material.parse_error = "previous task was interrupted"
        db.commit()

    with client.app.state.testing_session_factory() as db:
        result = CourseService(db).rebuild_vector_index(1, course_id)
        material = db.scalar(select(CourseMaterial).where(CourseMaterial.course_id == course_id))

    assert result == {"course_id": course_id, "indexed_chunks": 1}
    assert material.parse_status == "parsed"
    assert material.parse_error == ""


def test_semantic_search_falls_back_to_mysql_chunks_when_vector_store_is_unavailable(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "offline-vector-search", "offline-vector-search@example.com")
    c_course_id = create_course(client, token, "C language")
    python_course_id = create_course(client, token, "Python language")

    with client.app.state.testing_session_factory() as db:
        c_material = CourseMaterial(
            course_id=c_course_id,
            user_id=1,
            filename="c.md",
            file_type="md",
            storage_path="c.md",
            size_bytes=10,
            parse_status="parsed",
        )
        python_material = CourseMaterial(
            course_id=python_course_id,
            user_id=1,
            filename="python.md",
            file_type="md",
            storage_path="python.md",
            size_bytes=10,
            parse_status="parsed",
        )
        db.add_all([c_material, python_material])
        db.flush()
        db.add_all(
            [
                KnowledgeChunk(
                    course_id=c_course_id,
                    material_id=c_material.id,
                    chunk_index=0,
                    source_locator="c-page-1",
                    heading="C 鎸囬拡",
                    content="C pointers, arrays, and memory addresses.",
                    token_count=20,
                    embedding_id="",
                ),
                KnowledgeChunk(
                    course_id=c_course_id,
                    material_id=c_material.id,
                    chunk_index=1,
                    source_locator="c-page-2",
                    heading="C 鍑芥暟",
                    content="Function definitions, parameter passing, and return values.",
                    token_count=20,
                    embedding_id="",
                ),
                KnowledgeChunk(
                    course_id=python_course_id,
                    material_id=python_material.id,
                    chunk_index=0,
                    source_locator="python-page-1",
                    heading="Python 鍑芥暟",
                    content="Python functions, parameters, and modular programming.",
                    token_count=20,
                    embedding_id="",
                ),
            ]
        )
        db.commit()

    monkeypatch.setattr(CourseService, "vector_service_cls", OfflineVectorService)

    response = client.get(
        f"/api/courses/{c_course_id}/semantic-search?q={quote('pointers')}",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["course_id"] == c_course_id
    assert payload[0]["source_locator"] == "c-page-1"
    assert "pointers" in payload[0]["content"]
    assert all(item["course_id"] == c_course_id for item in payload)


def test_rebuild_vector_index_endpoint_enqueues_background_reindex(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "reindex-owner", "reindex-owner@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))

    indexed_batches = []

    class RecordingVectorService(FakeVectorService):
        def upsert_chunks(self, course_id, chunks, **kwargs):
            indexed_batches.append({"course_id": course_id, "chunks": chunks})

    monkeypatch.setattr(CourseService, "vector_service_cls", RecordingVectorService)
    queue = NoopMaterialTaskQueue()
    client.app.state.material_task_queue = queue
    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )
        CourseService(db).process_material_by_id(1, course_id, material.id)
    indexed_batches.clear()

    response = client.post(f"/api/courses/{course_id}/vector-index/rebuild", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json() == {"course_id": course_id, "indexed_chunks": 1}
    assert indexed_batches == []
    assert queue.vector_rebuilds == [{"user_id": 1, "course_id": course_id}]


def test_rebuild_vector_index_marks_material_indexing_then_parsed(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "reindex-sync-owner", "reindex-sync-owner@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))

    statuses_seen = []

    class RecordingVectorService(FakeVectorService):
        def upsert_chunks(self, course_id, chunks, **kwargs):
            with client.app.state.testing_session_factory() as check_db:
                material = check_db.scalar(select(CourseMaterial).where(CourseMaterial.course_id == course_id))
                statuses_seen.append(material.parse_status)
            super().upsert_chunks(course_id, chunks, **kwargs)

    monkeypatch.setattr(CourseService, "vector_service_cls", RecordingVectorService)
    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )
        CourseService(db).process_material_by_id(1, course_id, material.id)
        statuses_seen.clear()
        material.parse_status = "index_failed"
        material.parse_error = "old failure"
        db.commit()

        result = CourseService(db).rebuild_vector_index(1, course_id)
        refreshed = db.scalar(select(CourseMaterial).where(CourseMaterial.id == material.id))

    assert result == {"course_id": course_id, "indexed_chunks": 1}
    assert statuses_seen == ["indexing"]
    assert refreshed.parse_status == "parsed"
    assert refreshed.parse_error == ""


def test_rebuild_vector_index_closes_vector_service(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "reindex-close-owner", "reindex-close-owner@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))

    class ClosingVectorService(FakeVectorService):
        closed_count = 0

    monkeypatch.setattr(CourseService, "vector_service_cls", ClosingVectorService)
    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )
        CourseService(db).process_material_by_id(1, course_id, material.id)
        material.parse_status = "index_failed"
        material.parse_error = "old failure"
        db.commit()

        CourseService(db).rebuild_vector_index(1, course_id)

    assert ClosingVectorService.closed_count == 2


def test_second_user_cannot_rebuild_first_users_vector_index(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    owner_token = register_user(client, "reindex-owner-2", "reindex-owner-2@example.com")
    other_token = register_user(client, "reindex-other", "reindex-other@example.com")
    course_id = create_course(client, owner_token)
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)

    response = client.post(f"/api/courses/{course_id}/vector-index/rebuild", headers=auth_headers(other_token))

    assert response.status_code == 404


def test_second_user_cannot_delete_first_users_material(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    owner_token = register_user(client, "delete-owner", "delete-owner@example.com")
    other_token = register_user(client, "delete-other", "delete-other@example.com")
    course_id = create_course(client, owner_token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)
    upload = client.post(
        f"/api/courses/{course_id}/materials",
        headers=auth_headers(owner_token),
        files={"file": ("lesson.pdf", b"fake pdf content", "application/pdf")},
    )

    response = client.delete(
        f"/api/courses/{course_id}/materials/{upload.json()['id']}",
        headers=auth_headers(other_token),
    )

    assert response.status_code == 404


def test_second_user_cannot_list_first_users_materials(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    owner_token = register_user(client, "material-owner", "material-owner@example.com")
    other_token = register_user(client, "material-other", "material-other@example.com")
    course_id = create_course(client, owner_token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)

    upload = client.post(
        f"/api/courses/{course_id}/materials",
        headers=auth_headers(owner_token),
        files={"file": ("lesson.pdf", b"fake pdf content", "application/pdf")},
    )
    listed = client.get(f"/api/courses/{course_id}/materials", headers=auth_headers(other_token))

    assert upload.status_code == 200
    assert listed.status_code == 404


def test_vector_failure_keeps_mysql_chunks_and_marks_material_index_failed(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "vector-failure", "vector-failure@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", RaisingVectorService)

    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )
        CourseService(db).process_material_by_id(1, course_id, material.id)
        materials = list(
            db.scalars(select(CourseMaterial).where(CourseMaterial.course_id == course_id))
        )
        chunks = list(db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.course_id == course_id)))

    assert len(materials) == 1
    assert materials[0].parse_status == "index_failed"
    assert "vector upsert failed" in materials[0].parse_error
    assert len(chunks) == 1


def test_upload_truncates_chunk_heading_to_fit_database_columns(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "long-heading", "long-heading@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(long_heading_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)

    with client.app.state.testing_session_factory() as db:
        material = CourseService(db).add_material(
            user_id=1,
            course_id=course_id,
            filename="lesson.pdf",
            content=b"fake pdf content",
        )
        CourseService(db).process_material_by_id(1, course_id, material.id)
    chunks_response = client.get(f"/api/courses/{course_id}/chunks", headers=auth_headers(token))

    assert chunks_response.status_code == 200
    assert len(chunks_response.json()[0]["heading"]) == 255


def test_upload_truncates_material_filename_to_fit_database_columns(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "long-filename", "long-filename@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)

    long_filename = f"{'a' * 300}.pdf"
    response = client.post(
        f"/api/courses/{course_id}/materials",
        headers=auth_headers(token),
        files={"file": (long_filename, b"fake pdf content", "application/pdf")},
    )

    assert response.status_code == 200
    assert len(response.json()["filename"]) == 255


def test_course_chunks_are_ordered_by_material_then_chunk_index(tmp_path):
    client = make_client(tmp_path)
    token = register_user(client, "chunk-order", "chunk-order@example.com")
    course_id = create_course(client, token, "C split textbook")

    with client.app.state.testing_session_factory() as db:
        first_material = CourseMaterial(
            course_id=course_id,
            user_id=1,
            filename="part1.pdf",
            file_type="pdf",
            storage_path="part1.pdf",
            size_bytes=10,
            parse_status="parsed",
        )
        second_material = CourseMaterial(
            course_id=course_id,
            user_id=1,
            filename="part2.pdf",
            file_type="pdf",
            storage_path="part2.pdf",
            size_bytes=10,
            parse_status="parsed",
        )
        db.add_all([first_material, second_material])
        db.flush()
        db.add_all(
            [
                KnowledgeChunk(
                    course_id=course_id,
                    material_id=first_material.id,
                    chunk_index=0,
                    source_locator="part1-page-1",
                    heading="part1 first",
                    content="first material first chunk",
                ),
                KnowledgeChunk(
                    course_id=course_id,
                    material_id=second_material.id,
                    chunk_index=0,
                    source_locator="part2-page-1",
                    heading="part2 first",
                    content="second material first chunk",
                ),
                KnowledgeChunk(
                    course_id=course_id,
                    material_id=first_material.id,
                    chunk_index=1,
                    source_locator="part1-page-2",
                    heading="part1 second",
                    content="first material second chunk",
                ),
            ]
        )
        db.commit()

    chunks = client.get(f"/api/courses/{course_id}/chunks", headers=auth_headers(token))

    assert chunks.status_code == 200
    assert [chunk["heading"] for chunk in chunks.json()] == [
        "part1 first",
        "part1 second",
        "part2 first",
    ]


def test_second_user_cannot_read_first_users_chunks_or_graph(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    owner_token = register_user(client, "chunk-owner", "chunk-owner@example.com")
    other_token = register_user(client, "chunk-other", "chunk-other@example.com")
    course_id = create_course(client, owner_token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)

    upload = client.post(
        f"/api/courses/{course_id}/materials",
        headers=auth_headers(owner_token),
        files={"file": ("lesson.pdf", b"fake pdf content", "application/pdf")},
    )
    chunks = client.get(f"/api/courses/{course_id}/chunks", headers=auth_headers(other_token))
    graph = client.get(f"/api/courses/{course_id}/knowledge-graph", headers=auth_headers(other_token))

    assert upload.status_code == 200
    assert chunks.status_code == 404
    assert graph.status_code == 404


def test_unbuilt_knowledge_graph_returns_empty_graph_without_neo4j_lookup(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "graph-empty", "graph-empty@example.com")
    course_id = create_course(client, token)

    class UnexpectedGraphStore:
        def __init__(self):
            raise AssertionError("graph store should not be opened before graph build succeeds")

    monkeypatch.setattr(CourseService, "graph_store_cls", UnexpectedGraphStore)

    graph = client.get(f"/api/courses/{course_id}/knowledge-graph", headers=auth_headers(token))

    assert graph.status_code == 200
    assert graph.json() == {"nodes": [], "edges": []}


def test_knowledge_graph_root_uses_course_name_when_stored_graph_uses_textbook_series(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "graph-root-course", "graph-root-course@example.com")
    course_name = "\u0043\u8bed\u8a00\u7a0b\u5e8f\u8bbe\u8ba1"
    textbook_series = "\u4e2d\u56fd\u9ad8\u7b49\u9662\u6821\u8ba1\u7b97\u673a\u57fa\u7840\u6559\u80b2\u8bfe\u7a0b\u4f53\u7cfb\u89c4\u5212\u6559\u6750"
    course_id = create_course(client, token, name=course_name)

    class FakeGraphStore:
        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            return {
                "nodes": [
                    {
                        "id": "chapter-1",
                        "name": "\u7b2c 1 \u7ae0 C \u8bed\u8a00\u6982\u8ff0",
                        "node_type": "chapter",
                        "level": 1,
                        "parent_id": "course-root",
                    },
                    {
                        "id": "course-root",
                        "name": textbook_series,
                        "node_type": "concept",
                        "level": 0,
                        "parent_id": "",
                        "summary": f"{textbook_series}\u7684\u8bfe\u7a0b\u77e5\u8bc6\u7ed3\u6784\u603b\u89c8\u3002",
                    },
                ],
                "edges": [{"source": "course-root", "target": "chapter-1", "relation_type": "contains"}],
            }

        def close(self):
            pass

    with client.app.state.testing_session_factory() as db:
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        db.commit()

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    graph = client.get(f"/api/courses/{course_id}/knowledge-graph", headers=auth_headers(token))

    assert graph.status_code == 200
    root_node = graph.json()["nodes"][0]
    assert root_node["id"] == "course-root"
    assert root_node["name"] == course_name
    assert course_name in root_node["summary"]
    assert textbook_series not in root_node["summary"]


def test_default_python_course_endpoint_creates_chunks_and_graph(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "python-default", "python-default@example.com")
    replaced_graphs = []

    class FakeGraphStore:
        graphs = {}

        def replace_course_graph(self, user_id, course_id, nodes, edges):
            replaced_graphs.append({"user_id": user_id, "course_id": course_id, "nodes": nodes, "edges": edges})
            self.graphs[(user_id, course_id)] = {"nodes": nodes, "edges": edges}

        def get_course_graph(self, user_id, course_id):
            return self.graphs.get((user_id, course_id), {"nodes": [], "edges": []})

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    response = client.post("/api/courses/default-python", headers=auth_headers(token))

    assert response.status_code == 200
    course = response.json()
    assert course["name"] == "Python 程序设计"
    assert "built-in:python" in course["description"]

    chunks = client.get(f"/api/courses/{course['id']}/chunks", headers=auth_headers(token))
    graph = client.get(f"/api/courses/{course['id']}/knowledge-graph", headers=auth_headers(token))

    assert chunks.status_code == 200
    assert len(chunks.json()) == len(DEFAULT_PYTHON_CHUNKS)
    assert graph.status_code == 200
    graph_payload = graph.json()
    assert len(graph_payload["nodes"]) == len(DEFAULT_PYTHON_NODES)
    assert len(graph_payload["edges"]) == len(DEFAULT_PYTHON_EDGES)
    assert {node["level"] for node in graph_payload["nodes"]} >= {0, 1, 2, 3}
    assert {node["id"] for node in graph_payload["nodes"]} >= {
        "course-root",
        "outline-chapter-1",
        "outline-section-1-2-1",
        "outline-section-3-2",
        "outline-section-6-2-7",
    }
    assert sum(1 for edge in graph_payload["edges"] if edge["relation_type"] == "contains") == len(
        DEFAULT_PYTHON_CONTAINS_EDGES
    )
    assert sum(1 for edge in graph_payload["edges"] if edge["relation_type"] == "prerequisite") == len(
        DEFAULT_PYTHON_PREREQUISITE_EDGES
    )
    assert replaced_graphs


def test_default_python_graph_keeps_sibling_outline_numbers_continuous(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "python-continuous", "python-continuous@example.com")

    class FakeGraphStore:
        graphs = {}

        def replace_course_graph(self, user_id, course_id, nodes, edges):
            self.graphs[(user_id, course_id)] = {"nodes": nodes, "edges": edges}

        def get_course_graph(self, user_id, course_id):
            return self.graphs.get((user_id, course_id), {"nodes": [], "edges": []})

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    response = client.post("/api/courses/default-python", headers=auth_headers(token))
    assert response.status_code == 200
    course = response.json()
    graph = client.get(f"/api/courses/{course['id']}/knowledge-graph", headers=auth_headers(token)).json()
    node_ids = {node["id"] for node in graph["nodes"]}

    missing_ids = []
    for node_id in sorted(node_ids):
        if not node_id.startswith("outline-section-"):
            continue
        suffix = node_id.removeprefix("outline-section-")
        parts = suffix.split("-")
        if len(parts) < 2:
            continue
        sibling_index = int(parts[-1])
        parent_prefix = "-".join(parts[:-1])
        for expected_index in range(1, sibling_index):
            expected_id = f"outline-section-{parent_prefix}-{expected_index}"
            if expected_id not in node_ids:
                missing_ids.append(expected_id)

    assert missing_ids == []


def test_default_c_course_endpoint_creates_chunks_and_graph(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "c-default", "c-default@example.com")
    replaced_graphs = []

    class FakeGraphStore:
        graphs = {}

        def replace_course_graph(self, user_id, course_id, nodes, edges):
            replaced_graphs.append({"user_id": user_id, "course_id": course_id, "nodes": nodes, "edges": edges})
            self.graphs[(user_id, course_id)] = {"nodes": nodes, "edges": edges}

        def get_course_graph(self, user_id, course_id):
            return self.graphs.get((user_id, course_id), {"nodes": [], "edges": []})

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    response = client.post("/api/courses/default-c", headers=auth_headers(token))

    assert response.status_code == 200
    course = response.json()
    assert course["name"] == "C语言程序设计"
    assert "built-in:c" in course["description"]

    chunks = client.get(f"/api/courses/{course['id']}/chunks", headers=auth_headers(token))
    graph = client.get(f"/api/courses/{course['id']}/knowledge-graph", headers=auth_headers(token))

    assert chunks.status_code == 200
    assert len(chunks.json()) >= 8
    assert graph.status_code == 200
    graph_payload = graph.json()
    assert graph_payload["nodes"][0]["id"] == "c-course-root"
    assert graph_payload["nodes"][0]["name"] == "C语言程序设计"
    assert any("指针" in node["name"] for node in graph_payload["nodes"])
    assert replaced_graphs


def test_builtin_knowledge_base_can_be_applied_to_existing_course(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "builtin-existing", "builtin-existing@example.com")
    course_id = create_course(client, token, "测试")
    replaced_graphs = []

    class FakeGraphStore:
        graphs = {}

        def replace_course_graph(self, user_id, course_id, nodes, edges):
            replaced_graphs.append({"user_id": user_id, "course_id": course_id, "nodes": nodes, "edges": edges})
            self.graphs[(user_id, course_id)] = {"nodes": nodes, "edges": edges}

        def get_course_graph(self, user_id, course_id):
            return self.graphs.get((user_id, course_id), {"nodes": [], "edges": []})

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    response = client.post(
        f"/api/courses/{course_id}/builtin-knowledge-base",
        headers=auth_headers(token),
        json={"template": "python"},
    )

    assert response.status_code == 200
    course = response.json()
    assert course["id"] == course_id
    assert course["name"] == "测试"
    assert "built-in:python" in course["description"]

    chunks = client.get(f"/api/courses/{course_id}/chunks", headers=auth_headers(token))
    graph = client.get(f"/api/courses/{course_id}/knowledge-graph", headers=auth_headers(token))
    courses = client.get("/api/courses", headers=auth_headers(token))

    assert chunks.status_code == 200
    assert len(chunks.json()) == len(DEFAULT_PYTHON_CHUNKS)
    assert all(chunk["course_id"] == course_id for chunk in chunks.json())
    assert graph.status_code == 200
    graph_payload = graph.json()
    assert graph_payload["nodes"][0]["name"] == "测试"
    assert replaced_graphs[-1]["course_id"] == course_id
    assert [item["name"] for item in courses.json()] == ["测试"]


def test_course_profile_endpoint_clones_legacy_account_profile_for_existing_course(tmp_path):
    client = make_client(tmp_path)
    token = register_user(client, "legacy-profile-owner", "legacy-profile-owner@example.com")
    course_id = create_course(client, token, "python")

    with client.app.state.testing_session_factory() as db:
        legacy_profile = confirm_profile_for_user(db, 1, course_id=None, learning_goal="学习Python")

    response = client.get(f"/api/profiles/me?course_id={course_id}", headers=auth_headers(token))

    assert response.status_code == 200
    assert response.json()["learning_goal"] == "学习Python"
    with client.app.state.testing_session_factory() as db:
        course_profile = db.scalar(
            select(StudentProfileRecord).where(
                StudentProfileRecord.user_id == 1,
                StudentProfileRecord.course_id == course_id,
            )
        )
        account_profile = db.scalar(
            select(StudentProfileRecord).where(
                StudentProfileRecord.user_id == 1,
                StudentProfileRecord.course_id.is_(None),
            )
        )
    assert course_profile is not None
    assert account_profile is not None
    assert course_profile.id != account_profile.id
    assert course_profile.profile_data["learning_goal"] == legacy_profile.learning_goal


def test_switching_builtin_knowledge_base_keeps_only_selected_template_chunks(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "builtin-switch", "builtin-switch@example.com")
    course_id = create_course(client, token, "语言程序设计")

    class FakeGraphStore:
        graphs = {}

        def replace_course_graph(self, user_id, course_id, nodes, edges):
            self.graphs[(user_id, course_id)] = {"nodes": nodes, "edges": edges}

        def get_course_graph(self, user_id, course_id):
            return self.graphs.get((user_id, course_id), {"nodes": [], "edges": []})

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    c_response = client.post(
        f"/api/courses/{course_id}/builtin-knowledge-base",
        headers=auth_headers(token),
        json={"template": "c"},
    )
    assert c_response.status_code == 200
    c_chunks = client.get(f"/api/courses/{course_id}/chunks", headers=auth_headers(token)).json()
    assert any(chunk["source_locator"].startswith("built-in-c:") for chunk in c_chunks)

    python_response = client.post(
        f"/api/courses/{course_id}/builtin-knowledge-base",
        headers=auth_headers(token),
        json={"template": "python"},
    )
    assert python_response.status_code == 200
    next_chunks = client.get(f"/api/courses/{course_id}/chunks", headers=auth_headers(token)).json()

    assert len(next_chunks) == len(DEFAULT_PYTHON_CHUNKS)
    assert all(chunk["source_locator"].startswith("built-in-python:") for chunk in next_chunks)


def test_delete_default_c_material_does_not_auto_restore_from_chunks_or_graph_reads(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "c-default-delete", "c-default-delete@example.com")

    class FakeGraphStore:
        graphs = {}
        replacements = []

        def replace_course_graph(self, user_id, course_id, nodes, edges):
            self.replacements.append({"user_id": user_id, "course_id": course_id, "nodes": nodes, "edges": edges})
            self.graphs[(user_id, course_id)] = {"nodes": nodes, "edges": edges}

        def get_course_graph(self, user_id, course_id):
            return self.graphs.get((user_id, course_id), {"nodes": [], "edges": []})

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)

    course = client.post("/api/courses/default-c", headers=auth_headers(token)).json()
    materials = client.get(f"/api/courses/{course['id']}/materials", headers=auth_headers(token)).json()
    material = next(item for item in materials if item["filename"] == DEFAULT_C_MATERIAL_FILENAME)

    response = client.delete(
        f"/api/courses/{course['id']}/materials/{material['id']}",
        headers=auth_headers(token),
    )
    chunks_after_delete = client.get(f"/api/courses/{course['id']}/chunks", headers=auth_headers(token))
    graph_after_delete = client.get(f"/api/courses/{course['id']}/knowledge-graph", headers=auth_headers(token))
    materials_after_reads = client.get(f"/api/courses/{course['id']}/materials", headers=auth_headers(token))

    assert response.status_code == 204
    assert chunks_after_delete.status_code == 200
    assert chunks_after_delete.json() == []
    assert graph_after_delete.status_code == 200
    assert graph_after_delete.json() == {"nodes": [], "edges": []}
    assert materials_after_reads.json() == []


def test_uploading_custom_c_split_materials_disables_builtin_auto_restore(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "c-custom-split", "c-custom-split@example.com")

    class FakeGraphStore:
        graphs = {}

        def replace_course_graph(self, user_id, course_id, nodes, edges):
            self.graphs[(user_id, course_id)] = {"nodes": nodes, "edges": edges}

        def get_course_graph(self, user_id, course_id):
            return self.graphs.get((user_id, course_id), {"nodes": [], "edges": []})

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    course = client.post("/api/courses/default-c", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        service = CourseService(db)
        first = service.add_material(1, course["id"], "C程序设计_part1_p001-p200.pdf", b"%PDF-1")
        second = service.add_material(1, course["id"], "C程序设计_part2_p201-p395.pdf", b"%PDF-2")
        db.add_all(
            [
                KnowledgeChunk(
                    course_id=course["id"],
                    material_id=first.id,
                    chunk_index=0,
                    source_locator="part1 page 1",
                    heading="目录",
                    content=(
                        "目录 第1章 程序设计和C语言 1 "
                        "1.2 什么是计算机语言 5 "
                        "1.2.1 计算机语言的发展 6 "
                        "1.2.2 C语言的特点 8"
                    ),
                    token_count=80,
                    embedding_id="custom-c-part-1",
                ),
                KnowledgeChunk(
                    course_id=course["id"],
                    material_id=second.id,
                    chunk_index=0,
                    source_locator="part2 page 1",
                    heading="目录",
                    content=(
                        "目录 第6章 数组 201 "
                        "6.1 怎样定义和引用一维数组 202 "
                        "6.1.1 怎样定义一维数组 203 "
                        "6.1.2 怎样引用一维数组元素 205"
                    ),
                    token_count=80,
                    embedding_id="custom-c-part-2",
                ),
            ]
        )
        db.add(GraphBuildJob(course_id=course["id"], status="succeeded", current_stage="done", progress=100))
        db.commit()

    chunks = client.get(f"/api/courses/{course['id']}/chunks", headers=auth_headers(token))
    materials = client.get(f"/api/courses/{course['id']}/materials", headers=auth_headers(token))
    graph = client.get(f"/api/courses/{course['id']}/knowledge-graph", headers=auth_headers(token))

    assert chunks.status_code == 200
    source_locators = {chunk["source_locator"] for chunk in chunks.json()}
    assert source_locators == {"part1 page 1", "part2 page 1"}
    assert all(not chunk["source_locator"].startswith("built-in-c:") for chunk in chunks.json())

    assert materials.status_code == 200
    assert {material["filename"] for material in materials.json()} == {
        "C程序设计_part1_p001-p200.pdf",
        "C程序设计_part2_p201-p395.pdf",
    }

    assert graph.status_code == 200
    node_ids = {node["id"] for node in graph.json()["nodes"]}
    assert {"outline-section-1-2-1", "outline-section-6-1-1"} <= node_ids


def test_default_python_course_endpoint_is_idempotent_per_user(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "python-idempotent", "python-idempotent@example.com")

    class FakeGraphStore:
        def replace_course_graph(self, user_id, course_id, nodes, edges):  # noqa: ARG002
            pass

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    first = client.post("/api/courses/default-python", headers=auth_headers(token))
    second = client.post("/api/courses/default-python", headers=auth_headers(token))
    courses = client.get("/api/courses", headers=auth_headers(token))

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert [course["name"] for course in courses.json()].count("Python 程序设计") == 1


def test_default_python_graph_read_upgrades_existing_compact_seed(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "python-upgrade", "python-upgrade@example.com")
    replaced_graphs = []

    class FakeGraphStore:
        graphs = {}

        def replace_course_graph(self, user_id, course_id, nodes, edges):
            replaced_graphs.append({"user_id": user_id, "course_id": course_id, "nodes": nodes, "edges": edges})
            self.graphs[(user_id, course_id)] = {"nodes": nodes, "edges": edges}

        def get_course_graph(self, user_id, course_id):
            return self.graphs.get(
                (user_id, course_id),
                {"nodes": [{"id": "py-root", "name": "stale compact root"}], "edges": []},
            )

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    created = client.post("/api/courses/default-python", headers=auth_headers(token)).json()
    with client.app.state.testing_session_factory() as db:
        material = db.scalar(
            select(CourseMaterial).where(
                CourseMaterial.course_id == created["id"],
                CourseMaterial.storage_path == DEFAULT_PYTHON_MATERIAL_STORAGE_PATH,
            )
        )
        assert material is not None
        stale_chunks = list(
            db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.course_id == created["id"], KnowledgeChunk.material_id == material.id)
                .order_by(KnowledgeChunk.id.asc())
            )
        )
        for chunk in stale_chunks[48:]:
            db.delete(chunk)
        db.commit()

    graph = client.get(f"/api/courses/{created['id']}/knowledge-graph", headers=auth_headers(token))
    chunks = client.get(f"/api/courses/{created['id']}/chunks", headers=auth_headers(token))

    assert graph.status_code == 200
    graph_payload = graph.json()
    assert len(graph_payload["nodes"]) == len(DEFAULT_PYTHON_NODES)
    assert len(graph_payload["edges"]) == len(DEFAULT_PYTHON_EDGES)
    assert {node["id"] for node in graph_payload["nodes"]} >= {
        "outline-section-1-2-1",
        "outline-section-3-2-2",
        "outline-section-8-3",
    }
    assert len(chunks.json()) == len(DEFAULT_PYTHON_CHUNKS)
    assert len(replaced_graphs) >= 2


def test_knowledge_graph_read_repairs_missing_outline_nodes_from_chunks(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "graph-outline-repair", "graph-outline-repair@example.com")
    course_id = create_course(client, token, name="Python 绋嬪簭璁捐")

    with client.app.state.testing_session_factory() as db:
        material = CourseMaterial(
            course_id=course_id,
            user_id=1,
            filename="python.pdf",
            file_type="pdf",
            storage_path="python.pdf",
            size_bytes=100,
            parse_status="parsed",
        )
        db.add(material)
        db.flush()
        db.add_all(
            [
                KnowledgeChunk(
                    course_id=course_id,
                    material_id=material.id,
                    chunk_index=0,
                    source_locator="page 1",
                    heading="鐩綍",
                    content=(
                        "鐩綍 绗?1 绔?Python 姒傝堪 1 "
                        "1.2 Python 鐗堟湰鍜屽紑鍙戠幆澧?2 "
                        "1.2.1 Python 璇█鐨勭増鏈?2 "
                        "1.2.2 Python 鐨勯泦鎴愬紑鍙戠幆澧?3"
                    ),
                    token_count=80,
                    embedding_id="chunk-outline",
                ),
                KnowledgeChunk(
                    course_id=course_id,
                    material_id=material.id,
                    chunk_index=1,
                    source_locator="page 15",
                    heading="2. 绉戝璁＄畻",
                    content=(
                        "1.2 Python 鐗堟湰鍜屽紑鍙戠幆澧?"
                        "1.2.1 Python 璇█鐨勭増鏈?Python 璇█鐢?Guido van Rossum 璁捐銆?"
                        "1.2.2 Python IDE common environments include IDLE and Anaconda."
                    ),
                    token_count=80,
                    embedding_id="chunk-body",
                ),
            ]
        )
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        db.commit()

    replacements = []

    class FakeGraphStore:
        graph = {
            "nodes": [
                {
                    "id": "course-root",
                    "name": "Python 绋嬪簭璁捐",
                    "node_type": "concept",
                    "difficulty": "basic",
                    "summary": "old graph",
                    "source_chunk_ids": [],
                    "confidence": 0.8,
                    "level": 0,
                    "order": 0,
                    "parent_id": "",
                },
                {
                    "id": "outline-chapter-1",
                    "name": "绗?1 绔?Python 姒傝堪",
                    "node_type": "concept",
                    "difficulty": "basic",
                    "summary": "old chapter",
                    "source_chunk_ids": [],
                    "confidence": 0.8,
                    "level": 1,
                    "order": 1,
                    "parent_id": "course-root",
                },
                {
                    "id": "outline-section-1-2",
                    "name": "1.2 Python version and development environment",
                    "node_type": "concept",
                    "difficulty": "basic",
                    "summary": "old section",
                    "source_chunk_ids": [],
                    "confidence": 0.8,
                    "level": 2,
                    "order": 2,
                    "parent_id": "outline-chapter-1",
                },
                {
                    "id": "outline-section-1-2-2",
                    "name": "1.2.2 Python IDE",
                    "node_type": "tool",
                    "difficulty": "intermediate",
                    "summary": "old level three node",
                    "source_chunk_ids": [],
                    "confidence": 0.8,
                    "level": 3,
                    "order": 3,
                    "parent_id": "outline-section-1-2",
                },
            ],
            "edges": [
                {
                    "id": "contains-course-root-outline-chapter-1",
                    "source_node_id": "course-root",
                    "target_node_id": "outline-chapter-1",
                    "relation_type": "contains",
                    "reason": "old relation",
                    "confidence": 0.8,
                }
            ],
        }

        def replace_course_graph(self, user_id, course_id, nodes, edges):  # noqa: ARG002
            replacements.append({"nodes": nodes, "edges": edges})
            self.graph = {"nodes": nodes, "edges": edges}

        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            return self.graph

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    graph = client.get(f"/api/courses/{course_id}/knowledge-graph", headers=auth_headers(token))

    assert graph.status_code == 200
    node_ids = {node["id"] for node in graph.json()["nodes"]}
    assert {"outline-section-1-2-1", "outline-section-1-2-2"} <= node_ids
    assert replacements


def test_second_user_cannot_access_default_python_course(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    owner_token = register_user(client, "python-owner", "python-owner@example.com")
    other_token = register_user(client, "python-other", "python-other@example.com")

    class FakeGraphStore:
        def replace_course_graph(self, user_id, course_id, nodes, edges):  # noqa: ARG002
            pass

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    created = client.post("/api/courses/default-python", headers=auth_headers(owner_token))
    course_id = created.json()["id"]

    other_get = client.get(f"/api/courses/{course_id}", headers=auth_headers(other_token))
    other_chunks = client.get(f"/api/courses/{course_id}/chunks", headers=auth_headers(other_token))
    other_graph = client.get(f"/api/courses/{course_id}/knowledge-graph", headers=auth_headers(other_token))

    assert other_get.status_code == 404
    assert other_chunks.status_code == 404
    assert other_graph.status_code == 404


def test_knowledge_graph_nodes_include_default_mastery_status(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "graph-default-mastery", "graph-default-mastery@example.com")
    course_id = create_course(client, token)

    class FakeGraphStore:
        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            return {
                "nodes": [{"id": "n1", "name": "Gradient descent", "node_type": "concept"}],
                "edges": [],
            }

        def close(self):
            pass

    with client.app.state.testing_session_factory() as db:
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        confirm_profile_for_user(db, 1, course_id=course_id)
        db.commit()

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    graph = client.get(f"/api/courses/{course_id}/knowledge-graph", headers=auth_headers(token))

    assert graph.status_code == 200
    assert graph.json()["nodes"][0]["mastery_status"] == "not_started"
    assert "mastery_score" not in graph.json()["nodes"][0]


def test_assessment_updates_knowledge_graph_node_mastery(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "graph-mastery", "graph-mastery@example.com")
    course_id = create_course(client, token)

    class FakeGraphStore:
        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            return {
                "nodes": [{"id": "n1", "name": "Gradient descent", "node_type": "concept"}],
                "edges": [],
            }

        def close(self):
            pass

    with client.app.state.testing_session_factory() as db:
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        confirm_profile_for_user(db, 1, course_id=course_id)
        db.commit()

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)

    assessment = client.post(
        "/api/assessments/submit",
        headers=auth_headers(token),
        json={
            "student_id": "student-xm",
            "event_type": "exercise_submitted",
            "topic": "Gradient descent",
            "course_id": course_id,
            "knowledge_node_id": "n1",
            "score": 0.45,
            "detail": "learning rate鍒ゆ柇閿欒",
        },
    )
    graph = client.get(f"/api/courses/{course_id}/knowledge-graph", headers=auth_headers(token))

    assert assessment.status_code == 200
    node = graph.json()["nodes"][0]
    assert node["mastery_status"] == "severe_weak"
    assert node["mastery_score"] == 0.45


def test_assessment_updates_confirmed_profile_and_dynamic_path_basis(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "assessment-profile", "assessment-profile@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()
    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course["id"], weak_points=["鍑芥暟"], knowledge_graph_focus=["鍑芥暟"])

    response = client.post(
        "/api/assessments/submit",
        headers=auth_headers(token),
        json={
            "student_id": "user-1",
            "event_type": "exercise_submitted",
            "topic": "1.1 鍒濊瘑 Python",
            "course_id": course["id"],
            "knowledge_node_id": "outline-section-1-1",
            "score": 0.42,
            "detail": "璇惧爞娴嬭瘯涓病鏈夊垎娓呰В閲婂瀷璇█鍜岀紪璇戝瀷璇█",
        },
    )
    path = client.post(
        f"/api/courses/{course['id']}/learning-paths/plan",
        headers=auth_headers(token),
        json={"plan_type": "remedial", "focus_node_id": "outline-section-1-1"},
    )

    assert response.status_code == 200
    with client.app.state.testing_session_factory() as db:
        record = db.query(StudentProfileRecord).filter(StudentProfileRecord.user_id == 1).one()
        profile = StudentProfile(**record.profile_data)
    assert "1.1 鍒濊瘑 Python" in profile.weak_points
    assert "1.1 鍒濊瘑 Python" in profile.knowledge_graph_focus
    assert path.status_code == 200
    assert path.json()["plan_type"] == "remedial"
    assert path.json()["focus_node_id"] == "outline-section-1-1"


def test_course_learning_path_uses_graph_profile_and_mastery(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-user", "path@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course["id"])

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["course_id"] == course["id"]
    assert payload["student_id"] == "user-1"
    assert payload["is_dynamic"] is True
    assert payload["adjustment_basis"]
    assert payload["stages"]
    first = payload["stages"][0]
    assert first["node_id"]
    assert first["topic"]
    assert first["mastery_status"] in {"not_started", "severe_weak", "basic", "good", "proficient"}
    assert first["graph_basis"]
    assert first["profile_basis"]
    assert first["recommended_resource_types"]
    assert first["recommendation_reason"]


def test_course_learning_path_stays_in_active_chapter_until_it_is_complete(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-active-chapter", "path-active-chapter@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course["id"])

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    ids = [stage["node_id"] for stage in response.json()["stages"]]
    assert ids
    assert all(node_id == "outline-chapter-1" or node_id.startswith("outline-section-1-") for node_id in ids)
    assert "outline-chapter-2" not in ids
    assert not any(node_id.startswith("outline-section-2-") for node_id in ids)


def test_course_learning_path_excludes_chapter_heading_from_learning_tasks(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-no-heading-task", "path-no-heading-task@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course["id"])

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_chapter_id"] == "outline-chapter-1"
    assert payload["active_chapter_title"]
    assert payload["stages"]
    assert all(stage["level"] > 1 for stage in payload["stages"])
    assert "outline-chapter-1" not in [stage["node_id"] for stage in payload["stages"]]
    assert payload["current_stage_id"] != "outline-chapter-1"


def test_course_learning_path_excludes_section_heading_from_learning_tasks(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-no-section-heading", "path-no-section-heading@example.com")

    class SectionHeadingGraphStore:
        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            return {
                "nodes": [
                    {
                        "id": "chapter-1",
                        "name": "Chapter 1 Python",
                        "node_type": "chapter",
                        "level": 1,
                        "order": 1,
                        "parent_id": "",
                    },
                    {
                        "id": "section-1-1",
                        "name": "1.1 鐎涳缚绡勭痪顖氬彠",
                        "node_type": "section",
                        "level": 2,
                        "order": 1,
                        "parent_id": "chapter-1",
                    },
                    {
                        "id": "concept-1-1-1",
                        "name": "1.1.1 Python concept",
                        "node_type": "concept",
                        "level": 3,
                        "order": 2,
                        "parent_id": "section-1-1",
                    },
                ],
                "edges": [],
            }

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", SectionHeadingGraphStore)
    course_id = create_course(client, token)
    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course_id)
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        db.commit()

    response = client.post(f"/api/courses/{course_id}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    stage_ids = [stage["node_id"] for stage in response.json()["stages"]]
    assert stage_ids == ["concept-1-1-1"]


def test_course_learning_path_uses_leaf_nodes_as_learning_tasks(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-leaf-tasks", "path-leaf-tasks@example.com")

    class LeafGraphStore:
        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            return {
                "nodes": [
                    {
                        "id": "chapter-1",
                        "name": "Chapter 1",
                        "node_type": "chapter",
                        "level": 1,
                        "order": 1,
                        "parent_id": "",
                    },
                    {
                        "id": "section-1-1",
                        "name": "1.1 Initial Python",
                        "node_type": "concept",
                        "level": 2,
                        "order": 1,
                        "parent_id": "chapter-1",
                    },
                    {
                        "id": "concept-1-1-1",
                        "name": "1.1.1 Python introduction",
                        "node_type": "concept",
                        "level": 3,
                        "order": 1,
                        "parent_id": "section-1-1",
                    },
                    {
                        "id": "concept-1-1-2",
                        "name": "1.1.2 Python application fields",
                        "node_type": "concept",
                        "level": 3,
                        "order": 2,
                        "parent_id": "section-1-1",
                    },
                    {
                        "id": "section-1-2",
                        "name": "1.2 Leaf section without lower-level concepts",
                        "node_type": "section",
                        "level": 2,
                        "order": 2,
                        "parent_id": "chapter-1",
                    },
                ],
                "edges": [
                    {"source_node_id": "chapter-1", "target_node_id": "section-1-1", "relation_type": "contains"},
                    {"source_node_id": "section-1-1", "target_node_id": "concept-1-1-1", "relation_type": "contains"},
                    {"source_node_id": "section-1-1", "target_node_id": "concept-1-1-2", "relation_type": "contains"},
                    {"source_node_id": "chapter-1", "target_node_id": "section-1-2", "relation_type": "contains"},
                ],
            }

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", LeafGraphStore)
    course_id = create_course(client, token)
    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course_id)
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        db.commit()

    response = client.post(f"/api/courses/{course_id}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    stage_ids = [stage["node_id"] for stage in response.json()["stages"]]
    assert stage_ids == ["concept-1-1-1", "concept-1-1-2", "section-1-2"]
    assert "section-1-1" not in stage_ids


def test_course_learning_path_places_failed_leaf_remediation_before_next_mainline_task(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-remedial-leaf-order", "path-remedial-leaf-order@example.com")

    class RemedialLeafGraphStore:
        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            return {
                "nodes": [
                    {
                        "id": "chapter-1",
                        "name": "Chapter 1",
                        "node_type": "chapter",
                        "level": 1,
                        "order": 1,
                        "parent_id": "",
                    },
                    {
                        "id": "section-1-1",
                        "name": "1.1 Initial Python",
                        "node_type": "concept",
                        "level": 2,
                        "order": 1,
                        "parent_id": "chapter-1",
                    },
                    {
                        "id": "concept-a",
                        "name": "1.1.1 Knowledge A",
                        "node_type": "concept",
                        "level": 3,
                        "order": 1,
                        "parent_id": "section-1-1",
                    },
                    {
                        "id": "concept-b",
                        "name": "1.1.2 Knowledge B",
                        "node_type": "concept",
                        "level": 3,
                        "order": 2,
                        "parent_id": "section-1-1",
                    },
                    {
                        "id": "concept-c",
                        "name": "1.1.3 Knowledge C",
                        "node_type": "concept",
                        "level": 3,
                        "order": 3,
                        "parent_id": "section-1-1",
                    },
                    {
                        "id": "section-1-2",
                        "name": "1.2 Next section",
                        "node_type": "concept",
                        "level": 2,
                        "order": 2,
                        "parent_id": "chapter-1",
                    },
                    {
                        "id": "concept-next",
                        "name": "1.2.1 Next mainline task",
                        "node_type": "concept",
                        "level": 3,
                        "order": 1,
                        "parent_id": "section-1-2",
                    },
                ],
                "edges": [
                    {"source_node_id": "chapter-1", "target_node_id": "section-1-1", "relation_type": "contains"},
                    {"source_node_id": "section-1-1", "target_node_id": "concept-a", "relation_type": "contains"},
                    {"source_node_id": "section-1-1", "target_node_id": "concept-b", "relation_type": "contains"},
                    {"source_node_id": "section-1-1", "target_node_id": "concept-c", "relation_type": "contains"},
                    {"source_node_id": "chapter-1", "target_node_id": "section-1-2", "relation_type": "contains"},
                    {"source_node_id": "section-1-2", "target_node_id": "concept-next", "relation_type": "contains"},
                ],
            }

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", RemedialLeafGraphStore)
    course_id = create_course(client, token)
    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course_id)
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        service = CourseService(db)
        service.upsert_node_mastery(1, course_id, "concept-a", "1.1.1 Knowledge A", 0.92, "passed")
        service.upsert_node_mastery(1, course_id, "concept-b", "1.1.2 Knowledge B", 0.88, "passed")
        service.upsert_node_mastery(1, course_id, "concept-c", "1.1.3 Knowledge C", 0.42, "failed")
        db.commit()

    response = client.post(f"/api/courses/{course_id}/learning-paths/plan", headers=auth_headers(token))
    remedial_response = client.post(
        f"/api/courses/{course_id}/learning-paths/plan",
        headers=auth_headers(token),
        json={"plan_type": "remedial", "focus_node_id": "concept-c"},
    )

    assert response.status_code == 200
    payload = response.json()
    stage_ids = [stage["node_id"] for stage in payload["stages"]]
    assert stage_ids == ["concept-a", "concept-b", "concept-c", "concept-c::remedial::assessment-weakness", "concept-next"]
    assert payload["current_stage_id"] == "concept-c::remedial::assessment-weakness"
    assert next(stage for stage in payload["stages"] if stage["node_id"] == "concept-a")["path_status"] == "passed"
    assert next(stage for stage in payload["stages"] if stage["node_id"] == "concept-b")["path_status"] == "passed"
    failed_stage = next(stage for stage in payload["stages"] if stage["node_id"] == "concept-c")
    assert failed_stage["is_remedial"] is True
    remedial_stage = next(stage for stage in payload["stages"] if stage["node_id"] == "concept-c::remedial::assessment-weakness")
    assert remedial_stage["is_current"] is True
    assert remedial_stage["is_remedial"] is True
    assert stage_ids.index("concept-c") < stage_ids.index("concept-c::remedial::assessment-weakness") < stage_ids.index("concept-next")

    assert remedial_response.status_code == 200
    remedial_payload = remedial_response.json()
    remedial_ids = [stage["node_id"] for stage in remedial_payload["stages"]]
    assert remedial_ids == ["concept-a", "concept-b", "concept-c", "concept-c::remedial::assessment-weakness", "concept-next"]
    assert remedial_payload["current_stage_id"] == "concept-c::remedial::assessment-weakness"


def test_course_learning_path_inserts_assessment_weakness_stage_after_failed_leaf(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-remedial-weakness-stage", "path-remedial-weakness-stage@example.com")

    class WeaknessGraphStore:
        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            return {
                "nodes": [
                    {
                        "id": "chapter-1",
                        "name": "Chapter 1",
                        "node_type": "chapter",
                        "level": 1,
                        "order": 1,
                        "parent_id": "",
                    },
                    {
                        "id": "section-1-1",
                        "name": "1.1 Initial Python",
                        "node_type": "section",
                        "level": 2,
                        "order": 1,
                        "parent_id": "chapter-1",
                    },
                    {
                        "id": "concept-a",
                        "name": "1.1.1 Python language features",
                        "node_type": "concept",
                        "level": 3,
                        "order": 1,
                        "parent_id": "section-1-1",
                    },
                    {
                        "id": "concept-b",
                        "name": "1.1.2 Python application fields",
                        "node_type": "concept",
                        "level": 3,
                        "order": 2,
                        "parent_id": "section-1-1",
                    },
                ],
                "edges": [
                    {"source_node_id": "chapter-1", "target_node_id": "section-1-1", "relation_type": "contains"},
                    {"source_node_id": "section-1-1", "target_node_id": "concept-a", "relation_type": "contains"},
                    {"source_node_id": "section-1-1", "target_node_id": "concept-b", "relation_type": "contains"},
                ],
            }

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", WeaknessGraphStore)
    course_id = create_course(client, token)
    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course_id)
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        CourseService(db).upsert_node_mastery(
            1,
            course_id,
            "concept-a",
            "1.1.1 Python language features",
            0.52,
            json.dumps(
                {
                    "assessment_type": "comprehensive",
                    "feedback": [
                        "选择题薄弱维度：概念理解。",
                        "编程题未通过，需要继续完成可运行代码并匹配预期输出。",
                    ],
                    "dimension_scores": {"quiz": 0.5, "code": 0.25, "behavior": 0.67},
                },
                ensure_ascii=False,
            ),
        )
        db.commit()

    response = client.post(
        f"/api/courses/{course_id}/learning-paths/plan",
        headers=auth_headers(token),
        json={"plan_type": "remedial", "focus_node_id": "concept-a"},
    )

    assert response.status_code == 200
    payload = response.json()
    stage_ids = [stage["node_id"] for stage in payload["stages"]]
    assert stage_ids[:3] == ["concept-a", "concept-a::remedial::assessment-weakness", "concept-b"]
    assert payload["current_stage_id"] == "concept-a::remedial::assessment-weakness"
    remedial_stage = payload["stages"][1]
    assert remedial_stage["is_remedial"] is True
    assert remedial_stage["path_status"] == "current"
    assert "薄弱点专项" in remedial_stage["topic"]
    assert "编程题未通过" in remedial_stage["goal"]
    assert "concept-a" in remedial_stage["graph_basis"][0]


def test_course_learning_path_main_refresh_keeps_assessment_weakness_stage_for_basic_mastery(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-main-weakness-refresh", "path-main-weakness-refresh@example.com")

    class WeaknessRefreshGraphStore:
        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            return {
                "nodes": [
                    {
                        "id": "chapter-1",
                        "name": "Chapter 1",
                        "node_type": "chapter",
                        "level": 1,
                        "order": 1,
                        "parent_id": "",
                    },
                    {
                        "id": "section-1-1",
                        "name": "1.1 Initial Python",
                        "node_type": "section",
                        "level": 2,
                        "order": 1,
                        "parent_id": "chapter-1",
                    },
                    {
                        "id": "concept-a",
                        "name": "1.1.1 Python language features",
                        "node_type": "concept",
                        "level": 3,
                        "order": 1,
                        "parent_id": "section-1-1",
                    },
                    {
                        "id": "concept-b",
                        "name": "1.1.2 Python application fields",
                        "node_type": "concept",
                        "level": 3,
                        "order": 2,
                        "parent_id": "section-1-1",
                    },
                ],
                "edges": [
                    {"source_node_id": "chapter-1", "target_node_id": "section-1-1", "relation_type": "contains"},
                    {"source_node_id": "section-1-1", "target_node_id": "concept-a", "relation_type": "contains"},
                    {"source_node_id": "section-1-1", "target_node_id": "concept-b", "relation_type": "contains"},
                ],
            }

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", WeaknessRefreshGraphStore)
    course_id = create_course(client, token)
    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course_id)
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        CourseService(db).upsert_node_mastery(
            1,
            course_id,
            "concept-a",
            "1.1.1 Python language features",
            0.7,
            json.dumps(
                {
                    "assessment_type": "comprehensive",
                    "feedback": ["code practice did not meet the target"],
                    "dimension_scores": {"quiz": 0.72, "code": 0.4, "behavior": 0.8},
                }
            ),
        )
        db.commit()

    response = client.post(f"/api/courses/{course_id}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    stage_ids = [stage["node_id"] for stage in payload["stages"]]
    assert stage_ids[:3] == ["concept-a", "concept-a::remedial::assessment-weakness", "concept-b"]
    assert payload["current_stage_id"] == "concept-a::remedial::assessment-weakness"
    source_stage = next(stage for stage in payload["stages"] if stage["node_id"] == "concept-a")
    remedial_stage = next(stage for stage in payload["stages"] if stage["node_id"] == "concept-a::remedial::assessment-weakness")
    assert source_stage["mastery_status"] == "basic"
    assert source_stage["path_status"] != "passed"
    assert remedial_stage["is_current"] is True
    assert remedial_stage["is_remedial"] is True
    assert remedial_stage["path_status"] == "current"


def test_course_learning_path_main_refresh_inserts_generic_weakness_stage_without_assessment_detail(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-main-generic-weakness", "path-main-generic-weakness@example.com")

    class GenericWeaknessGraphStore:
        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            return {
                "nodes": [
                    {
                        "id": "chapter-1",
                        "name": "Chapter 1",
                        "node_type": "chapter",
                        "level": 1,
                        "order": 1,
                        "parent_id": "",
                    },
                    {
                        "id": "concept-a",
                        "name": "1.1.1 Python language features",
                        "node_type": "concept",
                        "level": 2,
                        "order": 1,
                        "parent_id": "chapter-1",
                    },
                    {
                        "id": "concept-b",
                        "name": "1.1.2 Python application fields",
                        "node_type": "concept",
                        "level": 2,
                        "order": 2,
                        "parent_id": "chapter-1",
                    },
                ],
                "edges": [
                    {"source_node_id": "chapter-1", "target_node_id": "concept-a", "relation_type": "contains"},
                    {"source_node_id": "chapter-1", "target_node_id": "concept-b", "relation_type": "contains"},
                ],
            }

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", GenericWeaknessGraphStore)
    course_id = create_course(client, token)
    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course_id)
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        CourseService(db).upsert_node_mastery(
            1,
            course_id,
            "concept-a",
            "1.1.1 Python language features",
            0.45,
            "classroom assessment failed",
        )
        db.commit()

    response = client.post(f"/api/courses/{course_id}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    stage_ids = [stage["node_id"] for stage in payload["stages"]]
    assert stage_ids[:3] == ["concept-a", "concept-a::remedial::assessment-weakness", "concept-b"]
    remedial_stage = next(stage for stage in payload["stages"] if stage["node_id"] == "concept-a::remedial::assessment-weakness")
    assert remedial_stage["is_remedial"] is True
    assert remedial_stage["is_current"] is True
    assert "Python language features" in remedial_stage["goal"]


def test_course_learning_path_counts_only_learning_task_nodes_for_chapter_completion(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-section-complete", "path-section-complete@example.com")

    class SectionHeadingGraphStore:
        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            return {
                "nodes": [
                    {
                        "id": "chapter-1",
                        "name": "Chapter 1",
                        "node_type": "chapter",
                        "level": 1,
                        "order": 1,
                        "parent_id": "",
                    },
                    {
                        "id": "section-1-1",
                        "name": "1.1 Heading",
                        "node_type": "section",
                        "level": 2,
                        "order": 1,
                        "parent_id": "chapter-1",
                    },
                    {
                        "id": "concept-1-1-1",
                        "name": "1.1.1 Concrete concept",
                        "node_type": "concept",
                        "level": 3,
                        "order": 2,
                        "parent_id": "section-1-1",
                    },
                    {
                        "id": "chapter-2",
                        "name": "Chapter 2",
                        "node_type": "chapter",
                        "level": 1,
                        "order": 2,
                        "parent_id": "",
                    },
                    {
                        "id": "concept-2-1",
                        "name": "2.1 Next concept",
                        "node_type": "concept",
                        "level": 2,
                        "order": 1,
                        "parent_id": "chapter-2",
                    },
                ],
                "edges": [],
            }

        def close(self):
            pass

    monkeypatch.setattr(CourseService, "graph_store_cls", SectionHeadingGraphStore)
    course_id = create_course(client, token)
    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course_id)
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        CourseService(db).upsert_node_mastery(1, course_id, "concept-1-1-1", "1.1.1 Concrete concept", 0.92, "passed")
        db.commit()

    response = client.post(f"/api/courses/{course_id}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_chapter_id"] == "chapter-2"
    first_chapter = next(chapter for chapter in payload["chapters"] if chapter["id"] == "chapter-1")
    assert first_chapter["total_nodes"] == 1
    assert first_chapter["completed_nodes"] == 1
    assert first_chapter["is_complete"] is True


def test_course_learning_path_respects_weekend_one_hour_profile_budget(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-weekend-budget", "path-weekend-budget@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course["id"], time_preference="一周1小时学习时间，周末才有空进行学习")

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["weekly_time_budget_minutes"] == 60
    assert payload["planned_minutes"] == 60
    assert payload["schedule_days"] == ["周六", "周日"]
    assert "周末" in payload["schedule_summary"]
    assert sum(stage["scheduled_minutes"] for stage in payload["stages"] if stage["is_minimum_task"]) == 60
    assert {
        stage["scheduled_day"]
        for stage in payload["stages"]
        if stage["task_type"] == "minimum"
    } <= {"周六", "周日"}


def test_course_learning_path_respects_daily_one_hour_profile_with_weekend_included(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-daily-budget", "path-daily-budget@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course["id"], time_preference="daily 1 hour with weekend")

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["weekly_time_budget_minutes"] == 420
    assert payload["planned_minutes"] == 420
    assert payload["schedule_days"] == ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    assert "周一、周二、周三、周四、周五、周六、周日可用 420 分钟" in payload["schedule_summary"]
    assert sum(stage["scheduled_minutes"] for stage in payload["stages"] if stage["is_minimum_task"]) == 420
    assert {
        stage["scheduled_day"]
        for stage in payload["stages"]
        if stage["task_type"] == "minimum"
    } >= {"周一", "周二", "周三", "周四", "周五"}


def test_course_learning_path_replans_when_profile_time_preference_changes(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-dynamic-budget", "path-dynamic-budget@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        weekend_profile = confirm_profile_for_user(db, 1, course_id=course["id"], time_preference="一周1小时学习时间，周末才有空进行学习")

    first_response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))
    assert first_response.status_code == 200
    first_payload = first_response.json()
    assert first_payload["weekly_time_budget_minutes"] == 60
    assert first_payload["schedule_days"] == ["周六", "周日"]

    with client.app.state.testing_session_factory() as db:
        record = db.scalar(select(StudentProfileRecord).where(StudentProfileRecord.user_id == 1))
        assert record is not None
        daily_profile = weekend_profile.model_copy(update={"time_preference": "daily 1 hour with weekend"}).with_completion_score()
        record.profile_data = daily_profile.model_dump(mode="json")
        db.commit()

    second_response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))
    assert second_response.status_code == 200
    second_payload = second_response.json()
    assert second_payload["weekly_time_budget_minutes"] == 420
    assert second_payload["planned_minutes"] == 420
    assert second_payload["schedule_days"] == ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    assert second_payload["schedule_days"] != first_payload["schedule_days"]


def test_course_learning_path_keeps_stretch_tasks_after_minimum_schedule(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-stretch", "path-stretch@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course["id"], time_preference="一周1小时学习时间，周末才有空进行学习")

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    minimum_stages = [stage for stage in payload["stages"] if stage["task_type"] == "minimum"]
    stretch_stages = [stage for stage in payload["stages"] if stage["task_type"] == "stretch"]
    assert len(minimum_stages) == 2
    assert stretch_stages
    assert payload["minimum_task_count"] == len(minimum_stages)
    assert payload["stretch_task_count"] == len(stretch_stages)
    assert sum(stage["scheduled_minutes"] for stage in minimum_stages) == 60
    assert all(stage["is_minimum_task"] is True and stage["is_stretch_task"] is False for stage in minimum_stages)
    assert all(stage["scheduled_minutes"] > 0 and stage["scheduled_day"] in {"周六", "周日"} for stage in stretch_stages)
    assert all(stage["scheduled_date"] for stage in stretch_stages)
    assert all(stage["schedule_label"] != "后续任务" for stage in stretch_stages)
    assert all(stage["is_minimum_task"] is False and stage["is_stretch_task"] is True for stage in stretch_stages)
    assert "后续关卡" in payload["schedule_summary"]
    assert "超额" not in payload["schedule_summary"]


def test_course_learning_path_marks_today_tasks_without_minimum_or_stretch_copy(tmp_path, monkeypatch):
    class Saturday(date):
        @classmethod
        def today(cls):
            return cls(2026, 5, 16)

    import app.services.learning_path_service as learning_path_service

    monkeypatch.setattr(learning_path_service, "date", Saturday)
    client = make_client(tmp_path)
    token = register_user(client, "path-today", "path-today@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course["id"], time_preference="一周1小时学习时间，周末才有空进行学习")

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    today_stages = [stage for stage in payload["stages"] if stage["is_today_task"]]
    assert today_stages
    assert all(stage["scheduled_day"] == "周六" for stage in today_stages)
    assert all(stage["schedule_label"] == "今日任务" for stage in today_stages)
    assert sum(stage["scheduled_minutes"] for stage in payload["stages"] if stage["is_minimum_task"]) == 60
    assert "minimum" not in payload["schedule_summary"].lower()
    assert "超额" not in payload["schedule_summary"]


def test_course_learning_path_can_switch_to_requested_chapter(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-chapter-switch", "path-chapter-switch@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course["id"])

    response = client.post(
        f"/api/courses/{course['id']}/learning-paths/plan",
        headers=auth_headers(token),
        json={"chapter_id": "outline-chapter-3"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_chapter_id"] == "outline-chapter-3"
    assert payload["active_chapter_title"]
    assert {chapter["id"] for chapter in payload["chapters"]} >= {"outline-chapter-1", "outline-chapter-3"}
    assert all(
        stage["node_id"] == "outline-chapter-3" or stage["node_id"].startswith("outline-section-3-")
        for stage in payload["stages"]
    )


def test_course_learning_path_prioritizes_weak_nodes_with_prerequisites(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-ranking", "ranking@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course["id"])
        service = CourseService(db)
        service.upsert_node_mastery(1, course["id"], "outline-section-3-2", "3.2 鍒楄〃", 0.42, "鍒楄〃鎿嶄綔钖勫急")
        service.upsert_node_mastery(1, course["id"], "outline-section-1-1", "1.1 Python intro", 0.96, "passed")
        graph = service.get_knowledge_graph(1, course["id"])
        for node in graph["nodes"]:
            node_id = node["id"]
            if node_id.startswith("outline-section-1-") or node_id.startswith("outline-section-2-"):
                service.upsert_node_mastery(1, course["id"], node_id, node["name"], 0.92, "passed prerequisite")

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_chapter_id"] == "outline-chapter-3"
    stages = payload["stages"]
    ids = [stage["node_id"] for stage in stages]
    assert "outline-section-3-2" not in ids
    assert any(node_id.startswith("outline-section-3-2-") for node_id in ids)
    assert "outline-chapter-3" not in ids
    assert all(stage["level"] > 1 for stage in stages)
    first_weak_child_id = next(node_id for node_id in ids if node_id.startswith("outline-section-3-2-"))
    if "outline-section-3-1" in ids:
        assert ids.index("outline-section-3-1") < ids.index(first_weak_child_id)
    if "outline-chapter-4" in ids:
        assert ids.index(first_weak_child_id) < ids.index("outline-chapter-4")
    if "outline-section-1-1" in ids:
        assert ids.index("outline-section-1-1") > 5
    assert any(stage["is_remedial"] for stage in stages if stage["node_id"].startswith("outline-section-3-2-"))
    assert stages[0]["graph_basis"]


def test_course_learning_path_requires_confirmed_profile(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-no-profile", "no-profile@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 400
    assert response.json()["detail"] == "confirmed course profile is required"


def test_course_learning_path_rejects_account_profile_without_course_profile(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-global-profile", "path-global-profile@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()
    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=None)

    response = client.post(f"/api/courses/{course['id']}/learning-paths/plan", headers=auth_headers(token))

    assert response.status_code == 400
    assert response.json()["detail"] == "confirmed course profile is required"


def test_course_learning_path_remedial_mode_focuses_failed_node_and_dependencies(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-remedial", "remedial@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course["id"])
        service = CourseService(db)
        service.upsert_node_mastery(
            1,
            course["id"],
            "outline-section-3-2",
            "3.2 list",
            0.42,
            "failed list assessment",
        )

    response = client.post(
        f"/api/courses/{course['id']}/learning-paths/plan",
        headers=auth_headers(token),
        json={"plan_type": "remedial", "focus_node_id": "outline-section-3-2"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan_type"] == "remedial"
    assert payload["focus_node_id"] == "outline-section-3-2"
    assert payload["current_stage_id"].startswith("outline-section-3-2-")
    assert payload["pass_threshold"] == 0.75
    assert payload["active_chapter_id"] == "outline-chapter-3"
    ids = [stage["node_id"] for stage in payload["stages"]]
    assert "outline-chapter-3" not in ids
    assert "outline-section-3-2" not in ids
    assert payload["current_stage_id"] in ids
    assert all(stage["level"] > 1 for stage in payload["stages"])
    if "outline-section-3-1" in ids:
        assert ids.index("outline-section-3-1") < ids.index(payload["current_stage_id"])
    focus_stage = next(stage for stage in payload["stages"] if stage["node_id"] == payload["current_stage_id"])
    assert focus_stage["mastery_status"] in {"not_started", "severe_weak", "basic"}
    assert focus_stage["is_current"] is True
    assert focus_stage["path_status"] == "current"
    assert focus_stage["is_remedial"] is True
    assert any("remedial" in item.lower() or "琛ユ晳" in item for item in payload["adjustment_basis"])


def test_course_learning_path_returns_to_mainline_after_focus_node_passes(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "path-pass", "path-pass@example.com")
    patch_in_memory_graph_store(monkeypatch)
    course = client.post("/api/courses/default-python", headers=auth_headers(token)).json()

    with client.app.state.testing_session_factory() as db:
        confirm_profile_for_user(db, 1, course_id=course["id"])
        service = CourseService(db)
        service.upsert_node_mastery(
            1,
            course["id"],
            "outline-section-3-2",
            "3.2 list",
            0.82,
            "passed list assessment",
        )

    response = client.post(
        f"/api/courses/{course['id']}/learning-paths/plan",
        headers=auth_headers(token),
        json={"plan_type": "main"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan_type"] == "main"
    assert payload["focus_node_id"] == ""
    ids = [stage["node_id"] for stage in payload["stages"]]
    if "outline-section-3-2" in ids:
        assert ids.index("outline-section-3-2") > 2
    assert payload["current_stage_id"] != "outline-section-3-2"
    current_stage = next(stage for stage in payload["stages"] if stage["node_id"] == payload["current_stage_id"])
    assert current_stage["path_status"] == "current"


def test_graph_store_is_closed_after_build_and_get_success(tmp_path, monkeypatch):
    client = make_client(tmp_path)
    token = register_user(client, "graph-success", "graph-success@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)
    monkeypatch.setattr(CourseService, "knowledge_graph_agent_cls", FakeKnowledgeGraphAgent)

    closed_operations = []

    class FakeGraphStore:
        def __init__(self):
            self.operation = None

        def replace_course_graph(self, user_id, course_id, nodes, edges):  # noqa: ARG002
            self.operation = "replace"

        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            self.operation = "get"
            return {"nodes": [], "edges": []}

        def close(self):
            closed_operations.append(self.operation)

    monkeypatch.setattr(CourseService, "graph_store_cls", FakeGraphStore)
    client.post(
        f"/api/courses/{course_id}/materials",
        headers=auth_headers(token),
        files={"file": ("lesson.pdf", b"fake pdf content", "application/pdf")},
    )

    build = client.post(f"/api/courses/{course_id}/knowledge-graph/build", headers=auth_headers(token))
    graph = client.get(f"/api/courses/{course_id}/knowledge-graph", headers=auth_headers(token))

    assert build.status_code == 200
    assert graph.status_code == 200
    assert closed_operations == ["replace", "get"]


def test_graph_store_is_closed_after_build_and_get_failure(tmp_path, monkeypatch):
    client = make_client(tmp_path, raise_server_exceptions=False)
    token = register_user(client, "graph-failure", "graph-failure@example.com")
    course_id = create_course(client, token)
    monkeypatch.setattr(CourseService, "parser", staticmethod(fake_parser))
    monkeypatch.setattr(CourseService, "vector_service_cls", FakeVectorService)
    monkeypatch.setattr(CourseService, "knowledge_graph_agent_cls", FakeKnowledgeGraphAgent)

    closed_operations = []

    class RaisingGraphStore:
        def __init__(self):
            self.operation = None

        def replace_course_graph(self, user_id, course_id, nodes, edges):  # noqa: ARG002
            self.operation = "replace"
            raise RuntimeError("graph replace failed")

        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            self.operation = "get"
            raise RuntimeError("graph get failed")

        def close(self):
            closed_operations.append(self.operation)

    monkeypatch.setattr(CourseService, "graph_store_cls", RaisingGraphStore)
    client.post(
        f"/api/courses/{course_id}/materials",
        headers=auth_headers(token),
        files={"file": ("lesson.pdf", b"fake pdf content", "application/pdf")},
    )

    build = client.post(f"/api/courses/{course_id}/knowledge-graph/build", headers=auth_headers(token))
    graph = client.get(f"/api/courses/{course_id}/knowledge-graph", headers=auth_headers(token))

    assert build.status_code == 500
    assert graph.status_code == 200
    assert graph.json() == {"nodes": [], "edges": []}
    assert closed_operations == ["replace"]


def test_graph_store_is_closed_after_get_failure_for_succeeded_graph_job(tmp_path, monkeypatch):
    client = make_client(tmp_path, raise_server_exceptions=False)
    token = register_user(client, "graph-get-failure", "graph-get-failure@example.com")
    course_id = create_course(client, token)

    closed_operations = []

    class RaisingGraphStore:
        def __init__(self):
            self.operation = None

        def get_course_graph(self, user_id, course_id):  # noqa: ARG002
            self.operation = "get"
            raise RuntimeError("graph get failed")

        def close(self):
            closed_operations.append(self.operation)

    with client.app.state.testing_session_factory() as db:
        db.add(GraphBuildJob(course_id=course_id, status="succeeded", current_stage="done", progress=100))
        db.commit()

    monkeypatch.setattr(CourseService, "graph_store_cls", RaisingGraphStore)

    graph = client.get(f"/api/courses/{course_id}/knowledge-graph", headers=auth_headers(token))

    assert graph.status_code == 500
    assert closed_operations == ["get"]


def test_course_knowledge_endpoints_require_authentication(tmp_path):
    client = make_client(tmp_path)

    materials = client.get("/api/courses/1/materials")
    chunks = client.get("/api/courses/1/chunks")
    rebuild_index = client.post("/api/courses/1/vector-index/rebuild")
    graph = client.get("/api/courses/1/knowledge-graph")
    build = client.post("/api/courses/1/knowledge-graph/build")

    assert materials.status_code == 401
    assert chunks.status_code == 401
    assert rebuild_index.status_code == 401
    assert graph.status_code == 401
    assert build.status_code == 401
