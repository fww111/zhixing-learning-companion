from fastapi.testclient import TestClient

from app.db import Base, create_engine_for_url, create_session_factory
from app.main import create_app


def make_client(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'auth-test.db'}"
    engine = create_engine_for_url(database_url)
    TestingSessionLocal = create_session_factory(engine)
    Base.metadata.create_all(bind=engine)
    app = create_app(session_factory=TestingSessionLocal)
    return TestClient(app)


def test_register_returns_token_and_user(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/auth/register",
        json={"username": "xiaoming", "email": "xm@example.com", "password": "secret123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"]
    assert payload["token_type"] == "bearer"
    assert payload["user"]["username"] == "xiaoming"
    assert "password" not in payload["user"]


def test_register_rejects_duplicate_username_or_email(tmp_path):
    client = make_client(tmp_path)
    body = {"username": "xiaoming", "email": "xm@example.com", "password": "secret123"}

    assert client.post("/api/auth/register", json=body).status_code == 200
    duplicate = client.post("/api/auth/register", json=body)

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "username or email already registered"


def test_login_rejects_wrong_password(tmp_path):
    client = make_client(tmp_path)
    client.post(
        "/api/auth/register",
        json={"username": "xiaoming", "email": "xm@example.com", "password": "secret123"},
    )

    response = client.post("/api/auth/login", json={"account": "xiaoming", "password": "wrong-pass"})

    assert response.status_code == 401


def test_me_requires_and_accepts_bearer_token(tmp_path):
    client = make_client(tmp_path)
    token_response = client.post(
        "/api/auth/register",
        json={"username": "xiaoming", "email": "xm@example.com", "password": "secret123"},
    )
    token = token_response.json()["access_token"]

    missing = client.get("/api/auth/me")
    valid = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert missing.status_code == 401
    assert valid.status_code == 200
    assert valid.json()["email"] == "xm@example.com"
