"""Interactively reset the one email-less first admin; never accepts secrets as arguments."""
from getpass import getpass
import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from fastapi import HTTPException
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True, encoding="utf-8-sig")
sys.path.insert(0, str(ROOT / "backend"))

from app.api.accounts import normalize_username  # noqa: E402
from app.core.admin_maintenance import reset_email_less_admin_password  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.database import build_engine  # noqa: E402
from app.core.security import password_hash  # noqa: E402


def _verify_target(settings, username):
    engine = build_engine(settings, readonly=True)
    try:
        with engine.connect() as connection:
            if connection.execute(text("SELECT current_database()")).scalar() != "project_db":
                raise RuntimeError("Unexpected database")
            if connection.execute(text("SELECT version_num FROM public.alembic_version")).scalar() != "0008_email_less_first_admin":
                raise RuntimeError("Expected database schema 0008")
            target = connection.execute(text("""
                SELECT user_id, username FROM public.users
                WHERE lower(username)=lower(:username) AND role='admin'
                  AND email IS NULL AND email_auth_exempt=true
            """), {"username": username}).mappings().first()
            if not target:
                raise LookupError("No email-less first administrator matches that username")
            return dict(target)
    finally:
        engine.dispose()


def main():
    if not sys.stdin.isatty():
        raise RuntimeError("Run this command in an interactive terminal")
    settings = Settings.from_env()
    if (settings.database != "project_db" or settings.environment == "test"
            or settings.host != "127.0.0.1" or settings.port != 55433):
        raise RuntimeError("Refusing non-production or unexpected database")
    known_hosts = ROOT / ".local" / "known_hosts"
    if not os.getenv("SSH_HOST") or not known_hosts.is_file():
        raise RuntimeError("Expected verified SSH/Tunnel configuration is missing")

    username = normalize_username(input("要重設密碼的首位管理員帳號：").strip())
    target = _verify_target(settings, username)
    print("目標帳號：@" + target["username"])
    if input("請輸入 RESET " + target["username"] + " 確認：").strip() != "RESET " + target["username"]:
        raise RuntimeError("Confirmation did not match; no change was made")

    password = getpass("設定新密碼（8–128 字元）：")
    if password != getpass("再次輸入新密碼："):
        raise RuntimeError("Passwords did not match; no change was made")
    encoded_password = password_hash(password)
    del password

    engine = build_engine(settings, readonly=False)
    try:
        with engine.begin() as connection:
            if connection.execute(text("SELECT current_database()")).scalar() != "project_db":
                raise RuntimeError("Unexpected database")
            if connection.execute(text("SELECT version_num FROM public.alembic_version")).scalar() != "0008_email_less_first_admin":
                raise RuntimeError("Expected database schema 0008")
            result = reset_email_less_admin_password(connection, username, encoded_password)
        print("管理員密碼已更新；舊登入工作階段已撤銷 "
              + str(result["revoked_sessions"]) + " 個。稽核紀錄已寫入資料庫。")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if isinstance(exc, HTTPException):
            message = str(exc.detail)
        elif isinstance(exc, (RuntimeError, ValueError, LookupError)):
            message = str(exc)
        else:
            message = "資料庫操作失敗，交易已回滾（" + type(exc).__name__ + "）"
        print("密碼重設未完成：" + message, file=sys.stderr)
        sys.exit(1)
