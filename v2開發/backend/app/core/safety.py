"""Guard test writes using declared and server-side identity."""
import os
from pathlib import Path
from sqlalchemy import text
from app.core.config import ROOT

def assert_test_target(settings):
    if (settings.environment != "test" or settings.database != "foodiemo_v2_test"
        or settings.user != "foodiemo_v2_test_owner"
        or settings.host != os.getenv("TEST_EXPECTED_HOST")
        or str(settings.port) != os.getenv("TEST_EXPECTED_PORT")
        or os.getenv("TEST_ALLOW_WRITE") != "foodiemo-v2-isolated"):
        raise RuntimeError("拒絕寫入：隔離測試資料庫、角色、主機／埠或標記不符")

def assert_test_connection(connection,settings):
    assert_test_target(settings)
    row = connection.execute(text("SELECT current_database(), current_user, "
        "shobj_description(oid, 'pg_database') FROM pg_database "
        "WHERE datname=current_database()")).one()
    if tuple(row) != ("foodiemo_v2_test","foodiemo_v2_test_owner","foodiemo-v2-isolated"):
        raise RuntimeError("拒絕寫入：伺服器資料庫、角色或隔離標記不符")

def assert_test_path(path):
    root=(ROOT/"test-uploads").resolve()
    expected=ROOT.resolve()/"test-uploads"
    target=Path(path).resolve()
    if root != expected or not target.is_relative_to(root):
        raise RuntimeError("拒絕操作：照片路徑不在 v2 專用測試目錄")
    return target

