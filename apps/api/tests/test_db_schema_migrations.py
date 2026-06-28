from app import db as db_module
from app.db import _ensure_mysql_course_owner_index


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if "information_schema.STATISTICS" in sql:
            return FakeResult(self.rows)
        return FakeResult([])


def test_mysql_course_owner_index_is_added_when_existing_courses_table_lacks_composite_index():
    connection = FakeConnection(
        [
            {"INDEX_NAME": "PRIMARY", "columns": "id"},
            {"INDEX_NAME": "ix_courses_user_id", "columns": "user_id"},
        ]
    )

    _ensure_mysql_course_owner_index(connection)

    assert any(
        statement == "ALTER TABLE courses ADD UNIQUE INDEX uq_courses_id_user_id (id, user_id)"
        for statement in connection.statements
    )


def test_mysql_course_owner_index_is_not_added_when_equivalent_index_exists():
    connection = FakeConnection(
        [
            {"INDEX_NAME": "PRIMARY", "columns": "id"},
            {"INDEX_NAME": "custom_courses_owner_scope", "columns": "id,user_id"},
        ]
    )

    _ensure_mysql_course_owner_index(connection)

    assert not any(statement.startswith("ALTER TABLE courses ADD") for statement in connection.statements)


def test_mysql_course_owner_index_is_skipped_before_courses_table_exists():
    connection = FakeConnection([])

    _ensure_mysql_course_owner_index(connection)

    assert not any(statement.startswith("ALTER TABLE courses ADD") for statement in connection.statements)


def test_init_db_runs_mysql_prerequisite_indexes_before_create_all(monkeypatch):
    calls = []

    class FakeEngine:
        class Dialect:
            name = "mysql"

        dialect = Dialect()

        def begin(self):
            return self

        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_prerequisite_indexes():
        calls.append("prerequisite_indexes")

    def fake_create_all(bind):
        calls.append("create_all")

    monkeypatch.setattr(db_module, "engine", FakeEngine())
    monkeypatch.setattr(db_module, "_ensure_mysql_prerequisite_indexes", fake_prerequisite_indexes)
    monkeypatch.setattr(db_module.Base.metadata, "create_all", fake_create_all)
    monkeypatch.setattr(db_module, "_ensure_course_scoped_profile_columns", lambda: calls.append("profile_columns"))

    db_module.init_db()

    assert calls == ["prerequisite_indexes", "create_all", "profile_columns"]
