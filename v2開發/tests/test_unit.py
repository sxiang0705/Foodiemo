import base64
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from app.core.config import Settings, ROOT
from app.core.safety import assert_test_target, assert_test_connection, assert_test_path
from app.main import create_app, get_session
from app.models.restaurants import Restaurant
from app.recommendation.service import card, map_link, encode_cursor, decode_cursor, recommend, RecommendationContext, RotationProvider

SETTINGS=Settings("127.0.0.1",55433,"foodiemo_v2_test","foodiemo_v2_test_owner","fixture-secret","test")
def row(id=9007199254740993,**kwargs):
    return SimpleNamespace(**(dict(restaurant_id=id,title="<b>店 & 名</b>",category=None,
        latitude=None,longitude=None,address=None)|kwargs))
class FakeEngine:
    def dispose(self):pass
class FixtureProvider:
    version="fixture-v1"
    def select(self,session,context):return [row()]
@pytest.fixture
def client():
    app=create_app(SETTINGS,FakeEngine(),FixtureProvider())
    app.dependency_overrides[get_session]=lambda:None
    with TestClient(app) as c:yield c

def test_missing_config_no_fallback():
    with patch.dict(os.environ,{},clear=True),patch("app.core.config.load_dotenv"):
        with pytest.raises(RuntimeError,match="PostgreSQL"):Settings.from_env()
@pytest.mark.parametrize("port",["bad","0","65536"])
def test_invalid_port(port):
    with patch.dict(os.environ,dict(DB_HOST="localhost",DB_PORT=port,DB_NAME="x",DB_USER="x",DB_PASSWORD="x"),clear=True),patch("app.core.config.load_dotenv"):
        with pytest.raises(RuntimeError,match="DB_PORT"):Settings.from_env()
def test_secret_repr():
    assert SETTINGS.password not in repr(SETTINGS)
    assert SETTINGS.password not in str(SETTINGS.url)

@pytest.fixture
def guard_env(monkeypatch):
    monkeypatch.setenv("TEST_EXPECTED_HOST","127.0.0.1")
    monkeypatch.setenv("TEST_EXPECTED_PORT","55433")
    monkeypatch.setenv("TEST_ALLOW_WRITE","foodiemo-v2-isolated")
@pytest.mark.parametrize("changes",[
    {"database":"project_db"},{"database":"project_db_test"},{"database":"foodiemo_v1_test"},
    {"database":"foodiemo_v2_restore_20260909"},{"user":"postgres"},{"host":"other"},
    {"port":5432},{"environment":"development"}])
def test_guard_refuses(changes,guard_env):
    with pytest.raises(RuntimeError):assert_test_target(replace(SETTINGS,**changes))
def test_guard_allows_exact(guard_env):
    assert_test_target(SETTINGS)
@pytest.mark.parametrize("identity",[
    ("project_db","foodiemo_v2_test_owner","foodiemo-v2-isolated"),
    ("foodiemo_v2_test","postgres","foodiemo-v2-isolated"),
    ("foodiemo_v2_test","foodiemo_v2_test_owner",None)])
def test_server_guard(identity,guard_env):
    class C:
        def execute(self,*args):return self
        def one(self):return identity
    with pytest.raises(RuntimeError):assert_test_connection(C(),SETTINGS)
def test_guard_missing_marker(monkeypatch,guard_env):
    monkeypatch.delenv("TEST_ALLOW_WRITE")
    with pytest.raises(RuntimeError):assert_test_target(SETTINGS)
@pytest.mark.parametrize("path",[ROOT/"uploads/x.jpg",ROOT/"test-uploads/../uploads/x.jpg",ROOT.parent/"v1開發/test-uploads/x.jpg"])
def test_path_guard(path):
    with pytest.raises(RuntimeError):assert_test_path(path)
def test_path_allowed():
    assert assert_test_path(ROOT/"test-uploads/x.jpg")==ROOT/"test-uploads/x.jpg"

@pytest.mark.parametrize("value",[1,9007199254740993,9223372036854775807])
def test_cursor_roundtrip(value):assert decode_cursor(encode_cursor(value))==value
@pytest.mark.parametrize("cursor",["junk","MToh","MTotMQ==",base64.b64encode(b"2:12").decode(),base64.b64encode(b"1:9223372036854775808").decode(),base64.b64encode(b"1:01").decode()])
def test_invalid_cursor(cursor):
    with pytest.raises(ValueError):decode_cursor(cursor)
