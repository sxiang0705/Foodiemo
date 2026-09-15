"""Run ONLY with scripts/test.py --integration against the v2 isolated PostgreSQL."""
import os
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect,text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.core.database import build_engine
from app.core.safety import assert_test_target,assert_test_connection
from app.main import create_app,get_session
pytestmark=[pytest.mark.integration,pytest.mark.skipif(os.getenv("RUN_PG_TESTS")!="1",reason="Use guarded integration entry point")]
ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture(scope="module")
def engine():
    s=Settings.from_env();assert_test_target(s)
    e=build_engine(s,readonly=False)
    with e.connect() as c:
        assert_test_connection(c,s)
        assert c.execute(text("SHOW server_version")).scalar()=="9.5.25"
    yield e
    e.dispose()
def test_migration_reentry(engine):
    config=Config(str(ROOT/"alembic.ini"))
    command.upgrade(config,"head");command.upgrade(config,"head")
    with engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM public.alembic_version")).scalar()=="0003_record_likes"
        assert len(inspect(c).get_table_names(schema="public"))==21
@pytest.fixture
def fixture_connection(engine):
    with engine.connect() as c:
        tx=c.begin()
        assert_test_connection(c,Settings.from_env())
        # No delete/truncate: require empty dedicated test candidates.
        assert c.execute(text("SELECT count(*) FROM public.restaurant_rows")).scalar()==0
        try:yield c
        finally:tx.rollback()
@pytest.mark.parametrize("count",[0,1,2,3,7])
def test_real_pg_recommendations_and_rotation(fixture_connection,engine,count):
    c=fixture_connection
    ids=[910003,910012,910105,920005,920111,930003,9007199254740993][:count]
    for i in ids:
        c.execute(text('INSERT INTO public.restaurant_rows (restaurant_id,"googleMaps_id",title,"reviewsCount") VALUES (:id,:gid,:title,0)'),
            {"id":i,"gid":"v2-fixture-"+str(i),"title":"<b>原版 & 店</b>"})
    s=Session(bind=c,join_transaction_mode="create_savepoint")
    app=create_app(Settings.from_env(),engine)
    app.dependency_overrides[get_session]=lambda:s
    try:
        client=TestClient(app)
        a=client.get("/api/restaurants/recommendations?count=3").json()
        assert [i["id"] for i in a["items"]]==[str(i) for i in ids[:3]]
        if count:
            b=client.get("/api/restaurants/recommendations",params={"cursor":a["next_cursor"]}).json()
            assert len(b["items"])==min(count,3)
            assert len({x["id"] for x in b["items"]})==len(b["items"])
            if count>3:assert a["items"][0]["id"]!=b["items"][0]["id"]
        for x in a["items"]:
            assert x["title"]=="<b>原版 & 店</b>" and x["rating"] is None and x["img"] is None
    finally:s.close()
def test_pg_constraints_and_jsonb(fixture_connection):
    c=fixture_connection
    assert c.execute(text("SELECT CAST(:x AS jsonb)->>'a'"),{"x":'{"a":1}'}).scalar()=="1"
    with pytest.raises(DBAPIError),c.begin_nested():
        c.execute(text("INSERT INTO public.business_hours (restaurant_id,weekday,is_closed) VALUES (-99,0,true)"))
def test_runtime_readonly_and_cleanup(engine):
    e=build_engine(Settings.from_env())
    try:
        with e.connect() as c:
            assert_test_connection(c,Settings.from_env())
            assert c.execute(text("SHOW transaction_read_only")).scalar()=="on"
            assert c.execute(text("SELECT count(*) FROM public.restaurant_rows")).scalar()==0
            with pytest.raises(DBAPIError):
                c.execute(text("CREATE TEMP TABLE forbidden(id int)"))
    finally:e.dispose()

