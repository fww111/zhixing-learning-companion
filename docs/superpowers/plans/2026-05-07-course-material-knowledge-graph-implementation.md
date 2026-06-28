# Course Material Knowledge Graph Implementation Plan

> Status note: this is an archived early implementation plan. The current project uses Milvus as the active vector retrieval layer, keeps the old Chroma adapter only as compatibility code, and has added course-scoped profiles, OpenMAIC classroom generation, intelligent tutoring, dynamic assessment, and wrong-question redo. Use `README.md`, `AGENTS.md`, and `docs/current-technical-overview.md` as the current source of truth.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MVP course-material knowledge base pipeline: private courses, PDF/PPT upload, parsing with OCR fallback, MySQL chunk storage, ChromaDB semantic retrieval, Neo4j knowledge graph storage, and React workbench views.

**Architecture:** FastAPI remains the API boundary. MySQL stores authenticated user-owned business records and chunk metadata, ChromaDB stores per-course chunk embeddings, and Neo4j stores course knowledge graph nodes/relations keyed by `user_id` and `course_id`. React adds a course knowledge-base workspace that calls protected APIs with the existing JWT token.

**Tech Stack:** FastAPI, SQLAlchemy, MySQL, DeepSeek V4 Pro, ChromaDB, Neo4j Python driver, pypdf, python-pptx, OCR via pytesseract/pdf2image, React + Vite + TypeScript.

---

## 0. Local Runtime Assumptions

Run backend commands from PowerShell after activating the local environment:

```powershell
conda activate a3
cd D:\softbei\a3
```

Neo4j details:

- Browser/admin UI: `http://127.0.0.1:7474/`
- Application driver URL: `bolt://127.0.0.1:7687`
- Username: `neo4j`
- Password: keep only in local `.env`, do not commit it.

Add these local `.env` values before running integration smoke tests:

```text
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<local-password>
CHROMA_PERSIST_DIRECTORY=./data/chroma
OCR_LANG=chi_sim+eng
```

## 1. File Structure

### Backend Files

- Create `apps/api/app/models/course.py`: SQLAlchemy tables for `Course`, `CourseMaterial`, `KnowledgeChunk`, and `GraphBuildJob`.
- Create `apps/api/app/schemas/course.py`: Pydantic request/response schemas for course, material, chunk, graph, and search APIs.
- Create `apps/api/app/core/storage.py`: local upload path creation, safe filename handling, and file type validation.
- Create `apps/api/app/services/material_parser.py`: PDF/PPT/PPTX text extraction and OCR fallback orchestration.
- Create `apps/api/app/services/chunking_service.py`: deterministic chunking and source locator preservation.
- Create `apps/api/app/services/vector_service.py`: ChromaDB collection naming, upsert, query, and delete helpers.
- Create `apps/api/app/services/graph_store.py`: Neo4j driver wrapper and graph read/write helpers.
- Create `apps/api/app/agents/knowledge_graph_agent.py`: DeepSeek/Mock knowledge node and relation extraction.
- Create `apps/api/app/services/course_service.py`: application service for course CRUD, material parsing, indexing, graph building, and permissions.
- Create `apps/api/app/routers/courses.py`: protected course/material/chunk/search/graph endpoints.
- Modify `apps/api/app/core/config.py`: add upload, ChromaDB, Neo4j, and OCR settings.
- Modify `apps/api/app/db.py`: import `app.models.course` in `init_db()`.
- Modify `apps/api/app/main.py`: include `courses.router`.
- Modify `apps/api/requirements.txt`: add parsing, OCR, ChromaDB, Neo4j dependencies.
- Modify `.env.example`: add non-secret Neo4j/Chroma/OCR keys with empty password.

### Backend Tests

- Create `apps/api/tests/test_course_models.py`: DB model creation and ownership tests.
- Create `apps/api/tests/test_material_parser.py`: PDF/PPT chunk extraction using monkeypatched parsers.
- Create `apps/api/tests/test_vector_service.py`: Chroma adapter behavior with fake client.
- Create `apps/api/tests/test_graph_store.py`: Neo4j Cypher behavior with fake session.
- Create `apps/api/tests/test_courses_api.py`: protected API flow tests.
- Create `apps/api/tests/test_knowledge_graph_agent.py`: Mock LLM graph extraction contract tests.

### Frontend Files

- Modify `apps/web/src/api/client.ts`: add course/material/chunk/search/graph API types and functions.
- Create `apps/web/src/components/CourseKnowledgeBase.tsx`: course list, create form, and selected course container.
- Create `apps/web/src/components/MaterialUploadPanel.tsx`: upload UI and material status table.
- Create `apps/web/src/components/KnowledgeChunksPanel.tsx`: keyword/semantic search and chunk list.
- Create `apps/web/src/components/KnowledgeGraphPanel.tsx`: read-only graph visualization and node detail panel.
- Modify `apps/web/src/pages/Workspace.tsx`: add a tab or section for the course knowledge-base workflow.
- Modify `apps/web/src/styles/app.css`: add dense workbench styles for the new panels.

---

## Task 1: Backend Configuration And Dependencies

