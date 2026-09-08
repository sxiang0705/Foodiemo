import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api.restaurants import router
from app.core.config import ROOT, Settings
from app.core.database import build_engine

logger = logging.getLogger("foodiemo")


def create_app(settings=None, engine=None):
    settings = settings or Settings.from_env()
    db_engine = engine if engine is not None else build_engine(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        db_engine.dispose()

    app = FastAPI(title="Foodiemo v1", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.engine = db_engine

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; connect-src 'self'; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
        return response

    def error(request, status, code, message):
        return JSONResponse(status_code=status, content={"error": {
            "code": code, "message": message, "request_id": request.state.request_id}})

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        # Never log the exception text: drivers may include SQL, credentials or rows.
        logger.warning("database_unavailable request_id=%s type=%s",
                       request.state.request_id, type(exc).__name__)
        return error(request, 503, "DATABASE_UNAVAILABLE", "資料庫暫時無法使用，請稍後重試")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return error(request, 422, "INVALID_REQUEST", "查詢參數格式或範圍不正確")

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(request, exc.status_code, "NOT_FOUND" if exc.status_code == 404 else "REQUEST_ERROR",
                     "找不到指定資料" if exc.status_code == 404 else "無法處理請求")

    @app.get("/api/v1/health")
    def health():
        with db_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    app.include_router(router)
    app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
    return app
