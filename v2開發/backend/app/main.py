import logging
from pathlib import Path
from urllib.parse import urlsplit
from app.api.accounts import router as accounts_router
from app.api.records import router as records_router
from app.core.mail import SMTPMailer
from app.core.safety import assert_test_path
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException
from app.core.config import ROOT, Settings
from app.core.database import build_engine
from app.recommendation.service import RotationProvider, decode_cursor, recommend

logger = logging.getLogger("foodiemo.v2")

def get_session(request: Request):
    with Session(request.app.state.engine) as session:
        yield session

def create_app(settings=None, engine=None, provider=None, write_engine=None, mailer=None, storage_root=None):
    settings = settings or Settings.from_env()
    db_engine = engine if engine is not None else build_engine(settings)
    mutation_engine=write_engine if write_engine is not None else (engine if engine is not None else build_engine(settings,readonly=False))
    @asynccontextmanager
    async def lifespan(app):
        yield
        db_engine.dispose()
        if mutation_engine is not db_engine:mutation_engine.dispose()
    app = FastAPI(title="Foodiemo v2", version="0.2.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.engine = db_engine
    app.state.write_engine=mutation_engine
    app.state.settings=settings
    app.state.mailer=mailer or SMTPMailer(settings)
    app.state.storage_root=Path(storage_root) if storage_root else ROOT/("test-uploads" if settings.environment=="test" else "uploads")
    if settings.environment=="test":assert_test_path(app.state.storage_root)
    app.state.provider = provider or RotationProvider()

    @app.middleware("http")
    async def headers(request, call_next):
        request.state.request_id = uuid4().hex
        if request.method not in ("GET","HEAD","OPTIONS"):
            origin=request.headers.get("origin")
            if origin and origin!=str(request.base_url).rstrip("/"):
                return JSONResponse({"detail":"不接受跨來源操作"},status_code=403)
            if request.headers.get("sec-fetch-site")=="cross-site":
                return JSONResponse({"detail":"不接受跨來源操作"},status_code=403)
        response = await call_next(request)
        response.headers.update({
            "X-Request-ID":request.state.request_id, "X-Content-Type-Options":"nosniff",
            "Referrer-Policy":"same-origin", "Cache-Control":"no-store",
            "Content-Security-Policy":(
                "default-src 'self'; script-src 'self' 'unsafe-inline' https://unpkg.com https://accounts.google.com; "
                "style-src 'self' 'unsafe-inline' https://unpkg.com https://accounts.google.com; "
                "img-src 'self' data: blob: https:; font-src 'self' data: https://unpkg.com; "
                "connect-src 'self' https://accounts.google.com; frame-src 'self' https://accounts.google.com; "
                "worker-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'")})
        return response

    def error(request, status, code, message):
        return JSONResponse(status_code=status, content={"detail":message,"error":{
            "code":code,"message":message,"request_id":request.state.request_id}})
    @app.exception_handler(SQLAlchemyError)
    async def db_error(request, exc):
        logger.warning("database_unavailable request_id=%s type=%s",request.state.request_id,type(exc).__name__)
        return error(request,503,"DATABASE_UNAVAILABLE","資料暫時讀取或保存失敗，請稍後再試")
    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error(request,422,"INVALID_REQUEST","查詢參數格式或範圍不正確")
    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(request,exc.status_code,"NOT_FOUND" if exc.status_code==404 else "REQUEST_ERROR",
                     "找不到指定資料" if exc.status_code==404 else (exc.detail if isinstance(exc.detail,str) else "無法處理請求"))

    @app.get("/api/health")
    def health():
        with db_engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"status":"ok","stage":"original-frontend-accounts-records","readonly":False}

    @app.get("/api/restaurants/recommendations")
    def recommendations(count: int = Query(3,ge=1,le=3),
                        cursor: str = Query("",max_length=64),
                        t: str = Query("",max_length=32), session=Depends(get_session)):
        try:
            decode_cursor(cursor)
        except ValueError:
            raise HTTPException(422) from None
        return recommend(session,app.state.provider,count,cursor)

    app.include_router(accounts_router)
    app.include_router(records_router)

    @app.api_route("/api/{remaining:path}",methods=["GET","POST","PUT","PATCH","DELETE"])
    def pending(request: Request, remaining: str):
        return error(request,501,"NOT_IMPLEMENTED","此功能尚未完成 v2 串接")
    app.mount("/static/api",StaticFiles(directory=ROOT/"frontend/api"),name="frontend-api")
    app.mount("/",StaticFiles(directory=ROOT/"frontend",html=True),name="frontend")
    return app