**Files:**
- Modify: `apps/api/app/core/config.py`
- Modify: `apps/api/requirements.txt`
- Modify: `.env.example`
- Test: `apps/api/tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Append to `apps/api/tests/test_config.py`:

```python
def test_course_knowledge_settings_are_loaded(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("UPLOAD_DIR", "data/uploads")
    monkeypatch.setenv("CHROMA_PERSIST_DIRECTORY", "data/chroma")
    monkeypatch.setenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("OCR_LANG", "chi_sim+eng")

    settings = Settings.from_environment()

    assert settings.upload_dir == "data/uploads"
    assert settings.chroma_persist_directory == "data/chroma"
    assert settings.neo4j_uri == "bolt://127.0.0.1:7687"
    assert settings.neo4j_user == "neo4j"
    assert settings.neo4j_password == "secret"
    assert settings.ocr_lang == "chi_sim+eng"
```

- [ ] **Step 2: Run test to verify failure**

```powershell
conda activate a3
cd D:\softbei\a3
python -m pytest apps/api/tests/test_config.py -q
```

Expected: FAIL because `Settings` does not yet expose the new fields.

- [ ] **Step 3: Implement settings**

Add fields to `Settings` in `apps/api/app/core/config.py`:

```python
    upload_dir: str = "data/uploads"
    chroma_persist_directory: str = "data/chroma"
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    ocr_lang: str = "chi_sim+eng"
    max_upload_size_mb: int = 100
```

Add environment loading in `Settings.from_environment()`:

```python
            upload_dir=os.getenv("UPLOAD_DIR", "data/uploads"),
            chroma_persist_directory=os.getenv("CHROMA_PERSIST_DIRECTORY", "data/chroma"),
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
            ocr_lang=os.getenv("OCR_LANG", "chi_sim+eng"),
            max_upload_size_mb=int(os.getenv("MAX_UPLOAD_SIZE_MB", "100")),
```

- [ ] **Step 4: Add dependencies**

Append to `apps/api/requirements.txt`:

```text
chromadb
neo4j
pypdf
python-pptx
pytesseract
pdf2image
Pillow
python-multipart
```

- [ ] **Step 5: Update `.env.example` without secrets**

Append:

```text
UPLOAD_DIR=data/uploads
MAX_UPLOAD_SIZE_MB=100
CHROMA_PERSIST_DIRECTORY=./data/chroma
NEO4J_URI=bolt://127.0.0.1:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=
OCR_LANG=chi_sim+eng
```

- [ ] **Step 6: Run config tests**

```powershell
python -m pytest apps/api/tests/test_config.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add apps/api/app/core/config.py apps/api/requirements.txt .env.example apps/api/tests/test_config.py
git commit -m "chore: add knowledge base runtime settings"
```

---

## Task 2: MySQL Course And Material Models

**Files:**
- Create: `apps/api/app/models/course.py`
- Modify: `apps/api/app/models/__init__.py`
- Modify: `apps/api/app/db.py`
- Test: `apps/api/tests/test_course_models.py`

- [ ] **Step 1: Write failing model tests**

Create `apps/api/tests/test_course_models.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.course import Course, CourseMaterial, GraphBuildJob, KnowledgeChunk
from app.models.user import User


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_course_material_chunk_and_job_are_user_owned():
    db = make_session()
    user = User(username="owner", email="owner@example.com", password_hash="hash")
    db.add(user)
    db.commit()
    db.refresh(user)

    course = Course(user_id=user.id, name="机器学习基础", major="计算机", level="本科", description="demo")
    db.add(course)
    db.commit()
    db.refresh(course)

    material = CourseMaterial(
        course_id=course.id,
        user_id=user.id,
        filename="lesson.pdf",
        file_type="pdf",
        storage_path="data/uploads/1/lesson.pdf",
        size_bytes=12,
    )
    db.add(material)
    db.commit()
    db.refresh(material)

    chunk = KnowledgeChunk(
        course_id=course.id,
        material_id=material.id,
        chunk_index=0,
        source_locator="page 1",
        heading="绪论",
        content="机器学习研究如何从数据中学习模型。",
        token_count=16,
        embedding_id="chunk-1",
    )
    job = GraphBuildJob(course_id=course.id, status="pending", current_stage="parse", progress=0)
    db.add_all([chunk, job])
    db.commit()

    assert course.user_id == user.id
    assert material.user_id == user.id
    assert chunk.source_locator == "page 1"
    assert job.status == "pending"
```

- [ ] **Step 2: Run test to verify failure**

```powershell
python -m pytest apps/api/tests/test_course_models.py -q
```

Expected: FAIL because `app.models.course` does not exist.

- [ ] **Step 3: Implement SQLAlchemy models**

Create `apps/api/app/models/course.py`:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    major: Mapped[str] = mapped_column(String(255), default="")
    level: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CourseMaterial(Base):
    __tablename__ = "course_materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(50), default="pending")
    parse_error: Mapped[str] = mapped_column(Text, default="")
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True, nullable=False)
    material_id: Mapped[int] = mapped_column(ForeignKey("course_materials.id"), index=True, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_locator: Mapped[str] = mapped_column(String(255), default="")
    heading: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding_id: Mapped[str] = mapped_column(String(255), default="")


class GraphBuildJob(Base):
    __tablename__ = "graph_build_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    current_stage: Mapped[str] = mapped_column(String(100), default="parse")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

Modify `apps/api/app/models/__init__.py`:

```python
from app.models import course, user  # noqa: F401
```

Modify `init_db()` in `apps/api/app/db.py`:

```python
def init_db() -> None:
    from app.models import course, user  # noqa: F401

    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 4: Run model tests**

```powershell
python -m pytest apps/api/tests/test_course_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/models/course.py apps/api/app/models/__init__.py apps/api/app/db.py apps/api/tests/test_course_models.py
git commit -m "feat: add course knowledge base models"
```

---

## Task 3: File Storage, Parsing, OCR, And Chunking

**Files:**
- Create: `apps/api/app/core/storage.py`
- Create: `apps/api/app/services/material_parser.py`
- Create: `apps/api/app/services/chunking_service.py`
- Test: `apps/api/tests/test_material_parser.py`

- [ ] **Step 1: Write failing parser and chunking tests**

Create `apps/api/tests/test_material_parser.py`:

```python
from pathlib import Path

from app.core.storage import allowed_file_type, safe_upload_name
from app.services.chunking_service import chunk_pages
from app.services.material_parser import ParsedPage


def test_safe_upload_name_removes_path_parts():
    assert safe_upload_name("..\\secret\\lesson 1.pdf").endswith(".pdf")
    assert "\\" not in safe_upload_name("..\\secret\\lesson 1.pdf")
    assert "/" not in safe_upload_name("../secret/lesson 1.pdf")


def test_allowed_file_type_whitelist():
    assert allowed_file_type("course.PDF") == "pdf"
    assert allowed_file_type("slides.pptx") == "pptx"
    assert allowed_file_type("image.exe") is None


def test_chunk_pages_preserves_source_locator():
    pages = [
        ParsedPage(source_locator="page 1", heading="绪论", text="机器学习是从数据中学习规律。" * 20, ocr_used=False),
        ParsedPage(source_locator="page 2", heading="监督学习", text="监督学习使用有标签样本。" * 20, ocr_used=False),
    ]

    chunks = chunk_pages(pages, max_chars=120)

    assert chunks
    assert chunks[0].source_locator == "page 1"
    assert chunks[0].heading == "绪论"
    assert "机器学习" in chunks[0].content
```

- [ ] **Step 2: Run test to verify failure**

```powershell
python -m pytest apps/api/tests/test_material_parser.py -q
```

Expected: FAIL because storage/parser/chunking files do not exist.

- [ ] **Step 3: Implement storage helpers**

Create `apps/api/app/core/storage.py`:

```python
from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

ALLOWED_EXTENSIONS = {"pdf", "ppt", "pptx"}


def allowed_file_type(filename: str) -> str | None:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix if suffix in ALLOWED_EXTENSIONS else None


def safe_upload_name(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    stem = Path(filename.replace("\\", "/")).name
    stem = Path(stem).stem
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._")
    return f"{cleaned or 'material'}-{uuid4().hex[:8]}{suffix}"


def course_upload_dir(root: str, user_id: int, course_id: int) -> Path:
    path = Path(root) / str(user_id) / str(course_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
```

- [ ] **Step 4: Implement parser contracts**

Create `apps/api/app/services/material_parser.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedPage:
    source_locator: str
    heading: str
    text: str
    ocr_used: bool = False


def parse_material(path: Path, file_type: str, ocr_lang: str) -> list[ParsedPage]:
    if file_type == "pdf":
        return parse_pdf(path, ocr_lang)
    if file_type in {"ppt", "pptx"}:
        return parse_pptx(path)
    raise ValueError(f"Unsupported file type: {file_type}")


def parse_pdf(path: Path, ocr_lang: str) -> list[ParsedPage]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[ParsedPage] = []
    extracted_chars = 0
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        extracted_chars += len(text)
        pages.append(ParsedPage(source_locator=f"page {index}", heading="", text=text, ocr_used=False))

    if pages and extracted_chars / max(len(pages), 1) < 20:
        return parse_pdf_with_ocr(path, ocr_lang)
    return [page for page in pages if page.text.strip()]


def parse_pdf_with_ocr(path: Path, ocr_lang: str) -> list[ParsedPage]:
    from pdf2image import convert_from_path
    import pytesseract

    pages: list[ParsedPage] = []
    for index, image in enumerate(convert_from_path(str(path)), start=1):
        text = pytesseract.image_to_string(image, lang=ocr_lang).strip()
        if text:
            pages.append(ParsedPage(source_locator=f"page {index}", heading="", text=text, ocr_used=True))
    return pages


def parse_pptx(path: Path) -> list[ParsedPage]:
    from pptx import Presentation

    presentation = Presentation(str(path))
    pages: list[ParsedPage] = []
    for index, slide in enumerate(presentation.slides, start=1):
        texts: list[str] = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                texts.append(shape.text.strip())
        content = "\n".join(text for text in texts if text).strip()
        if content:
            heading = texts[0].strip() if texts else ""
            pages.append(ParsedPage(source_locator=f"slide {index}", heading=heading, text=content, ocr_used=False))
    return pages
```

- [ ] **Step 5: Implement chunking**

Create `apps/api/app/services/chunking_service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from app.services.material_parser import ParsedPage


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    source_locator: str
    heading: str
    content: str
    token_count: int


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 2)


def chunk_pages(pages: list[ParsedPage], max_chars: int = 1200) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for page in pages:
        text = " ".join(page.text.split())
        if not text:
            continue
        start = 0
        while start < len(text):
            content = text[start:start + max_chars].strip()
            if content:
                chunks.append(
                    TextChunk(
                        chunk_index=len(chunks),
                        source_locator=page.source_locator,
                        heading=page.heading,
                        content=content,
                        token_count=estimate_tokens(content),
                    )
                )
            start += max_chars
    return chunks
```

- [ ] **Step 6: Run parser tests**

```powershell
python -m pytest apps/api/tests/test_material_parser.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add apps/api/app/core/storage.py apps/api/app/services/material_parser.py apps/api/app/services/chunking_service.py apps/api/tests/test_material_parser.py
git commit -m "feat: add material parsing and chunking"
```

---

## Task 4: ChromaDB Vector Service

**Files:**
- Create: `apps/api/app/services/vector_service.py`
- Test: `apps/api/tests/test_vector_service.py`

- [ ] **Step 1: Write failing vector tests**

Create `apps/api/tests/test_vector_service.py`:

```python
from app.services.vector_service import ChromaVectorService


class FakeCollection:
    def __init__(self):
        self.upserts = []

    def upsert(self, ids, documents, metadatas):
        self.upserts.append({"ids": ids, "documents": documents, "metadatas": metadatas})

    def query(self, query_texts, n_results):
        return {
            "ids": [["chunk-1"]],
            "documents": [["梯度下降用于优化损失函数"]],
            "metadatas": [[{"chunk_id": 1, "course_id": 2, "source_locator": "page 3"}]],
            "distances": [[0.12]],
        }


class FakeClient:
    def __init__(self):
        self.collection = FakeCollection()

    def get_or_create_collection(self, name):
        self.name = name
        return self.collection


def test_upsert_chunks_uses_course_scoped_collection():
    client = FakeClient()
    service = ChromaVectorService(client)

    service.upsert_chunks(
        course_id=2,
        chunks=[{"id": 1, "content": "梯度下降", "source_locator": "page 3"}],
    )

    assert client.name == "course_2"
    assert client.collection.upserts[0]["ids"] == ["chunk-1"]
    assert client.collection.upserts[0]["metadatas"][0]["chunk_id"] == 1


def test_semantic_search_returns_chunk_metadata():
    service = ChromaVectorService(FakeClient())

    results = service.search(course_id=2, query="优化", limit=3)

    assert results[0]["chunk_id"] == 1
    assert results[0]["source_locator"] == "page 3"
```

- [ ] **Step 2: Run test to verify failure**

```powershell
python -m pytest apps/api/tests/test_vector_service.py -q
```

Expected: FAIL because `vector_service.py` does not exist.

- [ ] **Step 3: Implement vector service**

Create `apps/api/app/services/vector_service.py`:

```python
from __future__ import annotations

from typing import Any

import chromadb

from app.core.config import settings


class ChromaVectorService:
    def __init__(self, client: Any | None = None):
        self.client = client or chromadb.PersistentClient(path=settings.chroma_persist_directory)

    def collection_name(self, course_id: int) -> str:
        return f"course_{course_id}"

    def collection(self, course_id: int):
        return self.client.get_or_create_collection(name=self.collection_name(course_id))

    def upsert_chunks(self, course_id: int, chunks: list[dict[str, Any]]) -> None:
        if not chunks:
            return
        collection = self.collection(course_id)
        collection.upsert(
            ids=[f"chunk-{chunk['id']}" for chunk in chunks],
            documents=[chunk["content"] for chunk in chunks],
            metadatas=[
                {
                    "chunk_id": chunk["id"],
                    "course_id": course_id,
                    "source_locator": chunk.get("source_locator", ""),
                }
                for chunk in chunks
            ],
        )

    def search(self, course_id: int, query: str, limit: int = 5) -> list[dict[str, Any]]:
        result = self.collection(course_id).query(query_texts=[query], n_results=limit)
        rows: list[dict[str, Any]] = []
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for index, chroma_id in enumerate(ids):
            metadata = metadatas[index] or {}
            rows.append(
                {
                    "id": chroma_id,
                    "chunk_id": metadata.get("chunk_id"),
                    "course_id": metadata.get("course_id"),
                    "source_locator": metadata.get("source_locator", ""),
                    "content": documents[index],
                    "distance": distances[index] if index < len(distances) else None,
                }
            )
        return rows
```

- [ ] **Step 4: Run vector tests**

```powershell
python -m pytest apps/api/tests/test_vector_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/services/vector_service.py apps/api/tests/test_vector_service.py
git commit -m "feat: add chromadb vector service"
```

---

## Task 5: Neo4j Graph Store

**Files:**
- Create: `apps/api/app/services/graph_store.py`
- Test: `apps/api/tests/test_graph_store.py`

- [ ] **Step 1: Write failing graph store tests**

Create `apps/api/tests/test_graph_store.py`:

```python
from app.services.graph_store import Neo4jGraphStore


class FakeSession:
    def __init__(self):
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **params):
        self.queries.append((query, params))
        return []


class FakeDriver:
    def __init__(self):
        self.session_obj = FakeSession()

    def session(self):
        return self.session_obj


def test_write_graph_scopes_nodes_by_user_and_course():
    driver = FakeDriver()
    store = Neo4jGraphStore(driver=driver)

    store.replace_course_graph(
        user_id=7,
        course_id=3,
        nodes=[{"id": "n1", "name": "梯度下降", "node_type": "method", "difficulty": "basic", "summary": "优化方法", "source_chunk_ids": [1], "confidence": 0.9}],
        edges=[],
    )

    params = driver.session_obj.queries[-1][1]
    assert params["user_id"] == 7
    assert params["course_id"] == 3
    assert params["nodes"][0]["id"] == "n1"
```

- [ ] **Step 2: Run test to verify failure**

```powershell
python -m pytest apps/api/tests/test_graph_store.py -q
```

Expected: FAIL because `graph_store.py` does not exist.

- [ ] **Step 3: Implement graph store**

Create `apps/api/app/services/graph_store.py`:

```python
from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase

from app.core.config import settings


class Neo4jGraphStore:
    def __init__(self, driver: Any | None = None):
        self.driver = driver or GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def replace_course_graph(
        self,
        user_id: int,
        course_id: int,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> None:
        with self.driver.session() as session:
            session.run(
                "MATCH (n:KnowledgeNode {user_id: $user_id, course_id: $course_id}) DETACH DELETE n",
                user_id=user_id,
                course_id=course_id,
            )
            session.run(
                """
                UNWIND $nodes AS node
                MERGE (n:KnowledgeNode {id: node.id})
                SET n.user_id = $user_id,
                    n.course_id = $course_id,
                    n.name = node.name,
                    n.node_type = node.node_type,
                    n.difficulty = node.difficulty,
                    n.summary = node.summary,
                    n.source_chunk_ids = node.source_chunk_ids,
                    n.confidence = node.confidence
                """,
                user_id=user_id,
                course_id=course_id,
                nodes=nodes,
            )
            session.run(
                """
                UNWIND $edges AS edge
                MATCH (source:KnowledgeNode {id: edge.source_node_id, user_id: $user_id, course_id: $course_id})
                MATCH (target:KnowledgeNode {id: edge.target_node_id, user_id: $user_id, course_id: $course_id})
                MERGE (source)-[r:RELATES_TO {id: edge.id}]->(target)
                SET r.user_id = $user_id,
                    r.course_id = $course_id,
                    r.relation_type = edge.relation_type,
                    r.reason = edge.reason,
                    r.confidence = edge.confidence
                """,
                user_id=user_id,
                course_id=course_id,
                edges=edges,
            )

    def get_course_graph(self, user_id: int, course_id: int) -> dict[str, list[dict[str, Any]]]:
        with self.driver.session() as session:
            node_rows = session.run(
                """
                MATCH (n:KnowledgeNode {user_id: $user_id, course_id: $course_id})
                RETURN n
                """,
                user_id=user_id,
                course_id=course_id,
            )
            edge_rows = session.run(
                """
                MATCH (s:KnowledgeNode {user_id: $user_id, course_id: $course_id})-[r:RELATES_TO]->(t:KnowledgeNode {user_id: $user_id, course_id: $course_id})
                RETURN r, s.id AS source_node_id, t.id AS target_node_id
                """,
                user_id=user_id,
                course_id=course_id,
            )
            nodes = [dict(row["n"]) for row in node_rows]
            edges = [
                {**dict(row["r"]), "source_node_id": row["source_node_id"], "target_node_id": row["target_node_id"]}
                for row in edge_rows
            ]
        return {"nodes": nodes, "edges": edges}
```

- [ ] **Step 4: Run graph store tests**

```powershell
python -m pytest apps/api/tests/test_graph_store.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/services/graph_store.py apps/api/tests/test_graph_store.py
git commit -m "feat: add neo4j graph store"
```

---

## Task 6: Knowledge Graph Agent

**Files:**
- Create: `apps/api/app/agents/knowledge_graph_agent.py`
- Test: `apps/api/tests/test_knowledge_graph_agent.py`

- [ ] **Step 1: Write failing agent contract test**

Create `apps/api/tests/test_knowledge_graph_agent.py`:

```python
from app.agents.knowledge_graph_agent import KnowledgeGraphAgent


def test_mock_graph_agent_returns_nodes_and_edges():
    agent = KnowledgeGraphAgent(mock=True)

    graph = agent.build_graph([
        {"id": 1, "content": "梯度下降是优化损失函数的方法。学习梯度下降前需要理解损失函数。", "source_locator": "page 1"}
    ])

    assert graph["nodes"]
    assert graph["edges"]
    assert graph["nodes"][0]["source_chunk_ids"]
    assert graph["edges"][0]["relation_type"] in {"prerequisite", "contains", "applies_to", "common_mistake", "case_supports"}
```

- [ ] **Step 2: Run test to verify failure**

```powershell
python -m pytest apps/api/tests/test_knowledge_graph_agent.py -q
```

Expected: FAIL because `knowledge_graph_agent.py` does not exist.

- [ ] **Step 3: Implement mock-first graph agent**

Create `apps/api/app/agents/knowledge_graph_agent.py`:

```python
from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.core.config import settings


class KnowledgeGraphAgent:
    def __init__(self, mock: bool | None = None):
        self.mock = settings.mock_llm if mock is None else mock

    def build_graph(self, chunks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        if self.mock:
            return self._mock_graph(chunks)
        return self._llm_graph(chunks)

    def _mock_graph(self, chunks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        first_chunk_id = chunks[0]["id"] if chunks else 0
        nodes = [
            {
                "id": f"node-{uuid4().hex[:8]}",
                "name": "损失函数",
                "node_type": "concept",
                "difficulty": "basic",
                "summary": "衡量模型预测结果和真实结果差距的函数。",
                "source_chunk_ids": [first_chunk_id],
                "confidence": 0.88,
            },
            {
                "id": f"node-{uuid4().hex[:8]}",
                "name": "梯度下降",
                "node_type": "method",
                "difficulty": "basic",
                "summary": "沿负梯度方向迭代更新参数以最小化损失函数。",
                "source_chunk_ids": [first_chunk_id],
                "confidence": 0.9,
            },
        ]
        edges = [
            {
                "id": f"edge-{uuid4().hex[:8]}",
                "source_node_id": nodes[0]["id"],
                "target_node_id": nodes[1]["id"],
                "relation_type": "prerequisite",
                "reason": "理解损失函数后才能解释梯度下降优化的目标。",
                "confidence": 0.86,
            }
        ]
        return {"nodes": nodes, "edges": edges}

    def _llm_graph(self, chunks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        # In the first implementation pass, keep this wrapper small and parse strict JSON from the existing LLM client.
        from app.llm.client import LLMClient

        prompt = (
            "从以下课程材料片段中抽取课程知识图谱。只返回 JSON，格式为 "
            "{\"nodes\":[{\"id\":\"node-key\",\"name\":\"...\",\"node_type\":\"concept|method|formula|tool|case\","
            "\"difficulty\":\"basic|intermediate|advanced\",\"summary\":\"...\",\"source_chunk_ids\":[1],\"confidence\":0.9}],"
            "\"edges\":[{\"id\":\"edge-key\",\"source_node_id\":\"node-key\",\"target_node_id\":\"node-key\","
            "\"relation_type\":\"prerequisite|contains|applies_to|common_mistake|case_supports\",\"reason\":\"...\",\"confidence\":0.8}]}。\n"
            f"材料片段：{chunks[:20]}"
        )
        result = LLMClient().complete_json(prompt)
        return {"nodes": result.get("nodes", []), "edges": result.get("edges", [])}
```

- [ ] **Step 3a: Add JSON completion helper if missing**

Open `apps/api/app/llm/client.py`. If the class does not already expose a JSON completion method, add this method inside `LLMClient` and make `_llm_graph()` call it:

```python
    def complete_json(self, prompt: str) -> dict:
        import json

        content = self.complete(prompt)
        if isinstance(content, dict):
            return content
        return json.loads(content)
```

If the existing client method is not named `complete`, use the current single-prompt text completion method in that file and keep the return contract as `dict`.

- [ ] **Step 4: Run agent tests**

```powershell
python -m pytest apps/api/tests/test_knowledge_graph_agent.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add apps/api/app/agents/knowledge_graph_agent.py apps/api/tests/test_knowledge_graph_agent.py apps/api/app/llm/client.py
git commit -m "feat: add knowledge graph extraction agent"
```

---

## Task 7: Course Service And Protected Course APIs

**Files:**
- Create: `apps/api/app/schemas/course.py`
- Create: `apps/api/app/services/course_service.py`
- Create: `apps/api/app/routers/courses.py`
- Modify: `apps/api/app/main.py`
- Test: `apps/api/tests/test_courses_api.py`

- [ ] **Step 1: Write failing API tests**

Create `apps/api/tests/test_courses_api.py`:

```python
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.main import create_app


def make_client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestClient(create_app(TestingSessionLocal))


def auth_headers(client: TestClient):
    response = client.post(
        "/api/auth/register",
        json={"username": "course_user", "email": "course@example.com", "password": "pass12345"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_course_crud_requires_auth_and_returns_user_courses():
    client = make_client()

    assert client.get("/api/courses").status_code == 401

    headers = auth_headers(client)
    created = client.post(
        "/api/courses",
        json={"name": "机器学习基础", "major": "计算机", "level": "本科", "description": "demo"},
        headers=headers,
    )

    assert created.status_code == 200
    assert created.json()["name"] == "机器学习基础"

    listed = client.get("/api/courses", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "机器学习基础"
```

- [ ] **Step 2: Run test to verify failure**

```powershell
python -m pytest apps/api/tests/test_courses_api.py -q
```

Expected: FAIL because `/api/courses` routes do not exist.

- [ ] **Step 3: Implement schemas**

Create `apps/api/app/schemas/course.py` with request/response classes:

```python
from __future__ import annotations

from pydantic import BaseModel


class CourseCreate(BaseModel):
    name: str
    major: str = ""
    level: str = ""
    description: str = ""


class CourseRead(BaseModel):
    id: int
    user_id: int
    name: str
    major: str
    level: str
    description: str
    status: str

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Implement course service**

Create `apps/api/app/services/course_service.py`:

```python
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.course import Course
from app.schemas.course import CourseCreate


class CourseService:
    def __init__(self, db: Session):
        self.db = db

    def create_course(self, user_id: int, payload: CourseCreate) -> Course:
        course = Course(user_id=user_id, **payload.model_dump())
        self.db.add(course)
        self.db.commit()
        self.db.refresh(course)
        return course

    def list_courses(self, user_id: int) -> list[Course]:
        return self.db.query(Course).filter(Course.user_id == user_id).order_by(Course.id.desc()).all()

    def get_owned_course(self, user_id: int, course_id: int) -> Course | None:
        return self.db.query(Course).filter(Course.id == course_id, Course.user_id == user_id).first()
```

- [ ] **Step 5: Implement router and register it**

Create `apps/api/app/routers/courses.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.course import CourseCreate, CourseRead
from app.services.course_service import CourseService

router = APIRouter(prefix="/api/courses", tags=["courses"])


@router.post("", response_model=CourseRead)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return CourseService(db).create_course(current_user.id, payload)


@router.get("", response_model=list[CourseRead])
def list_courses(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return CourseService(db).list_courses(current_user.id)


@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    course = CourseService(db).get_owned_course(current_user.id, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course
```

Modify `apps/api/app/main.py`:

```python
from app.routers import assessments, auth, chat, courses, paths, profiles, resources
...
    app.include_router(courses.router)
```

- [ ] **Step 6: Run API tests**

```powershell
python -m pytest apps/api/tests/test_courses_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add apps/api/app/schemas/course.py apps/api/app/services/course_service.py apps/api/app/routers/courses.py apps/api/app/main.py apps/api/tests/test_courses_api.py
git commit -m "feat: add protected course APIs"
```

---

## Task 8: Material Upload, Parse Pipeline, Search, And Graph Endpoints

**Files:**
- Modify: `apps/api/app/schemas/course.py`
- Modify: `apps/api/app/services/course_service.py`
- Modify: `apps/api/app/routers/courses.py`
- Test: `apps/api/tests/test_courses_api.py`

- [ ] **Step 1: Extend API tests for material and graph flow**

Append to `apps/api/tests/test_courses_api.py`:

```python
from io import BytesIO


def test_material_upload_rejects_unsupported_file_type():
    client = make_client()
    headers = auth_headers(client)
    course = client.post("/api/courses", json={"name": "ML"}, headers=headers).json()

    response = client.post(
        f"/api/courses/{course['id']}/materials",
        headers=headers,
        files={"file": ("bad.exe", BytesIO(b"bad"), "application/octet-stream")},
    )

    assert response.status_code == 400


def test_chunks_and_graph_endpoints_are_protected():
    client = make_client()
    assert client.get("/api/courses/1/chunks").status_code == 401
    assert client.get("/api/courses/1/knowledge-graph").status_code == 401
```

- [ ] **Step 2: Run tests to verify failure**

```powershell
python -m pytest apps/api/tests/test_courses_api.py -q
```

Expected: FAIL because material/chunk/graph endpoints do not exist.

- [ ] **Step 3: Add response schemas**

Extend `apps/api/app/schemas/course.py`:

```python
class MaterialRead(BaseModel):
    id: int
    course_id: int
    filename: str
    file_type: str
    size_bytes: int
    parse_status: str
    parse_error: str
    ocr_used: bool

    class Config:
        from_attributes = True


class ChunkRead(BaseModel):
    id: int
    course_id: int
    material_id: int
    chunk_index: int
    source_locator: str
    heading: str
    content: str
    token_count: int
    embedding_id: str

    class Config:
        from_attributes = True


class SemanticSearchResult(BaseModel):
    chunk_id: int
    course_id: int
    source_locator: str
    content: str
    distance: float | None = None


class KnowledgeGraphRead(BaseModel):
    nodes: list[dict]
    edges: list[dict]
```

- [ ] **Step 4: Add service methods**

Add to `CourseService`:

```python
    def list_chunks(self, user_id: int, course_id: int):
        course = self.get_owned_course(user_id, course_id)
        if not course:
            return None
        from app.models.course import KnowledgeChunk
        return self.db.query(KnowledgeChunk).filter(KnowledgeChunk.course_id == course_id).order_by(KnowledgeChunk.chunk_index).all()
```

Add these methods to `CourseService`; keep the first pass synchronous behind endpoints so the demo flow is reliable:

```python
    def upload_material(self, user_id: int, course_id: int, file):
        from pathlib import Path

        from fastapi import HTTPException

        from app.core.config import settings
        from app.core.storage import allowed_file_type, course_upload_dir, safe_upload_name
        from app.models.course import CourseMaterial, KnowledgeChunk
        from app.services.chunking_service import chunk_pages
        from app.services.material_parser import parse_material
        from app.services.vector_service import ChromaVectorService

        course = self.get_owned_course(user_id, course_id)
        if not course:
            return None

        file_type = allowed_file_type(file.filename or "")
        if not file_type:
            raise HTTPException(status_code=400, detail="Unsupported file type")

        payload = file.file.read()
        if len(payload) > settings.max_upload_size_mb * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large")

        upload_dir = course_upload_dir(settings.upload_dir, user_id, course_id)
        stored_name = safe_upload_name(file.filename or f"material.{file_type}")
        storage_path = upload_dir / stored_name
        storage_path.write_bytes(payload)

        material = CourseMaterial(
            course_id=course_id,
            user_id=user_id,
            filename=file.filename or stored_name,
            file_type=file_type,
            storage_path=str(storage_path),
            size_bytes=len(payload),
            parse_status="running",
        )
        self.db.add(material)
        self.db.commit()
        self.db.refresh(material)

        try:
            pages = parse_material(Path(material.storage_path), file_type, settings.ocr_lang)
            chunks = chunk_pages(pages)
            material.ocr_used = any(page.ocr_used for page in pages)
            self.db.query(KnowledgeChunk).filter(KnowledgeChunk.material_id == material.id).delete()
            db_chunks: list[KnowledgeChunk] = []
            for chunk in chunks:
                db_chunk = KnowledgeChunk(
                    course_id=course_id,
                    material_id=material.id,
                    chunk_index=chunk.chunk_index,
                    source_locator=chunk.source_locator,
                    heading=chunk.heading,
                    content=chunk.content,
                    token_count=chunk.token_count,
                )
                self.db.add(db_chunk)
                db_chunks.append(db_chunk)
            material.parse_status = "completed"
            self.db.commit()
            for db_chunk in db_chunks:
                self.db.refresh(db_chunk)
                db_chunk.embedding_id = f"chunk-{db_chunk.id}"
            self.db.commit()
            ChromaVectorService().upsert_chunks(
                course_id,
                [
                    {"id": chunk.id, "content": chunk.content, "source_locator": chunk.source_locator}
                    for chunk in db_chunks
                ],
            )
        except Exception as exc:
            material.parse_status = "failed"
            material.parse_error = str(exc)
            self.db.commit()
        self.db.refresh(material)
        return material

    def semantic_search(self, user_id: int, course_id: int, query: str):
        if not self.get_owned_course(user_id, course_id):
            return None
        return ChromaVectorService().search(course_id, query)

    def build_graph(self, user_id: int, course_id: int):
        from app.agents.knowledge_graph_agent import KnowledgeGraphAgent
        from app.models.course import KnowledgeChunk
        from app.services.graph_store import Neo4jGraphStore

        if not self.get_owned_course(user_id, course_id):
            return None
        chunks = self.db.query(KnowledgeChunk).filter(KnowledgeChunk.course_id == course_id).all()
        graph = KnowledgeGraphAgent().build_graph(
            [{"id": chunk.id, "content": chunk.content, "source_locator": chunk.source_locator} for chunk in chunks]
        )
        Neo4jGraphStore().replace_course_graph(user_id, course_id, graph["nodes"], graph["edges"])
        return graph

    def get_graph(self, user_id: int, course_id: int):
        if not self.get_owned_course(user_id, course_id):
            return None
        return Neo4jGraphStore().get_course_graph(user_id, course_id)
```

- [ ] **Step 5: Add router endpoints**

Add to `apps/api/app/routers/courses.py`:

```python
from fastapi import File, UploadFile
from app.schemas.course import ChunkRead, KnowledgeGraphRead, MaterialRead, SemanticSearchResult
```

Implement endpoints:

```python
@router.post("/{course_id}/materials", response_model=MaterialRead)
def upload_material(course_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    material = CourseService(db).upload_material(current_user.id, course_id, file)
    if not material:
        raise HTTPException(status_code=404, detail="Course not found")
    return material


@router.get("/{course_id}/chunks", response_model=list[ChunkRead])
def list_chunks(course_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    chunks = CourseService(db).list_chunks(current_user.id, course_id)
    if chunks is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return chunks


@router.get("/{course_id}/semantic-search", response_model=list[SemanticSearchResult])
def semantic_search(course_id: int, q: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    results = CourseService(db).semantic_search(current_user.id, course_id, q)
    if results is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return results


@router.post("/{course_id}/knowledge-graph/build", response_model=KnowledgeGraphRead)
def build_graph(course_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    graph = CourseService(db).build_graph(current_user.id, course_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return graph


@router.get("/{course_id}/knowledge-graph", response_model=KnowledgeGraphRead)
def get_graph(course_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    graph = CourseService(db).get_graph(current_user.id, course_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return graph
```

- [ ] **Step 6: Run API tests**

```powershell
python -m pytest apps/api/tests/test_courses_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add apps/api/app/schemas/course.py apps/api/app/services/course_service.py apps/api/app/routers/courses.py apps/api/tests/test_courses_api.py
git commit -m "feat: add material knowledge base endpoints"
```

---

## Task 9: Frontend API Client And Course Knowledge Base Components

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Create: `apps/web/src/components/CourseKnowledgeBase.tsx`
- Create: `apps/web/src/components/MaterialUploadPanel.tsx`
- Create: `apps/web/src/components/KnowledgeChunksPanel.tsx`
- Create: `apps/web/src/components/KnowledgeGraphPanel.tsx`
- Modify: `apps/web/src/pages/Workspace.tsx`
- Modify: `apps/web/src/styles/app.css`

- [ ] **Step 1: Add frontend API types and calls**

Append to `apps/web/src/api/client.ts`:

```ts
export interface Course {
  id: number;
  user_id: number;
  name: string;
  major: string;
  level: string;
  description: string;
  status: string;
}

export interface CourseMaterial {
  id: number;
  course_id: number;
  filename: string;
  file_type: string;
  size_bytes: number;
  parse_status: string;
  parse_error: string;
  ocr_used: boolean;
}

export interface KnowledgeChunk {
  id: number;
  course_id: number;
  material_id: number;
  chunk_index: number;
  source_locator: string;
  heading: string;
  content: string;
  token_count: number;
  embedding_id: string;
}

export interface KnowledgeGraph {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
}

export async function listCourses(token: string): Promise<Course[]> {
  const response = await fetch("/api/courses", { headers: authHeaders(token) });
  if (!response.ok) throw new Error("课程列表加载失败");
  return response.json();
}

export async function createCourse(token: string, payload: Pick<Course, "name" | "major" | "level" | "description">): Promise<Course> {
  const response = await fetch("/api/courses", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error("课程创建失败");
  return response.json();
}

export async function uploadMaterial(token: string, courseId: number, file: File): Promise<CourseMaterial> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`/api/courses/${courseId}/materials`, {
    method: "POST",
    headers: authHeaders(token),
    body: form
  });
  if (!response.ok) throw new Error("材料上传失败");
  return response.json();
}

export async function listChunks(token: string, courseId: number): Promise<KnowledgeChunk[]> {
  const response = await fetch(`/api/courses/${courseId}/chunks`, { headers: authHeaders(token) });
  if (!response.ok) throw new Error("知识片段加载失败");
  return response.json();
}

export async function semanticSearch(token: string, courseId: number, query: string): Promise<KnowledgeChunk[]> {
  const response = await fetch(`/api/courses/${courseId}/semantic-search?q=${encodeURIComponent(query)}`, {
    headers: authHeaders(token)
  });
  if (!response.ok) throw new Error("语义检索失败");
  return response.json();
}

export async function buildKnowledgeGraph(token: string, courseId: number): Promise<KnowledgeGraph> {
  const response = await fetch(`/api/courses/${courseId}/knowledge-graph/build`, {
    method: "POST",
    headers: authHeaders(token)
  });
  if (!response.ok) throw new Error("知识图谱生成失败");
  return response.json();
}

export async function getKnowledgeGraph(token: string, courseId: number): Promise<KnowledgeGraph> {
  const response = await fetch(`/api/courses/${courseId}/knowledge-graph`, { headers: authHeaders(token) });
  if (!response.ok) throw new Error("知识图谱加载失败");
  return response.json();
}
```

- [ ] **Step 2: Build course workbench component**

Create `apps/web/src/components/CourseKnowledgeBase.tsx` with state for courses, selected course, materials, chunks, and graph. Keep it dense: course list on the left, upload/search/graph panels on the right.

- [ ] **Step 3: Build upload panel**

Create `MaterialUploadPanel.tsx` with a file input accepting `.pdf,.ppt,.pptx`, upload button, and material table.

- [ ] **Step 4: Build chunk panel**

Create `KnowledgeChunksPanel.tsx` with keyword/semantic search input and chunk cards showing source locator and heading.

- [ ] **Step 5: Build read-only graph panel**

Create `KnowledgeGraphPanel.tsx` using SVG or plain HTML layout for MVP. Do not implement drag editing. Use automatic positioning from index values.

- [ ] **Step 6: Wire into Workspace**

Modify `apps/web/src/pages/Workspace.tsx`:

```tsx
import { CourseKnowledgeBase } from "../components/CourseKnowledgeBase";
...
<CourseKnowledgeBase token={token} />
```

Place it as a prominent workbench section before or beside the existing generated learning workflow.

- [ ] **Step 7: Build frontend**

```powershell
cd D:\softbei\a3\apps\web
npm run build
```

Expected: TypeScript and Vite build succeed.

- [ ] **Step 8: Commit**

```powershell
git add apps/web/src/api/client.ts apps/web/src/components/CourseKnowledgeBase.tsx apps/web/src/components/MaterialUploadPanel.tsx apps/web/src/components/KnowledgeChunksPanel.tsx apps/web/src/components/KnowledgeGraphPanel.tsx apps/web/src/pages/Workspace.tsx apps/web/src/styles/app.css
git commit -m "feat: add course knowledge base workspace"
```

---

## Task 10: End-To-End Verification And Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/deployment.md` if present
- Modify: `docs/prd-course-material-knowledge-graph.md` only if implementation reveals necessary requirement corrections

- [ ] **Step 1: Install backend dependencies**

```powershell
conda activate a3
cd D:\softbei\a3\apps\api
pip install -r requirements.txt
```

Expected: dependencies install in the `a3` conda environment.

- [ ] **Step 2: Verify local services**

Open Neo4j admin UI in browser:

```text
http://127.0.0.1:7474/
```

Confirm login works with local username and password. Then verify backend driver URL in `.env`:

```text
NEO4J_URI=bolt://127.0.0.1:7687
```

- [ ] **Step 3: Run backend tests**

```powershell
cd D:\softbei\a3
python -m pytest apps/api/tests -q
```

Expected: all tests pass.

- [ ] **Step 4: Run frontend build**

```powershell
cd D:\softbei\a3\apps\web
npm run build
```

Expected: build succeeds.

- [ ] **Step 5: Smoke test APIs**

Start backend:

```powershell
cd D:\softbei\a3\apps\api
python -m uvicorn app.main:app --reload --port 8001
```

Use a second PowerShell:

```powershell
$register = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/auth/register" -Method Post -ContentType "application/json" -Body (@{
  username = "kgdemo"
  email = "kgdemo@example.com"
  password = "pass12345"
} | ConvertTo-Json)
$token = $register.access_token
$headers = @{ Authorization = "Bearer $token" }
$course = Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/courses" -Method Post -Headers $headers -ContentType "application/json" -Body (@{
  name = "机器学习基础"
  major = "计算机"
  level = "本科"
  description = "知识图谱演示课程"
} | ConvertTo-Json)
Invoke-RestMethod -Uri "http://127.0.0.1:8001/api/courses/$($course.id)" -Method Get -Headers $headers
```

Expected: course is created and returned for the authenticated user.

- [ ] **Step 6: Update docs**

Add a concise section to `README.md`:

```markdown
### Course Knowledge Graph Runtime

Backend commands should be run after `conda activate a3`.

Neo4j browser runs at `http://127.0.0.1:7474/`; the backend connects through `NEO4J_URI=bolt://127.0.0.1:7687`.
Store `NEO4J_PASSWORD`, `LLM_API_KEY`, and other secrets only in local `.env`.
ChromaDB persists vectors under `CHROMA_PERSIST_DIRECTORY`.
```

- [ ] **Step 7: Commit verification docs**

```powershell
git add README.md docs/prd-course-material-knowledge-graph.md docs/superpowers/plans/2026-05-07-course-material-knowledge-graph-implementation.md
git commit -m "docs: add course knowledge graph implementation plan"
```

---

## Self-Review

- Spec coverage: The plan covers private courses, upload, parsing, OCR fallback, MySQL chunks, ChromaDB semantic search, Neo4j graph persistence, read-only graph visualization, and learning-path integration entry points.
- Known implementation boundary: The first pass keeps parsing and graph generation callable synchronously for demo reliability. A production task queue can be added after MVP behavior is verified.
- Secret handling: Neo4j password is not written into committed files; it belongs in local `.env`.
- Environment note: All Python commands assume `conda activate a3` has already run.
