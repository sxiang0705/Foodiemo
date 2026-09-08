"""Refuse test writes unless BOTH declared and server-side identities match."""
import os
from sqlalchemy import text


def assert_test_target(settings):
    if (settings.environment != "test"
            or settings.database != "foodiemo_v1_test"
            or settings.host != os.getenv("TEST_EXPECTED_HOST")
            or str(settings.port) != os.getenv("TEST_EXPECTED_PORT")
            or os.getenv("TEST_ALLOW_WRITE") != "foodiemo-v1-isolated"):
        raise RuntimeError("拒絕寫入：需要明確指定隔離測試資料庫與主機／連接埠")


def assert_test_connection(connection, settings):
    assert_test_target(settings)
    identity = connection.execute(text("SELECT current_database(), "
        "shobj_description(oid, 'pg_database') FROM pg_database "
        "WHERE datname=current_database()" )).one()
    if tuple(identity) != ("foodiemo_v1_test", "foodiemo-v1-isolated"):
        raise RuntimeError("拒絕寫入：伺服器資料庫名稱或隔離標記不符")
