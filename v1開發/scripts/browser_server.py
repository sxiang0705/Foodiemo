"""Isolated browser fixture server: all fixture writes rollback when it exits."""
from pathlib import Path
import sys
import threading
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.orm import Session
import uvicorn
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import Settings
from app.core.database import build_engine
from app.core.safety import assert_test_target, assert_test_connection
from app.api.restaurants import get_repository
from app.repositories.restaurants import RestaurantRepository
from app.main import create_app

load_dotenv(ROOT / ".env.test", override=True, encoding="utf-8-sig")
settings = Settings.from_env()
assert_test_target(settings)
engine = build_engine(settings, readonly=False)
with engine.connect() as connection:
    transaction = connection.begin()
    assert_test_connection(connection, settings)
    connection.execute(text("""INSERT INTO public.restaurant_rows
        (restaurant_id, "googleMaps_id", title, address, "categoryName", "reviewsCount", website)
        VALUES (920003, 'browser-fixture-3', '街角小食堂', '測試街 3 號', '測試分類', 90, 'https://example.com'),
               (920012, 'browser-fixture-12', '<b>特殊 & 餐廳</b>', NULL, NULL, 0, 'javascript:alert(1)'),
               (920105, 'browser-fixture-105', '100%_好吃', '測試街 105 號', '測試分類', 2, NULL)"""))
    connection.execute(text("""INSERT INTO public.business_hours (restaurant_id, weekday, open_time, close_time)
        VALUES (920003, 1, '09:00', '18:00')"""))
    connection.execute(text("""INSERT INTO public.reviews_rows (restaurant_id, raw_text)
        VALUES (920003, '<b>評論文字</b> & 好吃')"""))
    connection.execute(text("""INSERT INTO public.restaurant_rows (restaurant_id, "googleMaps_id", title)
        SELECT 920200+i, 'browser-page-'||i, '分頁測試餐廳 '||i FROM generate_series(1,12) AS i"""))
    lock = threading.Lock()
    def repository():
        with lock:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                yield RestaurantRepository(session)
    app = create_app(settings, engine)
    app.dependency_overrides[get_repository] = repository
    try:
        uvicorn.run(app, host="127.0.0.1", port=8001, access_log=False)
    finally:
        transaction.rollback()
