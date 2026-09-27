"""One-time, interactive bootstrap of the first active Foodiemo admin account."""
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import text

ROOT_ENV = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(ROOT_ENV, override=True, encoding="utf-8-sig")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.core.config import Settings  # noqa: E402
from app.core.database import build_engine  # noqa: E402


def main():
    if not sys.stdin.isatty():
        raise RuntimeError("Run this command in an interactive terminal")
    settings = Settings.from_env()
    if (settings.database != "project_db" or settings.environment == "test"
            or settings.host != "127.0.0.1" or settings.port != 55433):
        raise RuntimeError("Refusing non-production or unexpected database")
    if not os.getenv("SSH_HOST") or not os.path.exists(os.path.join(os.path.dirname(ROOT_ENV), ".local", "known_hosts")):
        raise RuntimeError("Expected verified SSH/Tunnel configuration is missing")
    username = input("要授予管理員權限的既有 username：").strip()
    if not username:
        raise RuntimeError("Username is required")

    engine = build_engine(settings, readonly=False)
    try:
        with engine.begin() as c:
            database = c.execute(text("SELECT current_database()")).scalar()
            version = c.execute(text("SELECT version_num FROM public.alembic_version")).scalar()
            if database != "project_db" or version != "0007_admin_console":
                raise RuntimeError("Expected project_db with migration 0007_admin_console")
            c.execute(text("SELECT pg_advisory_xact_lock(hashtext('foodiemo-first-admin-v1'))"))
            if c.execute(text("SELECT count(*) FROM public.users WHERE role='admin'")).scalar():
                raise RuntimeError("An admin account already exists; use the admin console instead")
            target = c.execute(text("""
                SELECT user_id,username FROM public.users
                WHERE lower(username)=lower(:username) AND email_verified AND account_status='active'
                FOR UPDATE
            """), {"username": username}).mappings().first()
            if not target:
                raise RuntimeError("No active, verified account matches that username")
            print("Target account: @" + target["username"])
            if input("To confirm, type PROMOTE " + target["username"] + ": ").strip() != "PROMOTE " + target["username"]:
                raise RuntimeError("Confirmation did not match; no change was made")
            c.execute(text("UPDATE public.users SET role='admin',updated_at=now() WHERE user_id=:id"), {"id": target["user_id"]})
            c.execute(text("""
                INSERT INTO public.admin_audit_logs(actor_id,action,target_type,target_id,reason,details)
                VALUES(:id,'admin.first_bootstrap','user',:id,'Initial administrator setup',
                       '{"bootstrap":true}'::jsonb)
            """), {"id": target["user_id"]})
        print("First admin configured for @" + target["username"] + ". Reload the profile page to show the admin console entry.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Admin bootstrap stopped: " + str(exc), file=sys.stderr)
        sys.exit(1)
