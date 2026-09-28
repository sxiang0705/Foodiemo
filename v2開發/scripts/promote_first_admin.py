"""Create the one explicitly authorized email-less first admin account."""
from getpass import getpass
import json
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import text

ROOT_ENV = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(ROOT_ENV, override=True, encoding="utf-8-sig")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.core.config import Settings  # noqa: E402
from app.core.database import build_engine  # noqa: E402
from app.api.accounts import normalize_username  # noqa: E402
from app.core.security import password_hash  # noqa: E402


def main():
    if not sys.stdin.isatty():
        raise RuntimeError("Run this command in an interactive terminal")
    settings = Settings.from_env()
    if (settings.database != "project_db" or settings.environment == "test"
            or settings.host != "127.0.0.1" or settings.port != 55433):
        raise RuntimeError("Refusing non-production or unexpected database")
    if not os.getenv("SSH_HOST") or not os.path.exists(os.path.join(os.path.dirname(ROOT_ENV), ".local", "known_hosts")):
        raise RuntimeError("Expected verified SSH/Tunnel configuration is missing")
    display_name = input("管理員顯示名稱 [admin_1]: ").strip() or "admin_1"
    if len(display_name) > 80:
        raise RuntimeError("Display name must be at most 80 characters")
    username = normalize_username(input("管理員登入帳號 [admin001]: ").strip() or "admin001")
    password = getpass("設定管理員密碼：")
    if password != getpass("再次輸入管理員密碼："):
        raise RuntimeError("Passwords did not match; no change was made")
    encoded_password = password_hash(password)
    del password

    engine = build_engine(settings, readonly=False)
    try:
        with engine.begin() as c:
            database = c.execute(text("SELECT current_database()")).scalar()
            version = c.execute(text("SELECT version_num FROM public.alembic_version")).scalar()
            if database != "project_db" or version != "0008_email_less_first_admin":
                raise RuntimeError("Expected project_db with migration 0008_email_less_first_admin")
            c.execute(text("SELECT pg_advisory_xact_lock(hashtext('foodiemo-first-admin-v1'))"))
            if c.execute(text("SELECT count(*) FROM public.users WHERE role='admin'")).scalar():
                raise RuntimeError("An admin account already exists; use the admin console instead")
            if c.execute(text("SELECT 1 FROM public.users WHERE lower(username)=lower(:username)"),
                         {"username": username}).scalar():
                raise RuntimeError("This login username is already in use")
            if input("To confirm, type CREATE " + username + ": ").strip() != "CREATE " + username:
                raise RuntimeError("Confirmation did not match; no change was made")
            user_id = c.execute(text("""
                INSERT INTO public.users
                  (user_name,username,email,password_hash,email_verified,email_auth_exempt,role,account_status)
                VALUES(:name,:username,NULL,:password,false,true,'admin','active') RETURNING user_id
            """), {"name": display_name, "username": username, "password": encoded_password}).scalar()
            c.execute(text("""
                INSERT INTO public.admin_audit_logs(actor_id,action,target_type,target_id,reason,details)
                VALUES(:id,'admin.first_bootstrap','user',:id,'Initial email-less administrator setup',
                       CAST(:details AS jsonb))
            """), {"id": user_id,
                  "details": json.dumps({"bootstrap": True, "email_auth_exempt": True})})
        print("First admin created for @" + username + ". No email recovery is available for this account.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Admin bootstrap stopped: " + str(exc), file=sys.stderr)
        sys.exit(1)
