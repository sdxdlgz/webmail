import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app

EMPTY_DATA = {"users": [], "groups": [], "accounts": []}


@pytest.fixture()
def client(tmp_path: Path):
    data_file = tmp_path / "data.json"
    data_file.write_text(json.dumps(EMPTY_DATA), encoding="utf-8")

    settings = Settings(data_file_path=data_file)
    app = create_app(settings)

    with TestClient(app) as c:
        yield c


def test_me_requires_auth(client: TestClient):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_login_sets_cookie_and_me_works(client: TestClient):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    assert r.json()["username"] == "admin"

    set_cookie = (r.headers.get("set-cookie") or "").lower()
    assert "session_id=" in set_cookie
    assert "httponly" in set_cookie

    r2 = client.get("/api/auth/me")
    assert r2.status_code == 200
    assert r2.json()["username"] == "admin"


def test_logout_clears_session(client: TestClient):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200

    r = client.post("/api/auth/logout")
    assert r.status_code == 200

    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_login_rejects_bad_password(client: TestClient):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_login_validation_error(client: TestClient):
    r = client.post("/api/auth/login", json={"username": "admin"})
    assert r.status_code == 422


def test_admin_created_on_startup(tmp_path: Path):
    data_file = tmp_path / "data.json"
    data_file.write_text(json.dumps(EMPTY_DATA), encoding="utf-8")

    settings = Settings(data_file_path=data_file)
    app = create_app(settings)

    with TestClient(app):
        pass

    saved = json.loads(data_file.read_text(encoding="utf-8"))
    admin = next(u for u in saved["users"] if u["username"] == "admin")
    assert admin["password_hash"]
    assert admin["password_hash"] != "admin123"
