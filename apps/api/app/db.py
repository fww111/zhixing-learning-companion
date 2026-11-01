from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def get_db_url() -> str:
    return settings.database_url


def create_engine_for_url(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    db_engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    if database_url.startswith("sqlite"):

        @event.listens_for(db_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ARG001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return db_engine


def create_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


engine = create_engine_for_url(settings.database_url)
SessionLocal = create_session_factory(engine)


def init_db() -> None:
    from app.models import course, kb_evaluation, profile_record, user  # noqa: F401

    _ensure_mysql_prerequisite_indexes()
    Base.metadata.create_all(bind=engine)
    _ensure_course_scoped_profile_columns()


def _ensure_mysql_prerequisite_indexes() -> None:
    if engine.dialect.name not in {"mysql", "mariadb"}:
        return
    with engine.begin() as connection:
        _ensure_mysql_course_owner_index(connection)


def _ensure_course_scoped_profile_columns() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "profile_interviews" not in table_names or "student_profiles" not in table_names:
        return

    with engine.begin() as connection:
        for table_name in ("profile_interviews", "student_profiles"):
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            if "course_id" not in columns:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN course_id INTEGER NULL"))
        if engine.dialect.name in {"mysql", "mariadb"}:
            _ensure_mysql_course_profile_indexes(connection)


def _ensure_mysql_course_owner_index(connection) -> None:
    try:
        indexes = connection.execute(
            text(
                """
                SELECT INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columns
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'courses'
                GROUP BY INDEX_NAME
                """
            )
        ).mappings().all()
    except SQLAlchemyError:
        return

    index_columns = {row["INDEX_NAME"]: row["columns"] for row in indexes}
    if not index_columns:
        return
    if "id,user_id" not in set(index_columns.values()):
        connection.execute(text("ALTER TABLE courses ADD UNIQUE INDEX uq_courses_id_user_id (id, user_id)"))


def _ensure_mysql_course_profile_indexes(connection) -> None:
    try:
        indexes = connection.execute(
            text(
                """
                SELECT INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columns
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'student_profiles'
                GROUP BY INDEX_NAME
                """
            )
        ).mappings().all()
    except SQLAlchemyError:
        return

    index_columns = {row["INDEX_NAME"]: row["columns"] for row in indexes}
    if index_columns.get("uq_student_profiles_user_id") == "user_id":
        connection.execute(text("ALTER TABLE student_profiles DROP INDEX uq_student_profiles_user_id"))
    if "uq_student_profiles_user_course" not in index_columns:
        connection.execute(text("ALTER TABLE student_profiles ADD UNIQUE INDEX uq_student_profiles_user_course (user_id, course_id)"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
