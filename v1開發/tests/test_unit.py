import os
from dataclasses import replace
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import OperationalError
from app.api.restaurants import get_repository
from app.core.config import Settings
from app.core.database import build_engine
from app.core.safety import assert_test_target, assert_test_connection
from app.main import create_app
from app.models.restaurants import Restaurant

SETTINGS = Settings("127.0.0.1", 55432, "foodiemo_v1_test", "test", "not-a-real-secret", "test")

class FakeEngine:
    def dispose(self): pass

class FakeRepo:
    def list(self, page, page_size, q, category):
        return dict(items=[dict(id="9007199254740993", name="<b>店</b>", address=None,
                               category=None, review_count=0)], total=1, page=page, page_size=page_size)
    def detail(self, restaurant_id): return None
    def reviews(self, *args): return None

@pytest.fixture
def client():
    app = create_app(SETTINGS, FakeEngine())
    app.dependency_overrides[get_repository] = lambda: FakeRepo()
    with TestClient(app) as client:
        yield client

def test_ENV02_missing_config_fails_without_fallback():
    with patch.dict(os.environ, {}, clear=True), patch("app.core.config.load_dotenv"):
        with pytest.raises(RuntimeError, match="PostgreSQL"):
            Settings.from_env()

@pytest.mark.parametrize("port", ["bad", "0", "65536"])
def test_invalid_port(port):
    with patch.dict(os.environ, dict(DB_HOST="localhost", DB_PORT=port, DB_NAME="x", DB_USER="x", DB_PASSWORD="x"), clear=True), patch("app.core.config.load_dotenv"):
        with pytest.raises(RuntimeError, match="DB_PORT"): Settings.from_env()

def test_secret_not_in_repr_or_url():
    assert SETTINGS.password not in repr(SETTINGS)
    assert SETTINGS.password not in str(SETTINGS.url)

@pytest.mark.parametrize("changes", [
    {"database": "project_db"}, {"database": "project_db_test"}, {"environment": "development"},
    {"host": "different"}, {"port": 5432}
])
def test_ENV08_refuse_unsafe_targets(changes, monkeypatch):
    monkeypatch.setenv("TEST_EXPECTED_HOST", "127.0.0.1")
    monkeypatch.setenv("TEST_EXPECTED_PORT", "55432")
    monkeypatch.setenv("TEST_ALLOW_WRITE", "foodiemo-v1-isolated")
    with pytest.raises(RuntimeError): assert_test_target(replace(SETTINGS, **changes))

def test_ENV08_missing_marker(monkeypatch):
    monkeypatch.delenv("TEST_ALLOW_WRITE", raising=False)
    with pytest.raises(RuntimeError): assert_test_target(SETTINGS)

def test_case_sensitive_columns():
    query = str(select(Restaurant).compile(dialect=postgresql.dialect()))
    assert '"googleMaps_id"' in query and '"reviewsCount"' in query and '"categoryName"' in query
    assert "public.restaurant_rows" in query

@pytest.mark.parametrize("query", ["page=0", "page=10001", "page_size=51", "page_size=-1", "q=" + "a"*101])
def test_REST01_pagination_validation(client, query):
    response = client.get("/api/v1/restaurants?" + query)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"

def test_REST03_REST04_contract_preserves_missing_and_text(client):
    response = client.get("/api/v1/restaurants")
    item = response.json()["items"][0]
    assert item["id"] == "9007199254740993" and item["name"] == "<b>店</b>"
    assert item["rating"] is None and item["photo_url"] is None and item["address"] is None
    assert response.headers["X-Request-ID"]
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]

def test_REST02_not_found(client):
    assert client.get("/api/v1/restaurants/999").status_code == 404
    assert client.get("/api/v1/restaurants/999/reviews").status_code == 404
    assert client.get("/api/v1/restaurants/9223372036854775808").status_code == 422

def test_ENV03_REST05_database_error_is_redacted(client):
    def broken():
        raise OperationalError("SELECT private", {}, Exception("super-secret-password"))
    client.app.dependency_overrides[get_repository] = broken
    response = client.get("/api/v1/restaurants")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert "super-secret" not in response.text and "SELECT" not in response.text

def test_static_page_has_no_demo_auth(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "探索餐廳" in response.text
    assert client.get("/.env").status_code == 404

def test_real_connection_failure_is_bounded():
    import time
    settings = replace(SETTINGS, port=1)
    app = create_app(settings)
    start = time.monotonic()
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert time.monotonic() - start < 12
