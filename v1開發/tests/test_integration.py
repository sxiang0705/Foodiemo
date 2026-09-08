"""Small deterministic fixtures; every write follows target and server marker checks."""
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from alembic import command
from alembic.config import Config
from app.core.config import Settings
from app.core.database import build_engine
from app.core.safety import assert_test_target, assert_test_connection
from app.api.restaurants import get_repository
from app.main import create_app
from app.repositories.restaurants import RestaurantRepository

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv("RUN_PG_TESTS") != "1", reason="Use scripts/test.py --integration")]
ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture(scope="module")
def engine():
    settings = Settings.from_env()
    assert_test_target(settings)
    engine = build_engine(settings, readonly=False)
    with engine.connect() as c:
        assert_test_connection(c, settings)
        assert c.execute(text("SHOW server_version")).scalar().startswith("9.5.")
    yield engine
    engine.dispose()

def test_ENV06_migration_reentry(engine):
    config = Config(str(ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with engine.connect() as c:
        tables = set(inspect(c).get_table_names(schema="public"))
        assert len(tables - {"alembic_version"}) == 14
        assert c.execute(text("SELECT version_num FROM public.alembic_version")).scalar() == "0001_baseline"
        assert c.execute(text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN (SELECT oid FROM pg_class WHERE relnamespace='public'::regnamespace)")).scalar() >= 1

@pytest.fixture
def fixture_session(engine):
    with engine.connect() as connection:
        transaction = connection.begin()
        assert_test_connection(connection, Settings.from_env())
        # Abort on collisions rather than deleting unknown test data.
        connection.execute(text("""INSERT INTO public.restaurant_rows
            (restaurant_id, "googleMaps_id", title, address, "categoryName", "reviewsCount")
            VALUES (910003, 'foodiemo-fixture-3', '完整餐廳', '測試街 3 號', '測試分類', 90),
                   (910012, 'foodiemo-fixture-12', '<b>特殊 & 餐廳</b>', NULL, NULL, 0),
                   (910105, 'foodiemo-fixture-105', '100%_好吃', '測試街 105 號', '測試分類', 2)"""))
        connection.execute(text("""INSERT INTO public.business_hours
            (restaurant_id, weekday, open_time, close_time) VALUES (910003, 1, '09:00', '18:00')"""))
        connection.execute(text("""INSERT INTO public.reviews_rows (restaurant_id, raw_text, created_at)
            VALUES (910003, '<b>評論文字</b>', '2020-01-01T00:00:00Z')"""))
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        transaction.rollback()

@pytest.fixture
def client(fixture_session, engine):
    app = create_app(Settings.from_env(), engine)
    app.dependency_overrides[get_repository] = lambda: RestaurantRepository(fixture_session)
    # Do not dispose the module engine via app lifespan between tests.
    yield TestClient(app)

def test_REST01_filter_pagination_literal_wildcards(client):
    response = client.get("/api/v1/restaurants", params={"category": "測試分類", "page_size": 1})
    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert response.json()["items"][0]["id"] == "910003"
    assert client.get("/api/v1/restaurants", params={"q":"%_"}).json()["items"][0]["id"] == "910105"
    assert client.get("/api/v1/restaurants", params={"category":"測試分類","page":2,"page_size":1}).json()["items"][0]["id"] == "910105"

def test_REST02_noncontiguous_ids(client):
    assert client.get("/api/v1/restaurants/910003").status_code == 200
    assert client.get("/api/v1/restaurants/910004").status_code == 404

def test_REST03_REST04_missing_fields(client):
    r = client.get("/api/v1/restaurants/910012").json()
    assert r["name"] == "<b>特殊 & 餐廳</b>"
    assert r["business_hours"] == [] and r["rating"] is None and r["price"] is None
    assert r["address"] is None and r["photo_url"] is None
    r = client.get("/api/v1/restaurants/910003").json()
    assert r["business_hours"][0]["open_time"] == "09:00:00"

def test_REST05_empty(client):
    r = client.get("/api/v1/restaurants", params={"q":"確定不會有的餐廳"}).json()
    assert r["items"] == [] and r["total"] == 0

def test_REST06_import_date_is_not_publish_date(client):
    response = client.get("/api/v1/restaurants/910003/reviews")
    assert response.status_code == 200
    r = response.json()["items"][0]
    assert r["text"] == "<b>評論文字</b>" and r["published_at"] is None and r["rating"] is None
    assert "created_at" not in r
    assert client.get("/api/v1/restaurants/910003").json()["review_count"] == 90

def test_pg_constraints_jsonb_transactions(fixture_session):
    connection = fixture_session.connection()
    with pytest.raises(DBAPIError), connection.begin_nested():
        connection.execute(text("""INSERT INTO public.restaurant_rows ("googleMaps_id", title, "reviewsCount") VALUES ('invalid-fixture', 'bad', -1)"""))
    assert connection.execute(text("SELECT CAST(:payload AS jsonb) ->> 'a'"), {"payload": '{"a":1}'}).scalar() == "1"
    with pytest.raises(DBAPIError), connection.begin_nested():
        connection.execute(text("INSERT INTO public.reviews_rows (restaurant_id, raw_text) VALUES (-123, 'orphan')"))

def test_ENV01_runtime_connection_readonly():
    settings = Settings.from_env()
    assert_test_target(settings)
    engine = build_engine(settings)
    with engine.connect() as c:
        assert_test_connection(c, settings)
        assert c.execute(text("SHOW transaction_read_only")).scalar() == "on"
        with pytest.raises(DBAPIError):
            c.execute(text("CREATE TEMP TABLE should_not_exist(id int)"))
    engine.dispose()

def test_fixture_cleanup(engine):
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM public.restaurant_rows WHERE restaurant_id IN (910003,910012,910105)")).scalar() == 0
