"""Explicit PostgreSQL configuration; never falls back to a local database."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database: str
    user: str
    password: str = field(repr=False)
    environment: str = "development"

    app_secret: str = field(default="",repr=False)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = field(default="",repr=False)
    smtp_from: str = ""

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")
        required = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
        if any(not os.getenv(key) for key in required):
            raise RuntimeError("缺少 PostgreSQL 設定，請完成 v2開發/.env 的 DB_* 欄位")
        try:
            port = int(os.environ["DB_PORT"])
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            raise RuntimeError("DB_PORT 必須介於 1 與 65535") from None
        return cls(os.environ["DB_HOST"], port, os.environ["DB_NAME"],
                   os.environ["DB_USER"], os.environ["DB_PASSWORD"],
                   os.getenv("APP_ENV", "development"),
                   os.getenv("APP_SECRET", ""),os.getenv("SMTP_HOST", ""),int(os.getenv("SMTP_PORT", "587")),
                   os.getenv("SMTP_USERNAME", ""),os.getenv("SMTP_PASSWORD", ""),os.getenv("SMTP_FROM_EMAIL", ""))

    @property
    def url(self):
        return URL.create("postgresql+psycopg2", username=self.user,
                          password=self.password, host=self.host,
                          port=self.port, database=self.database)