def test_mapping_missing_safe_ids():
    item=card(row())
    assert item["id"]=="9007199254740993" and item["title"]=="<b>店 & 名</b>"
    assert all(item[k] is None for k in ["img","rating","hours","price"])
    assert item["source"]=="postgresql"
    assert item["mapLink"].startswith("https://www.google.com/maps/search/?")
    assert "<b>" not in item["mapLink"]
def test_map_coordinates_and_invalid():
    assert "22.5%2C120.5" in map_link(row(latitude=22.5,longitude=120.5))
    assert "nan" not in map_link(row(latitude=float("nan"),longitude=120.5))
def test_rotation_wrap_queries():
    class Session:
        def __init__(self):self.queries=[]
        def scalars(self,query):
            self.queries.append(str(query.compile(dialect=postgresql.dialect(),compile_kwargs={"literal_binds":True})))
            return [row(99)] if len(self.queries)==1 else [row(2),row(9)]
    s=Session()
    ids=[r.restaurant_id for r in RotationProvider().select(s,RecommendationContext(3,50))]
    assert ids==[99,2,9] and "LIMIT 3" in s.queries[0] and "LIMIT 2" in s.queries[1]
    assert "restaurant_id > 50" in s.queries[0] and "restaurant_id <= 50" in s.queries[1]
def test_provider_switch_and_duplicate_reject():
    assert recommend(None,FixtureProvider(),3,"")["algorithm_version"]=="fixture-v1"
    class Bad(FixtureProvider):
        def select(self,*a):return [row(),row()]
    with pytest.raises(RuntimeError):recommend(None,Bad(),3,"")
def test_case_sensitive_schema():
    sql=str(select(Restaurant).compile(dialect=postgresql.dialect()))
    assert all(x in sql for x in ['"googleMaps_id"','"categoryName"','"reviewsCount"'])
@pytest.mark.parametrize("query",["count=0","count=4","count=invalid","cursor=junk","cursor="+"x"*65])
def test_api_validation(client,query):
    assert client.get("/api/restaurants/recommendations?"+query).status_code==422
def test_original_api_contract(client):
    r=client.get("/api/restaurants/recommendations?count=3&t=123")
    assert r.status_code==200 and r.json()["items"][0]["id"]=="9007199254740993"
    assert r.headers["Cache-Control"]=="no-store"
def test_db_error_redacted(client):
    class F:
        def select(self,*a):raise OperationalError("SQL private",{},Exception("secret"))
    client.app.state.provider=F()
    response=client.get("/api/restaurants/recommendations")
    assert response.status_code==503
    assert "SQL private" not in response.text and "secret" not in response.text
def test_unimplemented_is_not_fake_success(client):
    assert client.post("/api/login/google",json={}).status_code==501
def test_frontend_static_and_secrets(client):
    assert client.get("/search.html").status_code==200
    assert "FoodiemoAPI" in client.get("/static/api/client.js").text
    assert client.get("/").status_code==200
    assert client.get("/.env").status_code==404
    assert client.get("/backend/app/main.py").status_code==404
    assert "unsafe-inline" in client.get("/").headers["Content-Security-Policy"]



@pytest.mark.parametrize("host,password,expected",[("smtp.gmail.com","abcd efgh ijkl mnop","abcdefghijklmnop"),("smtp.example.test","password with spaces","password with spaces")])
def test_smtp_chinese_hostname_and_password_spacing(monkeypatch,host,password,expected):
    from dataclasses import replace
    from app.core import mail
    captured={}
    class SMTP:
        def __init__(self,*args,**kwargs):captured.update(kwargs)
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def ehlo(self):pass
        def starttls(self,**kwargs):captured['tls']=True
        def login(self,user,secret):captured['password']=secret
        def send_message(self,message):captured['message']=message
    monkeypatch.setattr(mail.socket,'getfqdn',lambda:'測試電腦')
    monkeypatch.setattr(mail.smtplib,'SMTP',SMTP)
    settings=replace(SETTINGS,smtp_host=host,smtp_port=587,smtp_user='sender@example.test',smtp_password=password,smtp_from='sender@example.test')
    mail.SMTPMailer(settings).send('recipient@example.test','1234','signup')
    assert captured['local_hostname'].isascii()
    assert captured['password']==expected and captured['tls']
    assert captured['message']['To']=='recipient@example.test'
    assert '1234' in captured['message'].get_content()
