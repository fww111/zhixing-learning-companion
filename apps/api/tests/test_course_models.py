import warnings

import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable
from sqlalchemy.orm import sessionmaker

from app.db import Base, create_engine_for_url
from app.models.course import Course, CourseMaterial, GraphBuildJob, KnowledgeChunk, KnowledgeNodeMastery
from app.models.user import User


def make_session():
    engine = create_engine_for_url("sqlite:///:memory:")
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def test_course_material_chunk_and_graph_job_persist_ownership_source_and_status():
    db = make_session()
    try:
        user = User(username="xiaoming", email="xm@example.com", password_hash="hashed")
        db.add(user)
        db.flush()

        course = Course(user_id=user.id, name="机器学习基础", major="计算机科学", level="大二")
        db.add(course)
        db.flush()

        material = CourseMaterial(
            course_id=course.id,
            user_id=user.id,
            filename="gradient-descent.pdf",
            file_type="pdf",
            storage_path="/tmp/gradient-descent.pdf",
            size_bytes=2048,
            parse_status="parsed",
            ocr_used=True,
        )
        db.add(material)
        db.flush()

        chunk = KnowledgeChunk(
            course_id=course.id,
            material_id=material.id,
            chunk_index=0,
            source_locator="p.3",
            heading="梯度下降",
            content="梯度下降通过迭代更新参数最小化损失函数。",
            token_count=24,
            embedding_id="emb-001",
        )
        db.add(chunk)

        job = GraphBuildJob(course_id=course.id, status="running", current_stage="chunk", progress=40)
        db.add(job)
        db.commit()

        saved_course = db.get(Course, course.id)
        saved_material = db.get(CourseMaterial, material.id)
        saved_chunk = db.get(KnowledgeChunk, chunk.id)
        saved_job = db.get(GraphBuildJob, job.id)

        assert saved_course.user_id == user.id
        assert saved_course.status == "draft"
        assert saved_material.user_id == user.id
        assert saved_material.course_id == course.id
        assert saved_material.parse_status == "parsed"
        assert saved_material.ocr_used is True
        assert saved_chunk.course_id == course.id
        assert saved_chunk.material_id == material.id
        assert saved_chunk.source_locator == "p.3"
        assert saved_job.course_id == course.id
        assert saved_job.status == "running"
        assert saved_job.current_stage == "chunk"
        assert saved_job.progress == 40
    finally:
        db.close()


def test_course_material_rejects_user_id_that_disagrees_with_course_owner():
    db = make_session()
    try:
        owner = User(username="owner", email="owner@example.com", password_hash="hashed")
        other = User(username="other", email="other@example.com", password_hash="hashed")
        db.add_all([owner, other])
        db.flush()

        course = Course(user_id=owner.id, name="machine learning")
        db.add(course)
        db.flush()

        material = CourseMaterial(
            course_id=course.id,
            user_id=other.id,
            filename="gradient-descent.pdf",
            file_type="pdf",
            storage_path="/tmp/gradient-descent.pdf",
            size_bytes=2048,
        )
        db.add(material)

        with pytest.raises(IntegrityError):
            db.flush()
    finally:
        db.close()


def test_knowledge_chunk_rejects_course_id_that_disagrees_with_material_course():
    db = make_session()
    try:
        user = User(username="student", email="student@example.com", password_hash="hashed")
        db.add(user)
        db.flush()

        course = Course(user_id=user.id, name="machine learning")
        other_course = Course(user_id=user.id, name="linear algebra")
        db.add_all([course, other_course])
        db.flush()

        material = CourseMaterial(
            course_id=course.id,
            user_id=user.id,
            filename="gradient-descent.pdf",
            file_type="pdf",
            storage_path="/tmp/gradient-descent.pdf",
            size_bytes=2048,
        )
        db.add(material)
        db.flush()

        chunk = KnowledgeChunk(
            course_id=other_course.id,
            material_id=material.id,
            chunk_index=0,
            content="Gradient descent updates parameters iteratively.",
        )
        db.add(chunk)

        with pytest.raises(IntegrityError):
            db.flush()
    finally:
        db.close()


def test_knowledge_node_mastery_mysql_ddl_does_not_require_existing_composite_course_index():
    ddl = str(CreateTable(KnowledgeNodeMastery.__table__).compile(dialect=mysql.dialect()))

    assert "REFERENCES courses (id, user_id)" not in ddl
    assert "FOREIGN KEY(course_id) REFERENCES courses (id)" in ddl
    assert "FOREIGN KEY(user_id) REFERENCES users (id)" in ddl


def test_course_models_do_not_emit_datetime_utcnow_deprecation_warning():
    db = make_session()
    try:
        user = User(username="timestamp-user", email="timestamp@example.com", password_hash="hashed")
        db.add(user)
        db.flush()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)

            course = Course(user_id=user.id, name="time-safe course")
            db.add(course)
            db.flush()

            job = GraphBuildJob(course_id=course.id, status="pending", current_stage="parse", progress=0)
            db.add(job)
            db.flush()

        utcnow_warnings = [
            warning
            for warning in caught
            if warning.category is DeprecationWarning and "datetime.datetime.utcnow()" in str(warning.message)
        ]
        assert utcnow_warnings == []
    finally:
        db.close()
